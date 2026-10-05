"""Hand-written lexer (a manual DFA: dispatch on first character, then
consume the longest matching lexeme)."""
from typing import List

from .errors import LexError
from .tokens import KEYWORDS, ONE_CHAR, TWO_CHAR, TT, Token


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_trivia(self) -> None:
        while True:
            ch = self._peek()
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while self._peek() not in ("", "\n"):
                    self._advance()
            elif ch == "/" and self._peek(1) == "*":
                line, col = self.line, self.col
                self._advance(); self._advance()
                while not (self._peek() == "*" and self._peek(1) == "/"):
                    if self._peek() == "":
                        raise LexError("unterminated block comment", line, col)
                    self._advance()
                self._advance(); self._advance()
            else:
                return

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while True:
            self._skip_trivia()
            line, col = self.line, self.col
            ch = self._peek()
            if ch == "":
                tokens.append(Token(TT.EOF, "", line, col))
                return tokens
            if ch.isdigit():
                start = self.pos
                while self._peek().isdigit():
                    self._advance()
                if self._peek().isalpha() or self._peek() == "_":
                    raise LexError("invalid number literal", line, col)
                tokens.append(Token(TT.INT_LIT, self.src[start:self.pos], line, col))
            elif ch.isalpha() or ch == "_":
                start = self.pos
                while self._peek().isalnum() or self._peek() == "_":
                    self._advance()
                text = self.src[start:self.pos]
                tokens.append(Token(KEYWORDS.get(text, TT.ID), text, line, col))
            elif ch + self._peek(1) in TWO_CHAR:
                text = self._advance() + self._advance()
                tokens.append(Token(TWO_CHAR[text], text, line, col))
            elif ch in ONE_CHAR:
                self._advance()
                tokens.append(Token(ONE_CHAR[ch], ch, line, col))
            else:
                raise LexError(f"unexpected character {ch!r}", line, col)


def tokenize(source: str) -> List[Token]:
    return Lexer(source).tokenize()
