"""Static verifier package."""

from .errors import VerifyError  # noqa: F401
from .decoder import Instruction, decode_function  # noqa: F401
from .verifier import verify, verify_function, verify_module_header  # noqa: F401
