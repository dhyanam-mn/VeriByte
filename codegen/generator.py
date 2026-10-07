"""AST-to-bytecode code generator.

Translates a semantically-analyzed AST into a list of BCFunction objects,
following the compilation scheme from docs/ISA.md.  Uses label patching for
forward jumps (absolute byte offsets within a function's code).

The semantic analyzer must have already annotated:
  - Expr nodes with `.resolved_type` ("int" or "bool")
  - VarRef / LetStmt with `.slot` (local index)
  - Function with `.num_locals`
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from minilang import ast_nodes as A
from semantic import analyze
from semantic.analyzer import _always_returns
from semantic.symtab import SymbolTable
from .opcodes import Op


# ---------------------------------------------------------------------------
# Output representation
# ---------------------------------------------------------------------------

@dataclass
class BCFunction:
    """A compiled function ready for serialization."""
    name: str
    param_types: List[str]     # ["int", "bool", ...]
    return_type: str           # "int" | "bool"
    num_locals: int            # includes parameters
    local_types: List[str]     # declared types; parameters first
    max_stack: int
    code: bytes
    jump_targets: Optional[List[int]] = None


# ---------------------------------------------------------------------------
# Internal builder for a single function's code
# ---------------------------------------------------------------------------

class _Label:
    """A forward-reference placeholder for a jump target."""
    __slots__ = ("offset",)

    def __init__(self) -> None:
        self.offset: Optional[int] = None


class _FuncBuilder:
    """Emits bytecode for one function, tracking stack depth for max_stack."""

    def __init__(self, func_index_map: Dict[str, int],
                 st: SymbolTable) -> None:
        self._buf = bytearray()
        self._stack_depth = 0
        self._max_stack = 0
        self._patches: List[tuple[int, _Label]] = []  # (offset_in_buf, label)
        self._func_map = func_index_map
        self._st = st

    @property
    def pos(self) -> int:
        return len(self._buf)

    # ---- stack tracking ----
    def _push(self, n: int = 1) -> None:
        self._stack_depth += n
        if self._stack_depth > self._max_stack:
            self._max_stack = self._stack_depth

    def _pop(self, n: int = 1) -> None:
        self._stack_depth -= n

    # ---- emit helpers ----
    def emit_op(self, op: Op) -> None:
        self._buf.append(op)

    def emit_u8(self, val: int) -> None:
        self._buf.append(val & 0xFF)

    def emit_u16(self, val: int) -> None:
        self._buf.extend(struct.pack("<H", val))

    def emit_i32(self, val: int) -> None:
        self._buf.extend(struct.pack("<i", val))

    def new_label(self) -> _Label:
        return _Label()

    def place_label(self, label: _Label) -> None:
        label.offset = self.pos

    def emit_jump(self, op: Op, label: _Label) -> None:
        self.emit_op(op)
        self._patches.append((self.pos, label))
        self.emit_u16(0)  # placeholder

    def patch_jumps(self) -> None:
        self.jump_targets: List[int] = []
        for offset, label in self._patches:
            assert label.offset is not None, "label never placed"
            if label.offset > 65535:
                raise ValueError(f"jump target {label.offset} exceeds 16-bit max (65535)")
            self.jump_targets.append(label.offset)
            struct.pack_into("<H", self._buf, offset, label.offset)

    def finish(self) -> tuple[bytes, int]:
        self.patch_jumps()
        return bytes(self._buf), self._max_stack

    # ---- code generation ----

    def gen_expr(self, expr: A.Expr) -> None:
        if isinstance(expr, A.IntLit):
            self.emit_op(Op.PUSH_INT)
            self.emit_i32(expr.value)
            self._push()
        elif isinstance(expr, A.BoolLit):
            self.emit_op(Op.PUSH_BOOL)
            self.emit_u8(1 if expr.value else 0)
            self._push()
        elif isinstance(expr, A.VarRef):
            self.emit_op(Op.LOAD)
            self.emit_u16(expr.slot)  # type: ignore[attr-defined]
            self._push()
        elif isinstance(expr, A.UnaryExpr):
            self._gen_unary(expr)
        elif isinstance(expr, A.BinaryExpr):
            self._gen_binary(expr)
        elif isinstance(expr, A.CallExpr):
            self._gen_call(expr)

    def _gen_unary(self, expr: A.UnaryExpr) -> None:
        if expr.op == "-" and isinstance(expr.operand, A.IntLit) and expr.operand.value == 2147483648:
            self.emit_op(Op.PUSH_INT)
            self.emit_i32(-2147483648)
            self._push()
            return
        self.gen_expr(expr.operand)
        if expr.op == "-":
            self.emit_op(Op.NEG)
        elif expr.op == "!":
            self.emit_op(Op.NOT)
        # stack depth unchanged: pop 1, push 1

    _BINOP_MAP = {
        "+": Op.ADD, "-": Op.SUB, "*": Op.MUL, "/": Op.DIV, "%": Op.MOD,
        "&&": Op.AND, "||": Op.OR,
        "==": Op.EQ, "!=": Op.NE,
        "<": Op.LT, ">": Op.GT, "<=": Op.LE, ">=": Op.GE,
    }

    def _gen_binary(self, expr: A.BinaryExpr) -> None:
        self.gen_expr(expr.left)
        self.gen_expr(expr.right)
        self.emit_op(self._BINOP_MAP[expr.op])
        self._pop()  # two operands consumed, one result pushed → net -1

    def _gen_call(self, expr: A.CallExpr) -> None:
        for arg in expr.args:
            self.gen_expr(arg)
        func_idx = self._func_map[expr.name]
        self.emit_op(Op.CALL)
        self.emit_u16(func_idx)
        # CALL pops n args, pushes 1 return value → net -(n-1)
        self._pop(len(expr.args))
        self._push()

    def gen_stmt(self, stmt: A.Stmt) -> None:
        if isinstance(stmt, A.LetStmt):
            self._gen_let(stmt)
        elif isinstance(stmt, A.AssignStmt):
            self._gen_assign(stmt)
        elif isinstance(stmt, A.IfStmt):
            self._gen_if(stmt)
        elif isinstance(stmt, A.WhileStmt):
            self._gen_while(stmt)
        elif isinstance(stmt, A.ReturnStmt):
            self._gen_return(stmt)
        elif isinstance(stmt, A.PrintStmt):
            self._gen_print(stmt)
        elif isinstance(stmt, A.ExprStmt):
            self._gen_expr_stmt(stmt)
        elif isinstance(stmt, A.Block):
            for s in stmt.stmts:
                self.gen_stmt(s)

    def _gen_let(self, stmt: A.LetStmt) -> None:
        self.gen_expr(stmt.init)
        self.emit_op(Op.STORE)
        self.emit_u16(stmt.slot)  # type: ignore[attr-defined]
        self._pop()

    def _gen_assign(self, stmt: A.AssignStmt) -> None:
        self.gen_expr(stmt.value)
        # Look up slot via the semantic info on the VarRef we can reconstruct
        # Actually, AssignStmt doesn't get .slot from semantic — we need to
        # look it up.  But we don't have the symtab scope at codegen time.
        # We need to annotate AssignStmt.slot during semantic analysis.
        # For now, let's add that annotation.
        self.emit_op(Op.STORE)
        self.emit_u16(stmt.slot)  # type: ignore[attr-defined]
        self._pop()

    def _gen_if(self, stmt: A.IfStmt) -> None:
        # code(c), JMP_IF_FALSE L_else, T, JMP L_end, L_else: E, L_end:
        self.gen_expr(stmt.cond)
        if stmt.else_block is not None:
            l_else = self.new_label()
            self.emit_jump(Op.JMP_IF_FALSE, l_else)
            self._pop()  # JMP_IF_FALSE pops the bool
            for s in stmt.then_block.stmts:
                self.gen_stmt(s)
            then_returns = _always_returns(stmt.then_block.stmts)
            if not then_returns:
                l_end = self.new_label()
                self.emit_jump(Op.JMP, l_end)
            self.place_label(l_else)
            for s in stmt.else_block.stmts:
                self.gen_stmt(s)
            if not then_returns:
                self.place_label(l_end)
        else:
            l_end = self.new_label()
            self.emit_jump(Op.JMP_IF_FALSE, l_end)
            self._pop()  # JMP_IF_FALSE pops the bool
            for s in stmt.then_block.stmts:
                self.gen_stmt(s)
            self.place_label(l_end)

    def _gen_while(self, stmt: A.WhileStmt) -> None:
        # L_top: code(c), JMP_IF_FALSE L_end, B, JMP L_top, L_end:
        l_top = self.new_label()
        l_end = self.new_label()
        self.place_label(l_top)
        self.gen_expr(stmt.cond)
        self.emit_jump(Op.JMP_IF_FALSE, l_end)
        self._pop()  # JMP_IF_FALSE pops the bool
        for s in stmt.body.stmts:
            self.gen_stmt(s)
        self.emit_jump(Op.JMP, l_top)
        self.place_label(l_end)

    def _gen_return(self, stmt: A.ReturnStmt) -> None:
        assert stmt.value is not None
        self.gen_expr(stmt.value)
        self.emit_op(Op.RET)
        self._pop()  # RET consumes the return value

    def _gen_print(self, stmt: A.PrintStmt) -> None:
        self.gen_expr(stmt.value)
        self.emit_op(Op.PRINT)
        self._pop()

    def _gen_expr_stmt(self, stmt: A.ExprStmt) -> None:
        self.gen_expr(stmt.expr)
        self.emit_op(Op.POP)
        self._pop()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(prog: A.Program, st: SymbolTable) -> List[BCFunction]:
    """Compile a semantically-analyzed program to a list of BCFunction.

    The function list is ordered as they appear in the source.  The caller
    must determine ``entry_func`` (index of ``main``) for serialization.
    """
    # Build function-name → index map
    func_index: Dict[str, int] = {}
    for i, fn in enumerate(prog.functions):
        func_index[fn.name] = i

    result: List[BCFunction] = []
    for fn in prog.functions:
        builder = _FuncBuilder(func_index, st)
        for s in fn.body.stmts:
            builder.gen_stmt(s)
        code, max_stack = builder.finish()

        # Collect local types: parameters first, then remaining locals.
        # The semantic analyzer assigns slots 0..num_params-1 to params,
        # then num_params..num_locals-1 to let-bindings.
        num_locals = fn.num_locals  # type: ignore[attr-defined]
        local_types: List[str] = []
        for p in fn.params:
            local_types.append(p.type_name)
        # For non-parameter locals, we need to know their declared type.
        # We walk the AST to collect them in slot order.
        let_types = _collect_let_types(fn, len(fn.params))
        local_types.extend(let_types)

        result.append(BCFunction(
            name=fn.name,
            param_types=[p.type_name for p in fn.params],
            return_type=fn.return_type,
            num_locals=num_locals,
            local_types=local_types,
            max_stack=max_stack,
            code=code,
            jump_targets=builder.jump_targets,
        ))

    return result


def _collect_let_types(fn: A.Function, num_params: int) -> List[str]:
    """Walk the function body and return types for locals slots
    num_params..num_locals-1, in slot order."""
    num_locals = fn.num_locals  # type: ignore[attr-defined]
    types = [""] * (num_locals - num_params)

    def _walk_stmts(stmts: List[A.Stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, A.LetStmt):
                slot = stmt.slot  # type: ignore[attr-defined]
                types[slot - num_params] = stmt.type_name
            elif isinstance(stmt, A.IfStmt):
                _walk_stmts(stmt.then_block.stmts)
                if stmt.else_block is not None:
                    _walk_stmts(stmt.else_block.stmts)
            elif isinstance(stmt, A.WhileStmt):
                _walk_stmts(stmt.body.stmts)
            elif isinstance(stmt, A.Block):
                _walk_stmts(stmt.stmts)

    _walk_stmts(fn.body.stmts)
    return types
