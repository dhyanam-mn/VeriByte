"""Recursive-descent parser. Expressions use one method per precedence
level (lowest to highest), which is the textbook LL(1)-style grammar
with left recursion removed and loops used for left associativity."""
from typing import List

from . import ast_nodes as A
from .errors import ParseError
from .lexer import tokenize
from .tokens import TT, Token


class Parser:
    def __init__(self, tokens: List[Token]):
        self.toks = tokens
        self.i = 0

    # ---- helpers ----
    @property
    def cur(self) -> Token:
        return self.toks[self.i]

    def _check(self, *types: TT) -> bool:
        return self.cur.type in types

    def _match(self, *types: TT):
        if self.cur.type in types:
            tok = self.cur
            self.i += 1
            return tok
        return None

    def _expect(self, tt: TT, what: str) -> Token:
        if self.cur.type is tt:
            tok = self.cur
            self.i += 1
            return tok
        raise ParseError(
            f"expected {what}, found {self.cur.type.name} {self.cur.lexeme!r}",
            self.cur.line, self.cur.col)

    # ---- top level ----
    def parse_program(self) -> A.Program:
        first = self.cur
        funcs = []
        while not self._check(TT.EOF):
            funcs.append(self._function())
        return A.Program(first.line, first.col, funcs)

    def _type(self) -> str:
        tok = self._match(TT.INT, TT.BOOL)
        if tok is None:
            raise ParseError(
                f"expected type 'int' or 'bool', found {self.cur.lexeme!r}",
                self.cur.line, self.cur.col)
        return tok.lexeme

    def _function(self) -> A.Function:
        kw = self._expect(TT.FUNC, "'func'")
        name = self._expect(TT.ID, "function name")
        self._expect(TT.LPAREN, "'('")
        params: List[A.Param] = []
        if not self._check(TT.RPAREN):
            while True:
                p = self._expect(TT.ID, "parameter name")
                self._expect(TT.COLON, "':'")
                params.append(A.Param(p.line, p.col, p.lexeme, self._type()))
                if not self._match(TT.COMMA):
                    break
        self._expect(TT.RPAREN, "')'")
        self._expect(TT.COLON, "':' before return type")
        ret = self._type()
        body = self._block()
        return A.Function(kw.line, kw.col, name.lexeme, params, ret, body)

    # ---- statements ----
    def _block(self) -> A.Block:
        lb = self._expect(TT.LBRACE, "'{'")
        stmts = []
        while not self._check(TT.RBRACE, TT.EOF):
            stmts.append(self._statement())
        self._expect(TT.RBRACE, "'}'")
        return A.Block(lb.line, lb.col, stmts)

    def _statement(self):
        t = self.cur
        if self._match(TT.LET):
            name = self._expect(TT.ID, "variable name")
            self._expect(TT.COLON, "':'")
            ty = self._type()
            self._expect(TT.ASSIGN, "'='")
            init = self._expr()
            self._expect(TT.SEMI, "';'")
            return A.LetStmt(t.line, t.col, name.lexeme, ty, init)
        if self._match(TT.IF):
            self._expect(TT.LPAREN, "'('")
            cond = self._expr()
            self._expect(TT.RPAREN, "')'")
            then_b = self._block()
            else_b = None
            if self._match(TT.ELSE):
                # allow `else if` by wrapping the nested if in a block
                if self._check(TT.IF):
                    nested = self._statement()
                    else_b = A.Block(nested.line, nested.col, [nested])
                else:
                    else_b = self._block()
            return A.IfStmt(t.line, t.col, cond, then_b, else_b)
        if self._match(TT.WHILE):
            self._expect(TT.LPAREN, "'('")
            cond = self._expr()
            self._expect(TT.RPAREN, "')'")
            return A.WhileStmt(t.line, t.col, cond, self._block())
        if self._match(TT.RETURN):
            val = None if self._check(TT.SEMI) else self._expr()
            self._expect(TT.SEMI, "';'")
            return A.ReturnStmt(t.line, t.col, val)
        if self._match(TT.PRINT):
            self._expect(TT.LPAREN, "'('")
            val = self._expr()
            self._expect(TT.RPAREN, "')'")
            self._expect(TT.SEMI, "';'")
            return A.PrintStmt(t.line, t.col, val)
        if self._check(TT.LBRACE):
            return self._block()
        # assignment (ID '=' ...) vs expression statement (needs 1-token lookahead past ID)
        if self._check(TT.ID) and self.toks[self.i + 1].type is TT.ASSIGN:
            name = self._match(TT.ID)
            self._match(TT.ASSIGN)
            val = self._expr()
            self._expect(TT.SEMI, "';'")
            return A.AssignStmt(t.line, t.col, name.lexeme, val)
        e = self._expr()
        self._expect(TT.SEMI, "';'")
        return A.ExprStmt(t.line, t.col, e)

    # ---- expressions: one level per precedence tier ----
    def _expr(self):
        return self._or()

    def _binary_level(self, next_level, *ops: TT):
        left = next_level()
        while self.cur.type in ops:
            op = self.cur
            self.i += 1
            right = next_level()
            left = A.BinaryExpr(op.line, op.col, op.lexeme, left, right)
        return left

    def _or(self):        return self._binary_level(self._and, TT.OR)
    def _and(self):       return self._binary_level(self._equality, TT.AND)
    def _equality(self):  return self._binary_level(self._relational, TT.EQ, TT.NE)
    def _relational(self):
        return self._binary_level(self._additive, TT.LT, TT.GT, TT.LE, TT.GE)
    def _additive(self):  return self._binary_level(self._term, TT.PLUS, TT.MINUS)
    def _term(self):
        return self._binary_level(self._unary, TT.STAR, TT.SLASH, TT.PERCENT)

    def _unary(self):
        op = self._match(TT.MINUS, TT.NOT)
        if op:
            return A.UnaryExpr(op.line, op.col, op.lexeme, self._unary())
        return self._primary()

    def _primary(self):
        t = self.cur
        if self._match(TT.INT_LIT):
            return A.IntLit(t.line, t.col, int(t.lexeme))
        if self._match(TT.TRUE):
            return A.BoolLit(t.line, t.col, True)
        if self._match(TT.FALSE):
            return A.BoolLit(t.line, t.col, False)
        if self._match(TT.ID):
            if self._match(TT.LPAREN):
                args = []
                if not self._check(TT.RPAREN):
                    while True:
                        args.append(self._expr())
                        if not self._match(TT.COMMA):
                            break
                self._expect(TT.RPAREN, "')' after arguments")
                return A.CallExpr(t.line, t.col, t.lexeme, args)
            return A.VarRef(t.line, t.col, t.lexeme)
        if self._match(TT.LPAREN):
            e = self._expr()
            self._expect(TT.RPAREN, "')'")
            return e
        raise ParseError(
            f"expected expression, found {t.type.name} {t.lexeme!r}", t.line, t.col)


def parse(source: str) -> A.Program:
    return Parser(tokenize(source)).parse_program()
