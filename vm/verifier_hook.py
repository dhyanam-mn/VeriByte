"""Verifier hook for bytecode loading and execution.

Delegates to the static verifier to validate module and function safety invariants
before execution by the VM.
"""

from codegen.serializer import BCModule
from verifier import verify as static_verify


def verify(program: BCModule) -> None:
    """Validate program safety before execution using the static verifier."""
    static_verify(program)

