from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class Node:
    line: int
    col: int


# ---- expressions ----
@dataclass
class IntLit(Node):
    value: int

@dataclass
class BoolLit(Node):
    value: bool

@dataclass
class VarRef(Node):
    name: str

@dataclass
class UnaryExpr(Node):
    op: str
    operand: "Expr"

@dataclass
class BinaryExpr(Node):
    op: str
    left: "Expr"
    right: "Expr"

@dataclass
class CallExpr(Node):
    name: str
    args: List["Expr"]

Expr = Union[IntLit, BoolLit, VarRef, UnaryExpr, BinaryExpr, CallExpr]


# ---- statements ----
@dataclass
class LetStmt(Node):
    name: str
    type_name: str
    init: Expr

@dataclass
class AssignStmt(Node):
    name: str
    value: Expr

@dataclass
class IfStmt(Node):
    cond: Expr
    then_block: "Block"
    else_block: Optional["Block"]

@dataclass
class WhileStmt(Node):
    cond: Expr
    body: "Block"

@dataclass
class ReturnStmt(Node):
    value: Optional[Expr]

@dataclass
class PrintStmt(Node):
    value: Expr

@dataclass
class ExprStmt(Node):
    expr: Expr

@dataclass
class Block(Node):
    stmts: List["Stmt"] = field(default_factory=list)

Stmt = Union[LetStmt, AssignStmt, IfStmt, WhileStmt, ReturnStmt, PrintStmt, ExprStmt, Block]


# ---- top level ----
@dataclass
class Param(Node):
    name: str
    type_name: str

@dataclass
class Function(Node):
    name: str
    params: List[Param]
    return_type: str
    body: Block

@dataclass
class Program(Node):
    functions: List[Function]
