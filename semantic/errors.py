"""SemanticError: reports type / scope errors with source positions."""

from minilang.errors import MiniLangError


class SemanticError(MiniLangError):
    """Raised by the semantic analyzer for any type, scope, or control-flow error."""
    pass
