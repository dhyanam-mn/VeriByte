"""Worklist abstract interpreter and static verifier."""

from __future__ import annotations

from typing import Dict, List, Set

from codegen.generator import BCFunction
from codegen.opcodes import Op
from codegen.serializer import BCModule
from .cfg import check_jump_targets, compute_successors
from .decoder import Instruction, decode_function
from .errors import VerifyError
from .state import CONFLICT, State, UNSET, merge_states


def verify_module_header(module: BCModule) -> None:
    """Validate module-level header, function table, and entry function."""
    if not module.functions:
        raise VerifyError("<header>", 0, "HEADER", "BAD_CALL",
                          expected="at least one function", actual="0 functions")

    if not (0 <= module.entry_func < len(module.functions)):
        raise VerifyError("<header>", 0, "HEADER", "BAD_CALL",
                          expected=f"entry_func index < {len(module.functions)}",
                          actual=f"entry_func index {module.entry_func}")

    entry_fn = module.functions[module.entry_func]
    if entry_fn.name != "main" or len(entry_fn.param_types) != 0 or entry_fn.return_type != "int":
        raise VerifyError(entry_fn.name, 0, "HEADER", "BAD_CALL",
                          expected="entry function 'main(): int' taking 0 parameters",
                          actual=f"{entry_fn.name}({', '.join(entry_fn.param_types)}): {entry_fn.return_type}")

    for i, fn in enumerate(module.functions):
        if len(fn.local_types) != fn.num_locals:
            raise VerifyError(fn.name, 0, "SIGNATURE", "LOCAL_RANGE",
                              expected=f"len(local_types) == num_locals ({fn.num_locals})",
                              actual=f"len(local_types) == {len(fn.local_types)}")
        if fn.num_locals < len(fn.param_types):
            raise VerifyError(fn.name, 0, "SIGNATURE", "LOCAL_RANGE",
                              expected=f"num_locals >= num_params ({len(fn.param_types)})",
                              actual=f"num_locals {fn.num_locals}")
        if fn.local_types[:len(fn.param_types)] != fn.param_types:
            raise VerifyError(fn.name, 0, "SIGNATURE", "LOCAL_TYPE",
                              expected=f"parameters match initial locals {fn.param_types}",
                              actual=f"initial locals {fn.local_types[:len(fn.param_types)]}")


