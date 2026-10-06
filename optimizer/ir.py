"""Intermediate representation for bytecode optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Set

from codegen.opcodes import Op


@dataclass
class Label:
    """Symbolic jump target label."""
    id: int

    def __repr__(self) -> str:
        return f"L{self.id}"


@dataclass
class IRInstr:
    """An instruction in the optimizer IR."""
    op: Op
    operand: Any = None
    labels: Set[int] = field(default_factory=set)

    def __repr__(self) -> str:
        lbl_str = f"[{','.join(f'L{lbl}' for lbl in sorted(self.labels))}] " if self.labels else ""
        op_str = f" {self.operand}" if self.operand is not None else ""
        return f"{lbl_str}{self.op.name}{op_str}"
