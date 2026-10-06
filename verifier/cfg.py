"""Control flow analysis, jump-target validation, and successor computation."""

from __future__ import annotations

from typing import List, Set

from codegen.generator import BCFunction
from codegen.opcodes import Op
from .decoder import Instruction
from .errors import VerifyError


def check_jump_targets(fn: BCFunction, instructions: List[Instruction], valid_starts: Set[int]) -> None:
    """Ensure every JMP / JMP_IF_FALSE target is a valid instruction start in this function.

    Raises VerifyError(rule='BAD_JUMP') if any target is outside code or lands mid-instruction.
    """
    for instr in instructions:
        if instr.op in (Op.JMP, Op.JMP_IF_FALSE):
            target = instr.operand
            if target not in valid_starts:
                raise VerifyError(
                    func_name=fn.name,
                    offset=instr.offset,
                    mnemonic=instr.op.name,
                    rule="BAD_JUMP",
                    expected="valid instruction start offset",
                    actual=f"target offset {target}",
                )


def compute_successors(instr: Instruction) -> List[int]:
    """Compute successor instruction offsets for a decoded instruction."""
    if instr.op == Op.JMP:
        return [instr.operand]
    if instr.op == Op.JMP_IF_FALSE:
        fallthrough = instr.offset + instr.size
        return [fallthrough, instr.operand]
    if instr.op in (Op.RET, Op.HALT):
        return []
    return [instr.offset + instr.size]