def verify_function(fn: BCFunction, module: BCModule) -> None:
    """Verify a single function using abstract interpretation."""
    code_len = len(fn.code)
    if code_len == 0:
        raise VerifyError(
            func_name=fn.name,
            offset=0,
            mnemonic="<empty>",
            rule="FALLTHROUGH",
            expected="non-empty code ending in RET or HALT",
            actual="empty code",
        )

    # 1. Decode instruction stream & identify valid instruction starts
    instructions, valid_starts = decode_function(fn)

    # 2. Check all jump targets
    check_jump_targets(fn, instructions, valid_starts)

    instr_map: Dict[int, Instruction] = {inst.offset: inst for inst in instructions}

    # 3. Worklist abstract interpretation
    entry_locals = list(fn.param_types) + [UNSET] * (fn.num_locals - len(fn.param_types))
    entry_state = State(stack=(), locals=tuple(entry_locals))

    states: Dict[int, State] = {0: entry_state}
    worklist: List[int] = [0]
    in_worklist: Set[int] = {0}

    while worklist:
        pc = worklist.pop(0)
        in_worklist.remove(pc)

        state = states[pc]
        instr = instr_map[pc]
        op = instr.op
        mnemonic = op.name
        stack = state.stack
        locals_tuple = state.locals

        out_state: State | None = None

        if op == Op.PUSH_INT:
            if len(stack) + 1 > fn.max_stack:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_OVERFLOW",
                                  expected=f"depth <= {fn.max_stack}", actual=f"{list(stack)}")
            out_state = State(stack=stack + ("int",), locals=locals_tuple)

        elif op == Op.PUSH_BOOL:
            if len(stack) + 1 > fn.max_stack:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_OVERFLOW",
                                  expected=f"depth <= {fn.max_stack}", actual=f"{list(stack)}")
            out_state = State(stack=stack + ("bool",), locals=locals_tuple)

        elif op == Op.POP:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-1], locals=locals_tuple)

        elif op == Op.DUP:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            if len(stack) + 1 > fn.max_stack:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_OVERFLOW",
                                  expected=f"depth <= {fn.max_stack}", actual=f"{list(stack)}")
            out_state = State(stack=stack + (stack[-1],), locals=locals_tuple)

        elif op in (Op.ADD, Op.SUB, Op.MUL, Op.DIV, Op.MOD):
            if len(stack) < 2:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 2", actual=f"{list(stack)}")
            b, a = stack[-1], stack[-2]
            if a != "int" or b != "int":
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="[int, int]", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-2] + ("int",), locals=locals_tuple)

        elif op == Op.NEG:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            if stack[-1] != "int":
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="top is int", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-1] + ("int",), locals=locals_tuple)

        elif op in (Op.AND, Op.OR):
            if len(stack) < 2:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 2", actual=f"{list(stack)}")
            b, a = stack[-1], stack[-2]
            if a != "bool" or b != "bool":
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="[bool, bool]", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-2] + ("bool",), locals=locals_tuple)

        elif op == Op.NOT:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            if stack[-1] != "bool":
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="top is bool", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-1] + ("bool",), locals=locals_tuple)

        elif op in (Op.EQ, Op.NE):
            if len(stack) < 2:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 2", actual=f"{list(stack)}")
            b, a = stack[-1], stack[-2]
            if a != b:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="same types on stack", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-2] + ("bool",), locals=locals_tuple)

        elif op in (Op.LT, Op.GT, Op.LE, Op.GE):
            if len(stack) < 2:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 2", actual=f"{list(stack)}")
            b, a = stack[-1], stack[-2]
            if a != "int" or b != "int":
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="[int, int]", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-2] + ("bool",), locals=locals_tuple)

        elif op == Op.LOAD:
            idx = instr.operand
            if idx >= fn.num_locals:
                raise VerifyError(fn.name, pc, mnemonic, "LOCAL_RANGE",
                                  expected=f"local < {fn.num_locals}", actual=f"local {idx}")
            val = locals_tuple[idx]
            if val == UNSET or val == CONFLICT:
                raise VerifyError(fn.name, pc, mnemonic, "LOCAL_UNSET",
                                  expected=f"definitely assigned local {idx}", actual=val)
            if len(stack) + 1 > fn.max_stack:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_OVERFLOW",
                                  expected=f"depth <= {fn.max_stack}", actual=f"{list(stack)}")
            out_state = State(stack=stack + (val,), locals=locals_tuple)

        elif op == Op.STORE:
            idx = instr.operand
            if idx >= fn.num_locals:
                raise VerifyError(fn.name, pc, mnemonic, "LOCAL_RANGE",
                                  expected=f"local < {fn.num_locals}", actual=f"local {idx}")
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            val = stack[-1]
            declared_type = fn.local_types[idx]
            if val != declared_type:
                raise VerifyError(fn.name, pc, mnemonic, "LOCAL_TYPE",
                                  expected=f"type '{declared_type}'", actual=f"'{val}'")
            new_locals = list(locals_tuple)
            new_locals[idx] = val
            out_state = State(stack=stack[:-1], locals=tuple(new_locals))

        elif op == Op.JMP:
            out_state = state

        elif op == Op.JMP_IF_FALSE:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            if stack[-1] != "bool":
                raise VerifyError(fn.name, pc, mnemonic, "STACK_TYPE",
                                  expected="top is bool", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-1], locals=locals_tuple)

        elif op == Op.CALL:
            func_idx = instr.operand
            if func_idx >= len(module.functions):
                raise VerifyError(fn.name, pc, mnemonic, "BAD_CALL",
                                  expected=f"func_idx < {len(module.functions)}", actual=f"func_idx {func_idx}")
            callee = module.functions[func_idx]
            num_args = len(callee.param_types)
            if len(stack) < num_args:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected=f"at least {num_args} args", actual=f"{list(stack)}")
            args = list(stack[len(stack) - num_args:])
            if args != callee.param_types:
                raise VerifyError(fn.name, pc, mnemonic, "BAD_CALL",
                                  expected=f"arguments {callee.param_types}", actual=f"arguments {args}")
            stack_popped = stack[:len(stack) - num_args]
            if len(stack_popped) + 1 > fn.max_stack:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_OVERFLOW",
                                  expected=f"depth <= {fn.max_stack}", actual=f"{list(stack_popped)}")
            out_state = State(stack=stack_popped + (callee.return_type,), locals=locals_tuple)

        elif op == Op.RET:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            if stack[-1] != fn.return_type or len(stack) != 1:
                raise VerifyError(fn.name, pc, mnemonic, "BAD_RETURN",
                                  expected=f"[{fn.return_type}]", actual=f"{list(stack)}")
            out_state = None

        elif op == Op.PRINT:
            if len(stack) < 1:
                raise VerifyError(fn.name, pc, mnemonic, "STACK_UNDERFLOW",
                                  expected="depth >= 1", actual=f"{list(stack)}")
            out_state = State(stack=stack[:-1], locals=locals_tuple)

        elif op == Op.HALT:
            out_state = None

        if out_state is not None:
            succs = compute_successors(instr)
            for succ_pc in succs:
                if succ_pc == code_len:
                    raise VerifyError(fn.name, pc, mnemonic, "FALLTHROUGH",
                                      expected="RET, JMP, or HALT before EOF",
                                      actual="execution falls off end of code")
                if succ_pc not in states:
                    states[succ_pc] = out_state
                    if succ_pc not in in_worklist:
                        worklist.append(succ_pc)
                        in_worklist.add(succ_pc)
                else:
                    succ_mnemonic = instr_map[succ_pc].op.name
                    merged = merge_states(states[succ_pc], out_state, fn.name, succ_pc, succ_mnemonic)
                    if merged != states[succ_pc]:
                        states[succ_pc] = merged
                        if succ_pc not in in_worklist:
                            worklist.append(succ_pc)
                            in_worklist.add(succ_pc)


def verify(module: BCModule) -> None:
    """Verify that a compiled bytecode module satisfies all static safety properties.

    Raises VerifyError on any violation.
    """
    verify_module_header(module)
    for fn in module.functions:
        verify_function(fn, module)
