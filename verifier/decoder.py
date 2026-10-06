"""Bytecode instruction stream decoder and valid offset tracker."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple

from codegen.generator import BCFunction
from codegen.opcodes import MNEMONIC, OPERAND_SIZE, Op
from .errors import VerifyError


@dataclass
class Instruction:
    """Decoded bytecode instruction."""
    offset: int
    op: Op
    operand: Any
    size: int


def decode_function(fn: BCFunction) -> Tuple[List[Instruction], Set[int]]:
    """Decode instruction stream and record valid instruction start offsets.

    Raises VerifyError(rule='BAD_OPCODE') or VerifyError(rule='TRUNCATED').
    """
    code = fn.code
    instructions: List[Instruction] = []
    valid_starts: Set[int] = set()

    pc = 0
    code_len = len(code)

    while pc < code_len:
        op_byte = code[pc]
        try:
            op = Op(op_byte)
        except ValueError:
            raise VerifyError(
                func_name=fn.name,
                offset=pc,
                mnemonic=f"0x{op_byte:02X}",
                rule="BAD_OPCODE",
                expected="valid opcode byte",
                actual=f"0x{op_byte:02X}",
            )

        operand_size = OPERAND_SIZE[op]
        if pc + 1 + operand_size > code_len:
            raise VerifyError(
                func_name=fn.name,
                offset=pc,
                mnemonic=op.name,
                rule="TRUNCATED",
                expected=f"{operand_size} byte operand",
                actual=f"only {code_len - pc - 1} byte(s) remaining",
            )

        if op == Op.PUSH_BOOL:
            b_val = code[pc + 1]
            if b_val not in (0, 1):
                raise VerifyError(
                    func_name=fn.name,
                    offset=pc,
                    mnemonic=op.name,
                    rule="BAD_OPCODE",
                    expected="0 or 1 for bool operand",
                    actual=str(b_val),
                )
            operand: Any = bool(b_val != 0)
        elif operand_size == 1:
            operand = code[pc + 1]
        elif operand_size == 2:
            operand = struct.unpack_from("<H", code, pc + 1)[0]
        elif operand_size == 4:
            operand = struct.unpack_from("<i", code, pc + 1)[0]
        else:
            operand = None

        instr_size = 1 + operand_size
        instructions.append(Instruction(
            offset=pc,
            op=op,
            operand=operand,
            size=instr_size,
        ))
        valid_starts.add(pc)
        pc += instr_size

    return instructions, valid_starts
