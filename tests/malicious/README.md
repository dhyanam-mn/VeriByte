# Malicious Bytecode Test Suite

This directory contains crafted `.bc` bytecode files designed to test every static verifier rule.
Each file isolates and violates exactly one rule from `docs/VERIFIER_DESIGN.md`.

| File | Expected Rule | Description |
|---|---|---|
| `bad_call_1.bc` | `BAD_CALL` | CALL target function index 10 does not exist in function table |
| `bad_call_2.bc` | `BAD_CALL` | CALL passed argument of type int to function expecting bool |
| `bad_jump_1.bc` | `BAD_JUMP` | JMP target 100 exceeds code bounds |
| `bad_jump_2.bc` | `BAD_JUMP` | JMP target 2 jumps into the middle of PUSH_INT operand |
| `bad_opcode_1.bc` | `BAD_OPCODE` | Unknown opcode byte 0xEE |
| `bad_opcode_2.bc` | `BAD_OPCODE` | PUSH_BOOL with invalid operand 2 (must be 0 or 1) |
| `bad_return_1.bc` | `BAD_RETURN` | RET returned bool when function is declared to return int |
| `bad_return_2.bc` | `BAD_RETURN` | RET in helper returned int when helper is declared to return bool |
| `fallthrough_1.bc` | `FALLTHROUGH` | Code falls off the end of instruction stream without RET, JMP, or HALT |
| `fallthrough_2.bc` | `FALLTHROUGH` | JMP_IF_FALSE falls through past the end of the code stream |
| `local_range_1.bc` | `LOCAL_RANGE` | LOAD accessed local index 10 when num_locals=1 |
| `local_range_2.bc` | `LOCAL_RANGE` | STORE accessed local index 10 when num_locals=1 |
| `local_type_1.bc` | `LOCAL_TYPE` | STORE popped bool value into local 0 declared as int |
| `local_type_2.bc` | `LOCAL_TYPE` | STORE popped int value into local 0 declared as bool |
| `local_unset_1.bc` | `LOCAL_UNSET` | LOAD accessed local 0 before it was assigned (UNSET) |
| `local_unset_2.bc` | `LOCAL_UNSET` | LOAD accessed local 0 which is UNSET along the false branch |
| `merge_mismatch_1.bc` | `MERGE_MISMATCH` | Control flow join at RET has stack depth 1 from then-branch, depth 0 from else-branch |
| `merge_mismatch_2.bc` | `MERGE_MISMATCH` | Control flow join at RET has stack slot 0 type int from then-branch, bool from else-branch |
| `stack_overflow_1.bc` | `STACK_OVERFLOW` | Second PUSH_INT causes stack depth 2 to exceed declared max_stack=1 |
| `stack_overflow_2.bc` | `STACK_OVERFLOW` | Second DUP causes stack depth 3 to exceed declared max_stack=2 |
| `stack_type_1.bc` | `STACK_TYPE` | ADD executed with bool and int operands (expects [int, int]) |
| `stack_type_2.bc` | `STACK_TYPE` | AND executed with int operands (expects [bool, bool]) |
| `stack_underflow_1.bc` | `STACK_UNDERFLOW` | POP executed on empty operand stack |
| `stack_underflow_2.bc` | `STACK_UNDERFLOW` | ADD requires 2 stack operands, but only 1 is present |
| `truncated_1.bc` | `TRUNCATED` | PUSH_INT instruction truncated (needs 4 operand bytes, has 2) |
| `truncated_2.bc` | `TRUNCATED` | STORE instruction truncated (needs 2 operand bytes, has 1) |
