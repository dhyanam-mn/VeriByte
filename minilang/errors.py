class MiniLangError(Exception):
    """Base class for front-end errors, carrying a source position."""

    def __init__(self, message: str, line: int, col: int):
        super().__init__(f"{message} (line {line}, col {col})")
        self.message = message
        self.line = line
        self.col = col


class LexError(MiniLangError):
    pass


class ParseError(MiniLangError):
    pass
