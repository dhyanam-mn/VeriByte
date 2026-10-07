"""Semantic analyzer: two-pass type checking with return-path analysis.

Pass 1: collect every function signature into the symbol table (so forward
        calls and mutual recursion work).
Pass 2: type-check each function body.

The analyzer annotates AST nodes in-place:
    - Every Expr node gets a `.resolved_type` attribute ("int" or "bool").
    - Every VarRef gets a `.slot` attribute (local index).
    - Every LetStmt gets a `.slot` attribute.
    - Every Function gets a `.num_locals` attribute.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from minilang import ast_nodes as A
from .errors import SemanticError
from .symtab import FuncSig, SymbolTable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ARITH_OPS = {"+", "-", "*", "/", "%"}
_REL_OPS = {"<", ">", "<=", ">="}
_EQ_OPS = {"==", "!="}
_BOOL_OPS = {"&&", "||"}


def _type_name(t: str) -> str:
    """Human-friendly type name (just passes through 'int'/'bool')."""
    return t


# ---------------------------------------------------------------------------
# Return-path analysis
# ---------------------------------------------------------------------------

def _always_returns(stmts: List[A.Stmt]) -> bool:
    """True if every control-flow path through `stmts` ends in a return."""
    for stmt in stmts:
        if isinstance(stmt, A.ReturnStmt):
            return True
        if isinstance(stmt, A.IfStmt):
            if (stmt.else_block is not None
                    and _always_returns(stmt.then_block.stmts)
                    and _always_returns(stmt.else_block.stmts)):
                return True
        if isinstance(stmt, A.Block):
            if _always_returns(stmt.stmts):
                return True
    return False


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class _Analyzer:
    def __init__(self) -> None:
        self.st = SymbolTable()
        self._current_func: Optional[A.Function] = None

    # ---- entry point ----
    def check(self, prog: A.Program) -> None:
        # Pass 1: register function signatures
        for fn in prog.functions:
            if self.st.lookup_function(fn.name) is not None:
                raise SemanticError(
                    f"duplicate function '{fn.name}'", fn.line, fn.col)
            ptypes = [p.type_name for p in fn.params]
            sig = FuncSig(ptypes, fn.return_type, fn.line, fn.col)
            self.st.register_function(fn.name, sig)

        # Check that main exists with correct signature
        main_sig = self.st.lookup_function("main")
        if main_sig is None:
            raise SemanticError(
                "missing 'main' function", prog.line, prog.col)
        if main_sig.param_types:
            raise SemanticError(
                "'main' must take no parameters",
                main_sig.line, main_sig.col)
        if main_sig.return_type != "int":
            raise SemanticError(
                "'main' must return int",
                main_sig.line, main_sig.col)

        # Pass 2: type-check each function body
        for fn in prog.functions:
            self._check_function(fn)

    # ---- function ----
    def _check_function(self, fn: A.Function) -> None:
        self._current_func = fn
        self.st.enter_function()

        # Declare parameters as locals (slot 0..n-1) in the function's
        # top-level scope — which is the *same* scope as the body block, so
        # a `let` in the body that reuses a parameter name is rejected.
        self.st.enter_scope()
        seen_params: Dict[str, int] = {}
        for p in fn.params:
            if p.name in seen_params:
                raise SemanticError(
                    f"duplicate parameter '{p.name}'", p.line, p.col)
            seen_params[p.name] = 1
            self.st.declare_variable(p.name, p.type_name, p.line, p.col)

        # Check the body statements *without* opening another scope (params
        # and body-level lets share the same scope).
        for stmt in fn.body.stmts:
            self._check_stmt(stmt)
        self.st.exit_scope()

        # Every path must return
        if not _always_returns(fn.body.stmts):
            raise SemanticError(
                f"function '{fn.name}' may not return on all paths",
                fn.line, fn.col)

        fn.num_locals = self.st._next_slot  # type: ignore[attr-defined]
        self.st.exit_function(fn.name)
        self._current_func = None

    # ---- block / statements ----
    def _check_block(self, block: A.Block) -> None:
        self.st.enter_scope()
        for stmt in block.stmts:
            self._check_stmt(stmt)
        self.st.exit_scope()

    def _check_stmt(self, stmt: A.Stmt) -> None:
        if isinstance(stmt, A.LetStmt):
            self._check_let(stmt)
        elif isinstance(stmt, A.AssignStmt):
            self._check_assign(stmt)
        elif isinstance(stmt, A.IfStmt):
            self._check_if(stmt)
        elif isinstance(stmt, A.WhileStmt):
            self._check_while(stmt)
        elif isinstance(stmt, A.ReturnStmt):
            self._check_return(stmt)
        elif isinstance(stmt, A.PrintStmt):
            self._check_print(stmt)
        elif isinstance(stmt, A.ExprStmt):
            self._check_expr(stmt.expr)
        elif isinstance(stmt, A.Block):
            self._check_block(stmt)
        else:
            raise SemanticError(
                f"unexpected statement type {type(stmt).__name__}",
                stmt.line, stmt.col)

    def _check_let(self, stmt: A.LetStmt) -> None:
        # Duplicate in same scope?
        if self.st.has_in_current_scope(stmt.name):
            raise SemanticError(
                f"duplicate declaration of '{stmt.name}' in the same scope",
                stmt.line, stmt.col)
        # Type-check initializer
        init_type = self._check_expr(stmt.init)
        if init_type != stmt.type_name:
            raise SemanticError(
                f"initializer type mismatch: declared {stmt.type_name}, "
                f"got {init_type}",
                stmt.line, stmt.col)
        info = self.st.declare_variable(stmt.name, stmt.type_name,
                                        stmt.line, stmt.col)
        stmt.slot = info.slot  # type: ignore[attr-defined]

    def _check_assign(self, stmt: A.AssignStmt) -> None:
        info = self.st.lookup_variable(stmt.name)
        if info is None:
            raise SemanticError(
                f"undeclared variable '{stmt.name}'",
                stmt.line, stmt.col)
        val_type = self._check_expr(stmt.value)
        if val_type != info.type:
            raise SemanticError(
                f"assignment type mismatch for '{stmt.name}': "
                f"expected {info.type}, got {val_type}",
                stmt.line, stmt.col)
        stmt.slot = info.slot  # type: ignore[attr-defined]

    def _check_if(self, stmt: A.IfStmt) -> None:
        cond_type = self._check_expr(stmt.cond)
        if cond_type != "bool":
            raise SemanticError(
                f"if condition must be bool, got {cond_type}",
                stmt.line, stmt.col)
        self._check_block(stmt.then_block)
        if stmt.else_block is not None:
            self._check_block(stmt.else_block)

    def _check_while(self, stmt: A.WhileStmt) -> None:
        cond_type = self._check_expr(stmt.cond)
        if cond_type != "bool":
            raise SemanticError(
                f"while condition must be bool, got {cond_type}",
                stmt.line, stmt.col)
        self._check_block(stmt.body)

    def _check_return(self, stmt: A.ReturnStmt) -> None:
        assert self._current_func is not None
        if stmt.value is None:
            raise SemanticError(
                "return without a value (every function must return a value)",
                stmt.line, stmt.col)
        val_type = self._check_expr(stmt.value)
        if val_type != self._current_func.return_type:
            raise SemanticError(
                f"return type mismatch: expected "
                f"{self._current_func.return_type}, got {val_type}",
                stmt.line, stmt.col)

    def _check_print(self, stmt: A.PrintStmt) -> None:
        self._check_expr(stmt.value)

    # ---- expressions ----
    def _check_expr(self, expr: A.Expr) -> str:
        """Type-check `expr`, annotate it with `.resolved_type`, and return
        the type string."""
        ty = self._infer(expr)
        expr.resolved_type = ty  # type: ignore[attr-defined]
        return ty

    def _infer(self, expr: A.Expr) -> str:
        if isinstance(expr, A.IntLit):
            if expr.value > 2147483647:
                raise SemanticError(
                    f"integer literal {expr.value} exceeds 32-bit signed max 2147483647",
                    expr.line, expr.col)
            return "int"
        if isinstance(expr, A.BoolLit):
            return "bool"
        if isinstance(expr, A.VarRef):
            return self._infer_var(expr)
        if isinstance(expr, A.UnaryExpr):
            return self._infer_unary(expr)
        if isinstance(expr, A.BinaryExpr):
            return self._infer_binary(expr)
        if isinstance(expr, A.CallExpr):
            return self._infer_call(expr)
        raise SemanticError(
            f"unexpected expression type {type(expr).__name__}",
            expr.line, expr.col)

    def _infer_var(self, expr: A.VarRef) -> str:
        info = self.st.lookup_variable(expr.name)
        if info is None:
            raise SemanticError(
                f"undeclared variable '{expr.name}'",
                expr.line, expr.col)
        expr.slot = info.slot  # type: ignore[attr-defined]
        return info.type

    def _infer_unary(self, expr: A.UnaryExpr) -> str:
        if expr.op == "-" and isinstance(expr.operand, A.IntLit) and expr.operand.value == 2147483648:
            expr.operand.resolved_type = "int"
            return "int"
        operand_type = self._check_expr(expr.operand)
        if expr.op == "-":
            if operand_type != "int":
                raise SemanticError(
                    f"unary '-' requires int operand, got {operand_type}",
                    expr.line, expr.col)
            return "int"
        if expr.op == "!":
            if operand_type != "bool":
                raise SemanticError(
                    f"unary '!' requires bool operand, got {operand_type}",
                    expr.line, expr.col)
            return "bool"
        raise SemanticError(
            f"unknown unary operator '{expr.op}'", expr.line, expr.col)

    def _infer_binary(self, expr: A.BinaryExpr) -> str:
        left_type = self._check_expr(expr.left)
        right_type = self._check_expr(expr.right)
        op = expr.op

        if op in _ARITH_OPS:
            if left_type != "int":
                raise SemanticError(
                    f"left operand of '{op}' must be int, got {left_type}",
                    expr.line, expr.col)
            if right_type != "int":
                raise SemanticError(
                    f"right operand of '{op}' must be int, got {right_type}",
                    expr.line, expr.col)
            return "int"

        if op in _REL_OPS:
            if left_type != "int":
                raise SemanticError(
                    f"left operand of '{op}' must be int, got {left_type}",
                    expr.line, expr.col)
            if right_type != "int":
                raise SemanticError(
                    f"right operand of '{op}' must be int, got {right_type}",
                    expr.line, expr.col)
            return "bool"

        if op in _EQ_OPS:
            if left_type != right_type:
                raise SemanticError(
                    f"'{op}' requires same types, got {left_type} and "
                    f"{right_type}",
                    expr.line, expr.col)
            return "bool"

        if op in _BOOL_OPS:
            if left_type != "bool":
                raise SemanticError(
                    f"left operand of '{op}' must be bool, got {left_type}",
                    expr.line, expr.col)
            if right_type != "bool":
                raise SemanticError(
                    f"right operand of '{op}' must be bool, got {right_type}",
                    expr.line, expr.col)
            return "bool"

        raise SemanticError(
            f"unknown binary operator '{op}'", expr.line, expr.col)

    def _infer_call(self, expr: A.CallExpr) -> str:
        sig = self.st.lookup_function(expr.name)
        if sig is None:
            raise SemanticError(
                f"undeclared function '{expr.name}'",
                expr.line, expr.col)
        # Check arity
        if len(expr.args) != len(sig.param_types):
            raise SemanticError(
                f"function '{expr.name}' expects {len(sig.param_types)} "
                f"argument(s), got {len(expr.args)}",
                expr.line, expr.col)
        # Check argument types
        for i, (arg, expected) in enumerate(zip(expr.args, sig.param_types)):
            arg_type = self._check_expr(arg)
            if arg_type != expected:
                raise SemanticError(
                    f"argument {i + 1} of '{expr.name}' must be {expected}, "
                    f"got {arg_type}",
                    expr.line, expr.col)
        return sig.return_type


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze(prog: A.Program) -> SymbolTable:
    """Semantically analyze `prog`, raising SemanticError on failure.

    On success, AST nodes are annotated with type and slot info, and the
    returned SymbolTable contains function signatures and local counts.
    """
    a = _Analyzer()
    a.check(prog)
    return a.st
