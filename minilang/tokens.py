from dataclasses import dataclass
from enum import Enum, auto


class TT(Enum):
    # literals / identifiers
    INT_LIT = auto()
    ID = auto()
    # keywords
    FUNC = auto()
    LET = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    RETURN = auto()
    PRINT = auto()
    INT = auto()
    BOOL = auto()
    TRUE = auto()
    FALSE = auto()
    # operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()       # ==
    NE = auto()       # !=
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    AND = auto()      # &&
    OR = auto()       # ||
    NOT = auto()      # !
    ASSIGN = auto()   # =
    # delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    SEMI = auto()
    COLON = auto()
    EOF = auto()


KEYWORDS = {
    "func": TT.FUNC, "let": TT.LET, "if": TT.IF, "else": TT.ELSE,
    "while": TT.WHILE, "return": TT.RETURN, "print": TT.PRINT,
    "int": TT.INT, "bool": TT.BOOL, "true": TT.TRUE, "false": TT.FALSE,
}

# longest-match first
TWO_CHAR = {
    "==": TT.EQ, "!=": TT.NE, "<=": TT.LE, ">=": TT.GE,
    "&&": TT.AND, "||": TT.OR,
}
ONE_CHAR = {
    "+": TT.PLUS, "-": TT.MINUS, "*": TT.STAR, "/": TT.SLASH,
    "%": TT.PERCENT, "<": TT.LT, ">": TT.GT, "!": TT.NOT, "=": TT.ASSIGN,
    "(": TT.LPAREN, ")": TT.RPAREN, "{": TT.LBRACE, "}": TT.RBRACE,
    ",": TT.COMMA, ";": TT.SEMI, ":": TT.COLON,
}


@dataclass(frozen=True)
class Token:
    type: TT
    lexeme: str
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.line}:{self.col}\t{self.type.name}\t{self.lexeme!r}"
