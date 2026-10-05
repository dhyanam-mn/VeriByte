# Verifier Design (paper design for Review 1; implementation in Review 3)

## Goal

Accept a bytecode file only if every reachable VM state is provably safe in the
categories below. The verifier never executes the program.

## Abstract domain

Types: `int`, `bool`, plus `UNSET` (local not yet assigned) and `CONFLICT`
(merge of incompatible types, unusable).

Abstract state at instruction `pc`:

```
State = ( stack: list[Type], locals: list[Type or UNSET] )
```

## Algorithm (per function)

1. **Decode**: walk the code from offset 0, reading opcode and operand.
   Reject unknown opcodes and truncated operands. Record the set of valid
   instruction start offsets.
2. **Target check**: for every JMP / JMP_IF_FALSE, the target must be in the
   valid start set.
3. **Worklist dataflow**:
   - entry state: stack empty, parameters typed, other locals `UNSET`;
   - pop a pc from the worklist, apply the opcode's transfer function to the
     state (checking its preconditions), and for each successor merge the new
     state into the successor's stored state;
   - if the stored state changed, add the successor to the worklist;
   - stop at a fixed point (the lattice is finite, so this terminates).
4. **Merge rule** at a join point: stack depths must be equal; each stack slot
   must have the same type; a local that is `UNSET` on any incoming path
   becomes `UNSET` (so a later LOAD is rejected).
5. **Final checks**: execution may not fall off the end of the code (the last
   reachable instruction must be JMP, RET or HALT); `max_stack` is never
   exceeded; RET type equals the declared return type.

## Error report format

```
verify error in function 'f' at offset 17 (JMP_IF_FALSE):
  rule: STACK_TYPE
  expected stack top: bool
  actual abstract stack: [int]
```

## Properties and the rule names used in diagnostics

| Rule | Problem (report P#) | Meaning |
|---|---|---|
| BAD_OPCODE / TRUNCATED | P7 | undecodable instruction stream |
| BAD_JUMP | P2 | target outside code or not an instruction start |
| STACK_UNDERFLOW | P1 | pop with too few values |
| STACK_OVERFLOW | P1 | depth exceeds declared max_stack |
| STACK_TYPE | P3 | operand has the wrong type |
| MERGE_MISMATCH | P4 | different stack shapes meet at a join |
| LOCAL_RANGE / LOCAL_TYPE / LOCAL_UNSET | P5 | bad index, wrong type, or read before write |
| BAD_CALL | P6 | unknown callee or argument mismatch |
| BAD_RETURN / FALLTHROUGH | P6, P7 | wrong return type, or code can run off the end |

## Informal soundness argument

Claim: if the verifier accepts a function, then at every reachable `pc` the
concrete VM stack and locals are described by the abstract state stored for
that `pc`. Proof sketch by induction on execution steps: the entry state
matches by construction; each transfer function over-approximates its
instruction; each merge is a safe upper bound of its inputs. Hence none of the
checked preconditions can fail at runtime. (Division by zero is a runtime trap
and is deliberately outside the verifier's guarantees, the same way the JVM
treats `ArithmeticException`.)
