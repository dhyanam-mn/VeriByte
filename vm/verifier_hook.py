"""Verifier hook for bytecode loading and execution.

In Review 3, this will be connected to the static verifier.
Currently, this is a no-op hook.
"""

from codegen.serializer import BCModule


def verify(program: BCModule) -> None:
    """Validate program safety before execution.

    Currently a no-op placeholder for the static verifier in Review 3.
    """
    pass
