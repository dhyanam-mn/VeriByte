"""Verifier hook for bytecode loading and execution.

In Review 3, this will be connected to the static verifier.
Currently, this is a no-op hook.
"""

from codegen.serializer import BCModule
from verifier import verify as static_verify


def verify(program: BCModule) -> None:
    """Validate program safety before execution using the static verifier."""
    static_verify(program)

