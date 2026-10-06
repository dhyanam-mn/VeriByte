"""Symbol table with nested block scopes and a function table.

Design:
- FuncSig stores a function's parameter types and return type.
- Scope is a linked list of scopes (each scope has a parent). Lookup walks up.
- SymbolTable wraps the function table and a scope stack.
  It assigns a unique local *slot* to every variable (parameters first, then
  each `let` in order).  A name re-declared in an inner block gets a new slot,
  which is what the code generator needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class FuncSig:
    """Signature of a declared function."""
    param_types: List[str]       # ["int", "bool", ...]
    return_type: str             # "int" | "bool"
    line: int                    # source position of `func` keyword
    col: int


@dataclass
class VarInfo:
    """Info about a declared variable (parameter or let-bound)."""
    type: str       # "int" | "bool"
    slot: int       # local index for codegen
    line: int       # declaration site
    col: int


class Scope:
    """A single lexical scope.  Maps names to VarInfo."""

    def __init__(self, parent: Optional[Scope] = None) -> None:
        self.parent = parent
        self._vars: Dict[str, VarInfo] = {}

    def define(self, name: str, info: VarInfo) -> None:
        self._vars[name] = info

    def has_local(self, name: str) -> bool:
        """Check if *this* scope (not parent) has `name`."""
        return name in self._vars

    def lookup(self, name: str) -> Optional[VarInfo]:
        """Resolve `name` walking up the scope chain."""
        if name in self._vars:
            return self._vars[name]
        if self.parent is not None:
            return self.parent.lookup(name)
        return None


class SymbolTable:
    """Manages the function table and a per-function scope stack.

    Usage:
        st = SymbolTable()
        st.register_function(...)       # for every function (first pass)
        st.enter_function(func_node)    # sets up param locals + scope
        st.enter_scope()                # on `{`
        st.declare_variable(...)        # for `let`
        st.lookup_variable(name)        # returns VarInfo or None
        st.exit_scope()                 # on `}`
        st.exit_function()
    """

    def __init__(self) -> None:
        self.functions: Dict[str, FuncSig] = {}
        self._scope: Optional[Scope] = None
        self._next_slot: int = 0
        # After analysis, each function name -> { var_name -> slot } for locals
        # (only the latest mapping; codegen uses slot numbers)
        self.func_locals: Dict[str, int] = {}  # func_name -> num_locals

    # ---- function table ----
    def register_function(self, name: str, sig: FuncSig) -> None:
        self.functions[name] = sig

    def lookup_function(self, name: str) -> Optional[FuncSig]:
        return self.functions.get(name)

    # ---- scope management ----
    def enter_function(self) -> None:
        """Open a fresh scope stack for a function body."""
        self._scope = Scope()
        self._next_slot = 0

    def exit_function(self, func_name: str) -> None:
        """Close the function scope and record num_locals."""
        self.func_locals[func_name] = self._next_slot
        self._scope = None

    def enter_scope(self) -> None:
        self._scope = Scope(parent=self._scope)

    def exit_scope(self) -> None:
        assert self._scope is not None
        self._scope = self._scope.parent

    def declare_variable(self, name: str, ty: str, line: int, col: int) -> VarInfo:
        """Add a variable to the current scope, assigning it the next slot."""
        info = VarInfo(type=ty, slot=self._next_slot, line=line, col=col)
        assert self._scope is not None
        self._scope.define(name, info)
        self._next_slot += 1
        return info

    def has_in_current_scope(self, name: str) -> bool:
        """True if `name` is declared in the *innermost* scope (for dup checks)."""
        assert self._scope is not None
        return self._scope.has_local(name)

    def lookup_variable(self, name: str) -> Optional[VarInfo]:
        if self._scope is None:
            return None
        return self._scope.lookup(name)
