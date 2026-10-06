"""Bytecode Optimizer: constant folding, peephole optimizations, and dead code elimination."""

from __future__ import annotations

import struct
from typing import Dict, List, Set, Tuple

from codegen.generator import BCFunction
from codegen.opcodes import OPERAND_SIZE, Op
from codegen.serializer import BCModule
from verifier.decoder import decode_function
from vm.interpreter import idiv, imod, to_i32
from .ir import IRInstr, Label


def lift_to_ir(fn: BCFunction) -> Tuple[List[IRInstr], Label]:
    """Decode function bytecode into an IR instruction list with symbolic jump labels."""
    instructions, _ = decode_function(fn)

    # Identify jump targets
    jump_targets: Set[int] = set()
    for inst in instructions:
        if inst.op in (Op.JMP, Op.JMP_IF_FALSE):
            jump_targets.add(inst.operand)

    # Create Label mapping: offset -> label_id
    label_map: Dict[int, int] = {}
    next_label_id = 0
    for target in sorted(jump_targets):
        label_map[target] = next_label_id
        next_label_id += 1

    end_label = Label(next_label_id)

    ir_list: List[IRInstr] = []
    for inst in instructions:
        labels: Set[int] = set()
        if inst.offset in label_map:
            labels.add(label_map[inst.offset])

        operand = inst.operand
        if inst.op in (Op.JMP, Op.JMP_IF_FALSE):
            target_offset = inst.operand
            if target_offset in label_map:
                operand = Label(label_map[target_offset])
            elif target_offset == len(fn.code):
                operand = end_label

        ir_list.append(IRInstr(op=inst.op, operand=operand, labels=labels))

    return ir_list, end_label


def peephole_pass(ir: List[IRInstr]) -> bool:
    """Run a single pass of peephole optimizations. Return True if any change occurred."""
    changed = False
    i = 0

    while i < len(ir):
        # 1. PUSH, PUSH, BINOP Constant Folding (requires length >= 3)
        if i + 2 < len(ir):
            i0, i1, i2 = ir[i], ir[i + 1], ir[i + 2]
            # Must not have jump targets into i1 or i2
            if not i1.labels and not i2.labels:
                # Integer binary arithmetic / relational folding
                if i0.op == Op.PUSH_INT and i1.op == Op.PUSH_INT:
                    c1: int = i0.operand
                    c2: int = i1.operand
                    folded = None

                    if i2.op == Op.ADD:
                        folded = IRInstr(Op.PUSH_INT, to_i32(c1 + c2), labels=i0.labels)
                    elif i2.op == Op.SUB:
                        folded = IRInstr(Op.PUSH_INT, to_i32(c1 - c2), labels=i0.labels)
                    elif i2.op == Op.MUL:
                        folded = IRInstr(Op.PUSH_INT, to_i32(c1 * c2), labels=i0.labels)
                    elif i2.op == Op.DIV and c2 != 0:
                        folded = IRInstr(Op.PUSH_INT, idiv(c1, c2), labels=i0.labels)
                    elif i2.op == Op.MOD and c2 != 0:
                        folded = IRInstr(Op.PUSH_INT, imod(c1, c2), labels=i0.labels)
                    elif i2.op == Op.LT:
                        folded = IRInstr(Op.PUSH_BOOL, c1 < c2, labels=i0.labels)
                    elif i2.op == Op.GT:
                        folded = IRInstr(Op.PUSH_BOOL, c1 > c2, labels=i0.labels)
                    elif i2.op == Op.LE:
                        folded = IRInstr(Op.PUSH_BOOL, c1 <= c2, labels=i0.labels)
                    elif i2.op == Op.GE:
                        folded = IRInstr(Op.PUSH_BOOL, c1 >= c2, labels=i0.labels)
                    elif i2.op == Op.EQ:
                        folded = IRInstr(Op.PUSH_BOOL, c1 == c2, labels=i0.labels)
                    elif i2.op == Op.NE:
                        folded = IRInstr(Op.PUSH_BOOL, c1 != c2, labels=i0.labels)

                    if folded is not None:
                        ir[i:i + 3] = [folded]
                        changed = True
                        continue

                # Boolean binary logical / equality folding
                elif i0.op == Op.PUSH_BOOL and i1.op == Op.PUSH_BOOL:
                    b1: bool = i0.operand
                    b2: bool = i1.operand
                    folded = None

                    if i2.op == Op.AND:
                        folded = IRInstr(Op.PUSH_BOOL, b1 and b2, labels=i0.labels)
                    elif i2.op == Op.OR:
                        folded = IRInstr(Op.PUSH_BOOL, b1 or b2, labels=i0.labels)
                    elif i2.op == Op.EQ:
                        folded = IRInstr(Op.PUSH_BOOL, b1 == b2, labels=i0.labels)
                    elif i2.op == Op.NE:
                        folded = IRInstr(Op.PUSH_BOOL, b1 != b2, labels=i0.labels)

                    if folded is not None:
                        ir[i:i + 3] = [folded]
                        changed = True
                        continue

        # 2. PUSH, UNARY Constant Folding (requires length >= 2)
        if i + 1 < len(ir):
            i0, i1 = ir[i], ir[i + 1]
            if not i1.labels:
                if i0.op == Op.PUSH_INT and i1.op == Op.NEG:
                    folded = IRInstr(Op.PUSH_INT, to_i32(-i0.operand), labels=i0.labels)
                    ir[i:i + 2] = [folded]
                    changed = True
                    continue
                elif i0.op == Op.PUSH_BOOL and i1.op == Op.NOT:
                    folded = IRInstr(Op.PUSH_BOOL, not i0.operand, labels=i0.labels)
                    ir[i:i + 2] = [folded]
                    changed = True
                    continue

        # 3. NOT NOT Elimination
        if i + 1 < len(ir):
            i0, i1 = ir[i], ir[i + 1]
            if i0.op == Op.NOT and i1.op == Op.NOT and not i1.labels:
                if i + 2 < len(ir):
                    ir[i + 2].labels.update(i0.labels)
                del ir[i:i + 2]
                changed = True
                continue

        # 4. PUSH then POP Elimination
        if i + 1 < len(ir):
            i0, i1 = ir[i], ir[i + 1]
            if i0.op in (Op.PUSH_INT, Op.PUSH_BOOL) and i1.op == Op.POP and not i1.labels:
                if i + 2 < len(ir):
                    ir[i + 2].labels.update(i0.labels)
                del ir[i:i + 2]
                changed = True
                continue

        # 5. Redundant Jump to Next Instruction
        if i + 1 < len(ir):
            i0, i1 = ir[i], ir[i + 1]
            if i0.op == Op.JMP and isinstance(i0.operand, Label):
                if i0.operand.id in i1.labels:
                    # Jumping to the next instruction: redundant!
                    i1.labels.update(i0.labels)
                    del ir[i]
                    changed = True
                    continue

        i += 1

    return changed


