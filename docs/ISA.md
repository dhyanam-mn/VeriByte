# Bytecode Instruction Set (v1)

Stack machine. Values are `int` (32-bit signed) or `bool`. Each function has
its own code, its own locals (parameters occupy locals `0..n-1`) and its own
operand stack. Notation: stack effect `[before] -> [after]`, top of stack on
the right. `T` means "any single type".

## Opcode table

| Hex | Mnemonic | Operand | Stack effect | Verifier requirement |
|---|---|---|---|---|
| 01 | PUSH_INT | i32 | `[] -> [int]` | depth < max_stack |
| 02 | PUSH_BOOL | u8 (0/1) | `[] -> [bool]` | operand is 0 or 1 |
| 03 | POP | - | `[T] -> []` | depth >= 1 |
| 04 | DUP | - | `[T] -> [T, T]` | depth >= 1, room for one more |
| 10 | ADD | - | `[int, int] -> [int]` | both int |
| 11 | SUB | - | `[int, int] -> [int]` | both int |
| 12 | MUL | - | `[int, int] -> [int]` | both int |
| 13 | DIV | - | `[int, int] -> [int]` | both int (runtime: divide by zero traps) |
| 14 | MOD | - | `[int, int] -> [int]` | both int (runtime: divide by zero traps) |
| 15 | NEG | - | `[int] -> [int]` | top is int |
| 20 | AND | - | `[bool, bool] -> [bool]` | both bool |
| 21 | OR | - | `[bool, bool] -> [bool]` | both bool |
| 22 | NOT | - | `[bool] -> [bool]` | top is bool |
| 30 | EQ | - | `[T, T] -> [bool]` | same type, int or bool |
| 31 | NE | - | `[T, T] -> [bool]` | same type, int or bool |
| 32 | LT | - | `[int, int] -> [bool]` | both int |
| 33 | GT | - | `[int, int] -> [bool]` | both int |
| 34 | LE | - | `[int, int] -> [bool]` | both int |
| 35 | GE | - | `[int, int] -> [bool]` | both int |
| 40 | LOAD | u16 local | `[] -> [type of local]` | index < num_locals; local definitely assigned |
| 41 | STORE | u16 local | `[T] -> []` | index < num_locals; type matches local's declared type |
| 50 | JMP | u16 target | no change | target is a valid instruction start in this function |
| 51 | JMP_IF_FALSE | u16 target | `[bool] -> []` | top is bool; valid target; falls through otherwise |
| 60 | CALL | u16 func | `[a1..an] -> [ret]` | func exists; argument types match the callee signature |
| 61 | RET | - | `[ret] -> (end)` | top matches function return type; no further successor |
| 70 | PRINT | - | `[T] -> []` | depth >= 1 |
| FF | HALT | - | `(end)` | terminates the program |

Jump targets are absolute byte offsets from the start of the function's code.
All multi-byte operands are little-endian.

## Binary file format (.bc)

```
header:
  magic       4 bytes   "SBVM"
  version     u8        1
  num_funcs   u16
  entry_func  u16       index of main
per function (repeated num_funcs times):
  name_len    u8
  name        name_len bytes (ASCII)
  num_params  u8
  param_types num_params bytes   (0 = int, 1 = bool)
  return_type u8                 (0 = int, 1 = bool)
  num_locals  u16                (includes parameters)
  local_types num_locals bytes   (declared types; parameters first)
  max_stack   u16                (declared operand-stack bound)
  code_len    u32
  code        code_len bytes
```

Because `max_stack`, local types and signatures are declared in the file, the
verifier can check them without trusting the compiler. A malicious file may
lie about any of them, which is exactly what the verifier must catch.

## Compilation scheme (preview for Review 2)

| Source | Bytecode |
|---|---|
| `a + b` | code(a), code(b), ADD |
| `a && b` | code(a), code(b), AND (non-short-circuit in v1) |
| `x = e;` | code(e), STORE x |
| `if (c) T else E` | code(c), JMP_IF_FALSE L_else, T, JMP L_end, L_else: E, L_end: |
| `while (c) B` | L_top: code(c), JMP_IF_FALSE L_end, B, JMP L_top, L_end: |
| `f(a, b)` | code(a), code(b), CALL f |
| `return e;` | code(e), RET |
