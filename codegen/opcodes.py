"""Opcode constants matching docs/ISA.md (v1).

Each opcode knows its hex encoding and the size of its inline operand
(0, 1, 2, or 4 bytes).  This module is the single source of truth for
opcode encoding in the code generator, serializer, and disassembler.
"""

from enum import IntEnum


class Op(IntEnum):
    PUSH_INT      = 0x01
    PUSH_BOOL     = 0x02
    POP           = 0x03
    DUP           = 0x04

    ADD           = 0x10
    SUB           = 0x11
    MUL           = 0x12
    DIV           = 0x13
    MOD           = 0x14
    NEG           = 0x15

    AND           = 0x20
    OR            = 0x21
    NOT           = 0x22

    EQ            = 0x30
    NE            = 0x31
    LT            = 0x32
    GT            = 0x33
    LE            = 0x34
    GE            = 0x35

    LOAD          = 0x40
    STORE         = 0x41

    JMP           = 0x50
    JMP_IF_FALSE  = 0x51

    CALL          = 0x60
    RET           = 0x61

    PRINT         = 0x70

    HALT          = 0xFF


# Operand sizes in bytes: 0 = none, 1 = u8, 2 = u16, 4 = i32
OPERAND_SIZE = {
    Op.PUSH_INT:      4,
    Op.PUSH_BOOL:     1,
    Op.POP:           0,
    Op.DUP:           0,
    Op.ADD:           0,
    Op.SUB:           0,
    Op.MUL:           0,
    Op.DIV:           0,
    Op.MOD:           0,
    Op.NEG:           0,
    Op.AND:           0,
    Op.OR:            0,
    Op.NOT:           0,
    Op.EQ:            0,
    Op.NE:            0,
    Op.LT:            0,
    Op.GT:            0,
    Op.LE:            0,
    Op.GE:            0,
    Op.LOAD:          2,
    Op.STORE:         2,
    Op.JMP:           2,
    Op.JMP_IF_FALSE:  2,
    Op.CALL:          2,
    Op.RET:           0,
    Op.PRINT:         0,
    Op.HALT:          0,
}

# Mnemonic names for disassembly (upper-case, matching ISA.md)
MNEMONIC = {op: op.name for op in Op}
