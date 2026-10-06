"""Abstract interpreter state representation and lattice merge operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .errors import VerifyError

UNSET = "UNSET"
CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class State:
    """Abstract state at a program point."""
    stack: Tuple[str, ...]
    locals: Tuple[str, ...]

    def __repr__(self) -> str:
        return f"State(stack={list(self.stack)}, locals={list(self.locals)})"


def merge_states(s1: State, s2: State, func_name: str, offset: int, mnemonic: str) -> State:
    """Merge abstract state s2 into s1 at a join point.

    Raises VerifyError(rule='MERGE_MISMATCH') if stack depths or slot types disagree.
    Locals that are UNSET on either path remain UNSET.
    """
    if len(s1.stack) != len(s2.stack):
        raise VerifyError(
            func_name=func_name,
            offset=offset,
            mnemonic=mnemonic,
            rule="MERGE_MISMATCH",
            expected=f"stack depth {len(s1.stack)}",
            actual=f"stack depth {len(s2.stack)}",
        )

    merged_stack = []
    for i, (t1, t2) in enumerate(zip(s1.stack, s2.stack)):
        if t1 != t2:
            raise VerifyError(
                func_name=func_name,
                offset=offset,
                mnemonic=mnemonic,
                rule="MERGE_MISMATCH",
                expected=f"stack slot {i} type '{t1}'",
                actual=f"stack slot {i} type '{t2}'",
            )
        merged_stack.append(t1)

    merged_locals = []
    for l1, l2 in zip(s1.locals, s2.locals):
        if l1 == UNSET or l2 == UNSET:
            merged_locals.append(UNSET)
        elif l1 == l2:
            merged_locals.append(l1)
        else:
            merged_locals.append(CONFLICT)

    return State(
        stack=tuple(merged_stack),
        locals=tuple(merged_locals),
    )
