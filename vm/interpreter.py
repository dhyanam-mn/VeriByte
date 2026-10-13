"""Bytecode Virtual Machine (interpreter).

Implements the stack-based VM for the MiniLang ISA v1.
- Fetch-decode-execute loop
- Per-call frames (locals, operand stack, program counter)
- CALL / RET
- PRINT to a configurable output stream
- 32-bit signed wraparound for integer arithmetic
- VMTrap on division / modulo by zero
- Raw Python exceptions allowed to surface for invalid code (stack underflow, bad jumps, etc.)
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional, TextIO

from codegen.generator import BCFunction
from codegen.opcodes import Op
from codegen.serializer import BCModule
from .exceptions import VMTrap, VMInvariantError


def to_i32(val: int) -> int:
    """Wrap integer into 32-bit signed range [-2^31, 2^31 - 1]."""
    val = val & 0xFFFFFFFF
    if val >= 0x80000000:
        val -= 0x100000000
    return val


def idiv(a: int, b: int) -> int:
    """32-bit integer division truncated towards zero, trapping on 0."""
    if b == 0:
        raise VMTrap("division by zero")
    neg = (a < 0) ^ (b < 0)
    res = -(abs(a) // abs(b)) if neg else abs(a) // abs(b)
    return to_i32(res)


def imod(a: int, b: int) -> int:
    """32-bit integer modulo with sign matching dividend, trapping on 0."""
    if b == 0:
        raise VMTrap("modulo by zero")
    rem = abs(a) % abs(b)
    if a < 0:
        rem = -rem
    return to_i32(rem)


@dataclass
class Frame:
    """Activation frame for a single function call."""
    fn: BCFunction
    pc: int = 0
    locals: List[Any] = field(default_factory=list)
    stack: List[Any] = field(default_factory=list)


class VM:
    """Stack-based virtual machine interpreter."""

    def __init__(
        self,
        stdout: Optional[TextIO] = None,
        checked: bool = False,
        max_call_depth: int = 10000,
    ) -> None:
        self.stdout: TextIO = stdout if stdout is not None else sys.stdout
        self.checked: bool = checked
        self.max_call_depth: int = max_call_depth

    def run(
        self,
        module: BCModule,
        max_steps: Optional[int] = None,
        max_call_depth: Optional[int] = None,
    ) -> Any:
        """Execute a compiled module starting from its entry_func."""
        limit_call_depth = max_call_depth if max_call_depth is not None else self.max_call_depth

        valid_starts_map: dict[int, set[int]] = {}
        if self.checked:
            from verifier.decoder import decode_function
            for fn in module.functions:
                try:
                    _, vs = decode_function(fn)
                    valid_starts_map[id(fn)] = vs
                except Exception:
                    valid_starts_map[id(fn)] = set()

        entry_fn = module.functions[module.entry_func]
        initial_frame = Frame(
            fn=entry_fn,
            pc=0,
            locals=[None] * entry_fn.num_locals,
            stack=[],
        )
        frames: List[Frame] = [initial_frame]
        steps = 0

        while frames:
            if max_steps is not None:
                steps += 1
                if steps > max_steps:
                    raise TimeoutError(f"Step limit {max_steps} exceeded")

            frame = frames[-1]
            code = frame.fn.code
            pc = frame.pc

            if self.checked:
                valid_starts = valid_starts_map.get(id(frame.fn), set())
                if pc < 0 or pc >= len(code) or pc not in valid_starts:
                    raise VMInvariantError(
                        f"pc {pc} is not a valid instruction start in {frame.fn.name}"
                    )

            # Fetch opcode
            op_byte = code[pc]
            frame.pc += 1

            op = Op(op_byte)

            if op == Op.PUSH_INT:
                val = struct.unpack_from("<i", code, frame.pc)[0]
                frame.pc += 4
                frame.stack.append(val)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(
                        f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}"
                    )

            elif op == Op.PUSH_BOOL:
                val = code[frame.pc]
                frame.pc += 1
                frame.stack.append(bool(val != 0))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(
                        f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}"
                    )

            elif op == Op.POP:
                frame.stack.pop()

            elif op == Op.DUP:
                frame.stack.append(frame.stack[-1])
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(
                        f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}"
                    )

            elif op == Op.ADD:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for ADD must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(to_i32(a + b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.SUB:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for SUB must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(to_i32(a - b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.MUL:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for MUL must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(to_i32(a * b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.DIV:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for DIV must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(idiv(a, b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.MOD:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for MOD must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(imod(a, b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.NEG:
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int:
                        raise VMInvariantError(f"operand for NEG must be int, got {type(a).__name__}")
                frame.stack.append(to_i32(-a))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.AND:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not bool or type(b) is not bool:
                        raise VMInvariantError(f"operands for AND must be bool, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(bool(a and b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.OR:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not bool or type(b) is not bool:
                        raise VMInvariantError(f"operands for OR must be bool, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(bool(a or b))
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.NOT:
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not bool:
                        raise VMInvariantError(f"operand for NOT must be bool, got {type(a).__name__}")
                frame.stack.append(not a)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.EQ:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not type(b):
                        raise VMInvariantError(f"operands for EQ must have matching types, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(a == b)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.NE:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not type(b):
                        raise VMInvariantError(f"operands for NE must have matching types, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(a != b)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.LT:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for LT must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(a < b)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.GT:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for GT must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(a > b)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.LE:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for LE must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(a <= b)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.GE:
                b = frame.stack.pop()
                a = frame.stack.pop()
                if self.checked:
                    if type(a) is not int or type(b) is not int:
                        raise VMInvariantError(f"operands for GE must be int, got {type(a).__name__} and {type(b).__name__}")
                frame.stack.append(a >= b)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.LOAD:
                local_idx = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc += 2
                if self.checked:
                    if local_idx >= frame.fn.num_locals:
                        raise VMInvariantError(f"local index {local_idx} >= num_locals {frame.fn.num_locals} in {frame.fn.name}")
                    val = frame.locals[local_idx]
                    if val is None:
                        raise VMInvariantError(f"LOAD from uninitialized local slot {local_idx} in {frame.fn.name}")
                else:
                    val = frame.locals[local_idx]
                frame.stack.append(val)
                if self.checked and len(frame.stack) > frame.fn.max_stack:
                    raise VMInvariantError(f"stack depth {len(frame.stack)} exceeds max_stack {frame.fn.max_stack} in {frame.fn.name}")

            elif op == Op.STORE:
                local_idx = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc += 2
                val = frame.stack.pop()
                if self.checked:
                    if local_idx >= frame.fn.num_locals:
                        raise VMInvariantError(f"local index {local_idx} >= num_locals {frame.fn.num_locals} in {frame.fn.name}")
                    expected_type = frame.fn.local_types[local_idx]
                    if expected_type == "int" and type(val) is not int:
                        raise VMInvariantError(f"STORE to local slot {local_idx} expected int, got {type(val).__name__}")
                    elif expected_type == "bool" and type(val) is not bool:
                        raise VMInvariantError(f"STORE to local slot {local_idx} expected bool, got {type(val).__name__}")
                frame.locals[local_idx] = val

            elif op == Op.JMP:
                target = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc = target

            elif op == Op.JMP_IF_FALSE:
                target = struct.unpack_from("<H", code, frame.pc)[0]
                cond = frame.stack.pop()
                if self.checked:
                    if type(cond) is not bool:
                        raise VMInvariantError(f"JMP_IF_FALSE condition must be bool, got {type(cond).__name__}")
                if not cond:
                    frame.pc = target
                else:
                    frame.pc += 2

            elif op == Op.CALL:
                func_idx = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc += 2
                if len(frames) >= limit_call_depth:
                    raise VMTrap("call depth exceeded")
                if self.checked:
                    if func_idx >= len(module.functions):
                        raise VMInvariantError(f"call target func_idx {func_idx} >= num_funcs {len(module.functions)}")
                target_fn = module.functions[func_idx]
                num_params = len(target_fn.param_types)
                # Arguments were pushed left-to-right, so top of stack is the last param
                args = [frame.stack.pop() for _ in range(num_params)]
                args.reverse()
                if self.checked:
                    for i, (arg, ptype) in enumerate(zip(args, target_fn.param_types)):
                        if ptype == "int" and type(arg) is not int:
                            raise VMInvariantError(f"CALL arg {i} to {target_fn.name} expected int, got {type(arg).__name__}")
                        elif ptype == "bool" and type(arg) is not bool:
                            raise VMInvariantError(f"CALL arg {i} to {target_fn.name} expected bool, got {type(arg).__name__}")

                new_locals = [None] * target_fn.num_locals
                new_locals[:num_params] = args
                new_frame = Frame(
                    fn=target_fn,
                    pc=0,
                    locals=new_locals,
                    stack=[],
                )
                frames.append(new_frame)

            elif op == Op.RET:
                if self.checked:
                    if len(frame.stack) != 1:
                        raise VMInvariantError(
                            f"RET in {frame.fn.name} does not leave exactly one value (depth {len(frame.stack)})"
                        )
                    ret_val_peek = frame.stack[0]
                    expected_ret = frame.fn.return_type
                    if expected_ret == "int" and type(ret_val_peek) is not int:
                        raise VMInvariantError(f"RET in {frame.fn.name} expected int, got {type(ret_val_peek).__name__}")
                    elif expected_ret == "bool" and type(ret_val_peek) is not bool:
                        raise VMInvariantError(f"RET in {frame.fn.name} expected bool, got {type(ret_val_peek).__name__}")
                ret_val = frame.stack.pop()
                frames.pop()
                if frames:
                    frames[-1].stack.append(ret_val)
                    if self.checked and len(frames[-1].stack) > frames[-1].fn.max_stack:
                        raise VMInvariantError(
                            f"caller stack depth {len(frames[-1].stack)} exceeds max_stack {frames[-1].fn.max_stack} in {frames[-1].fn.name}"
                        )
                else:
                    return ret_val

            elif op == Op.PRINT:
                val = frame.stack.pop()
                if isinstance(val, bool):
                    text = "true" if val else "false"
                else:
                    text = str(val)
                self.stdout.write(f"{text}\n")
                self.stdout.flush()

            elif op == Op.HALT:
                return frame.stack[-1] if frame.stack else 0

        return 0