def jump_threading_pass(ir: List[IRInstr]) -> bool:
    """Thread jumps: if a jump targets another unconditional jump, redirect directly."""
    # Build label -> instruction index map
    label_to_index: Dict[int, int] = {}
    for idx, inst in enumerate(ir):
        for lbl_id in inst.labels:
            label_to_index[lbl_id] = idx

    changed = False
    for inst in ir:
        if inst.op in (Op.JMP, Op.JMP_IF_FALSE) and isinstance(inst.operand, Label):
            target_lbl = inst.operand.id
            if target_lbl in label_to_index:
                target_idx = label_to_index[target_lbl]
                target_inst = ir[target_idx]
                if target_inst.op == Op.JMP and isinstance(target_inst.operand, Label):
                    # Avoid infinite loop on self-loop jump
                    if target_inst.operand.id != target_lbl:
                        inst.operand = target_inst.operand
                        changed = True

    return changed


def eliminate_unreachable_code(ir: List[IRInstr]) -> bool:
    """Remove dead code following unconditional jumps/returns up to the next label."""
    changed = False
    i = 0
    while i < len(ir):
        if ir[i].op in (Op.RET, Op.HALT, Op.JMP):
            # Delete subsequent instructions until we encounter a labelled instruction
            del_idx = i + 1
            while del_idx < len(ir) and not ir[del_idx].labels:
                del ir[del_idx]
                changed = True
        i += 1
    return changed


def reassemble(ir: List[IRInstr], end_label: Label) -> bytes:
    """Compile IR instructions back to raw bytecode bytes with recomputed jump offsets."""
    # Pass 1: compute byte offsets for each instruction
    label_offsets: Dict[int, int] = {}
    pc = 0

    for inst in ir:
        for lbl_id in inst.labels:
            label_offsets[lbl_id] = pc
        op = inst.op
        operand_size = OPERAND_SIZE[op]
        pc += 1 + operand_size

    # The end_label targets the byte right after the last instruction
    label_offsets[end_label.id] = pc

    # Pass 2: emit bytecode with resolved jump targets
    buf = bytearray()
    for inst in ir:
        op = inst.op
        buf.append(op.value)
        operand_size = OPERAND_SIZE[op]

        if operand_size == 0:
            continue
        elif operand_size == 1:
            val = 1 if inst.operand else 0
            buf.append(val & 0xFF)
        elif operand_size == 2:
            if isinstance(inst.operand, Label):
                target_offset = label_offsets[inst.operand.id]
                buf.extend(struct.pack("<H", target_offset))
            else:
                buf.extend(struct.pack("<H", inst.operand))
        elif operand_size == 4:
            buf.extend(struct.pack("<i", inst.operand))

    return bytes(buf)


