"""VM runtime exceptions."""


class VMTrap(Exception):
    """Raised when execution hits a defined runtime trap, such as division or modulo by zero."""
    pass
