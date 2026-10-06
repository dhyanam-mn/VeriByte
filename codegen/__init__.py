"""Code generation package: AST → bytecode, serializer, disassembler."""

from .generator import generate, BCFunction  # noqa: F401
from .serializer import (  # noqa: F401
    serialize, write_bytecode, load_bytecode,
    BCModule, BytecodeFormatError,
)
from .disassembler import disassemble, disassemble_function, disassemble_functions  # noqa: F401
from .opcodes import Op  # noqa: F401
