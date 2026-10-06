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
from .exceptions import VMTrap


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

    def __init__(self, stdout: Optional[TextIO] = None) -> None:
        self.stdout: TextIO = stdout if stdout is not None else sys.stdout

    def run(self, module: BCModule) -> Any:
        """Execute a compiled module starting from its entry_func."""
        entry_fn = module.functions[module.entry_func]
        initial_frame = Frame(
            fn=entry_fn,
            pc=0,
            locals=[None] * entry_fn.num_locals,
            stack=[],
        )
        frames: List[Frame] = [initial_frame]

        while frames:
            frame = frames[-1]
            code = frame.fn.code
            pc = frame.pc

            # Fetch opcode
            op_byte = code[pc]
            frame.pc += 1

            op = Op(op_byte)

            if op == Op.PUSH_INT:
                val = struct.unpack_from("<i", code, frame.pc)[0]
                frame.pc += 4
                frame.stack.append(val)

            elif op == Op.PUSH_BOOL:
                val = code[frame.pc]
                frame.pc += 1
                frame.stack.append(bool(val != 0))

            elif op == Op.POP:
                frame.stack.pop()

            elif op == Op.DUP:
                frame.stack.append(frame.stack[-1])

            elif op == Op.ADD:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(to_i32(a + b))

            elif op == Op.SUB:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(to_i32(a - b))

            elif op == Op.MUL:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(to_i32(a * b))

            elif op == Op.DIV:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(idiv(a, b))

            elif op == Op.MOD:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(imod(a, b))

            elif op == Op.NEG:
                a = frame.stack.pop()
                frame.stack.append(to_i32(-a))

            elif op == Op.AND:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(bool(a and b))

            elif op == Op.OR:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(bool(a or b))

            elif op == Op.NOT:
                a = frame.stack.pop()
                frame.stack.append(not a)

            elif op == Op.EQ:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(a == b)

            elif op == Op.NE:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(a != b)

            elif op == Op.LT:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(a < b)

            elif op == Op.GT:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(a > b)

            elif op == Op.LE:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(a <= b)

            elif op == Op.GE:
                b = frame.stack.pop()
                a = frame.stack.pop()
                frame.stack.append(a >= b)

            elif op == Op.LOAD:
                local_idx = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc += 2
                frame.stack.append(frame.locals[local_idx])

            elif op == Op.STORE:
                local_idx = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc += 2
                val = frame.stack.pop()
                frame.locals[local_idx] = val

            elif op == Op.JMP:
                target = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc = target

            elif op == Op.JMP_IF_FALSE:
                target = struct.unpack_from("<H", code, frame.pc)[0]
                cond = frame.stack.pop()
                if not cond:
                    frame.pc = target
                else:
                    frame.pc += 2

            elif op == Op.CALL:
                func_idx = struct.unpack_from("<H", code, frame.pc)[0]
                frame.pc += 2
                target_fn = module.functions[func_idx]
                num_params = len(target_fn.param_types)
                # Arguments were pushed left-to-right, so top of stack is the last param
                args = [frame.stack.pop() for _ in range(num_params)]
                args.reverse()

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
                ret_val = frame.stack.pop()
                frames.pop()
                if frames:
                    frames[-1].stack.append(ret_val)
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
