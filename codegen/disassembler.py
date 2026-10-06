"""Disassembler: prints bytecode in a human-readable text format.

Output format per function:
    == function_name(param_types): return_type  locals=N  max_stack=M ==
    0000  PUSH_INT       42
    0005  STORE          0
    ...
"""

from __future__ import annotations

import struct
from io import StringIO
from typing import List

from .generator import BCFunction
from .opcodes import MNEMONIC, OPERAND_SIZE, Op
from .serializer import BCModule


def disassemble_function(fn: BCFunction) -> str:
    """Disassemble a single function to a string."""
    out = StringIO()

    # Header
    params_str = ", ".join(fn.param_types) if fn.param_types else ""
    out.write(
        f"== {fn.name}({params_str}): {fn.return_type}"
        f"  locals={fn.num_locals}  max_stack={fn.max_stack} ==\n"
    )

    code = fn.code
    pc = 0
    while pc < len(code):
        op_byte = code[pc]
        try:
            op = Op(op_byte)
        except ValueError:
            out.write(f"  {pc:04d}  ??? (0x{op_byte:02X})\n")
            pc += 1
            continue

        mnemonic = MNEMONIC[op]
        operand_size = OPERAND_SIZE[op]
        pc += 1  # past the opcode byte

        if operand_size == 0:
            out.write(f"  {pc - 1:04d}  {mnemonic}\n")
        elif operand_size == 1:
            val = code[pc]
            out.write(f"  {pc - 1:04d}  {mnemonic:<15s}{val}\n")
            pc += 1
        elif operand_size == 2:
            val = struct.unpack_from("<H", code, pc)[0]
            out.write(f"  {pc - 1:04d}  {mnemonic:<15s}{val}\n")
            pc += 2
        elif operand_size == 4:
            val = struct.unpack_from("<i", code, pc)[0]
            out.write(f"  {pc - 1:04d}  {mnemonic:<15s}{val}\n")
            pc += 4

    return out.getvalue()


def disassemble(module: BCModule) -> str:
    """Disassemble a full BCModule to a string."""
    return "\n\n".join(disassemble_function(fn).rstrip() for fn in module.functions) + "\n"


def disassemble_functions(functions: List[BCFunction]) -> str:
    """Disassemble a list of BCFunction (without a BCModule wrapper)."""
    return "\n\n".join(disassemble_function(fn).rstrip() for fn in functions) + "\n"