def compute_peak_stack(code: bytes) -> int:
    """Simulate abstract stack depth on the decoded bytecode to find true max_stack."""
    if not code:
        return 1
    instructions, _ = decode_function_raw(code)
    instr_map = {inst.offset: inst for inst in instructions}

    depths: Dict[int, int] = {0: 0}
    worklist: List[int] = [0]
    peak = 0

    while worklist:
        pc = worklist.pop(0)
        depth = depths[pc]
        inst = instr_map[pc]
        op = inst.op

        # Track peak at this instruction
        current_peak = depth
        delta = 0

        if op in (Op.PUSH_INT, Op.PUSH_BOOL):
            delta = 1
            current_peak = depth + 1
        elif op == Op.POP:
            delta = -1
        elif op == Op.DUP:
            delta = 1
            current_peak = depth + 1
        elif op in (Op.ADD, Op.SUB, Op.MUL, Op.DIV, Op.MOD, Op.AND, Op.OR,
                     Op.EQ, Op.NE, Op.LT, Op.GT, Op.LE, Op.GE):
            delta = -1
        elif op in (Op.NEG, Op.NOT):
            delta = 0
        elif op == Op.LOAD:
            delta = 1
            current_peak = depth + 1
        elif op == Op.STORE:
            delta = -1
        elif op == Op.JMP:
            delta = 0
        elif op == Op.JMP_IF_FALSE:
            delta = -1
        elif op == Op.CALL:
            # CALL pops N args, pushes 1
            delta = 1  # worst case conservative estimate
            current_peak = depth + 1
        elif op in (Op.RET, Op.PRINT):
            delta = -1
        elif op == Op.HALT:
            delta = 0

        peak = max(peak, current_peak)
        next_depth = max(0, depth + delta)

        # Successors
        succs: List[int] = []
        if op == Op.JMP:
            succs.append(inst.operand)
        elif op == Op.JMP_IF_FALSE:
            succs.append(inst.offset + inst.size)
            succs.append(inst.operand)
        elif op in (Op.RET, Op.HALT):
            succs = []
        else:
            succs.append(inst.offset + inst.size)

        for s in succs:
            if s < len(code) and s in instr_map and s not in depths:
                depths[s] = next_depth
                worklist.append(s)

    return max(1, peak)


def decode_function_raw(code: bytes):
    """Simple raw decoder for stack tracking."""
    from verifier.decoder import Instruction
    instructions = []
    valid_starts = set()
    pc = 0
    while pc < len(code):
        op = Op(code[pc])
        sz = OPERAND_SIZE[op]
        operand = None
        if sz == 1:
            operand = code[pc + 1]
        elif sz == 2:
            operand = struct.unpack_from("<H", code, pc + 1)[0]
        elif sz == 4:
            operand = struct.unpack_from("<i", code, pc + 1)[0]
        inst = Instruction(offset=pc, op=op, operand=operand, size=1 + sz)
        instructions.append(inst)
        valid_starts.add(pc)
        pc += 1 + sz
    return instructions, valid_starts


def optimize_function(fn: BCFunction) -> BCFunction:
    """Optimize a single BCFunction through iterative peephole and constant folding passes."""
    if not fn.code:
        return fn

    ir, end_label = lift_to_ir(fn)

    # Iterative optimization loop
    iterations = 0
    max_iterations = 20
    while iterations < max_iterations:
        c1 = peephole_pass(ir)
        c2 = jump_threading_pass(ir)
        c3 = eliminate_unreachable_code(ir)
        if not (c1 or c2 or c3):
            break
        iterations += 1

    optimized_code = reassemble(ir, end_label)
    new_max_stack = min(fn.max_stack, compute_peak_stack(optimized_code))

    return BCFunction(
        name=fn.name,
        param_types=list(fn.param_types),
        return_type=fn.return_type,
        num_locals=fn.num_locals,
        local_types=list(fn.local_types),
        max_stack=new_max_stack,
        code=optimized_code,
    )


def optimize_module(module: BCModule) -> BCModule:
    """Optimize all functions in a BCModule."""
    optimized_funcs = [optimize_function(fn) for fn in module.functions]
    return BCModule(
        version=module.version,
        entry_func=module.entry_func,
        functions=optimized_funcs,
    )
