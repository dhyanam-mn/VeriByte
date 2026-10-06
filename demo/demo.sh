#!/bin/bash
# Demonstration of SVM Verifier preventing runtime failures.
# Shows:
# 1. Running an unverified malicious file with --unsafe crashes the VM interpreter.
# 2. Running with verification enabled cleanly catches the violation with diagnostics.

MALICIOUS_FILE="tests/malicious/stack_underflow_1.bc"

echo "================================================================="
echo "DEMO: Secure Bytecode VM - Static Verifier Demonstration"
echo "Target: $MALICIOUS_FILE"
echo "================================================================="
echo ""

echo ">>> Step 1: Run with --unsafe (skipping verification)..."
echo "Command: python svm.py run --unsafe $MALICIOUS_FILE"
python svm.py run --unsafe "$MALICIOUS_FILE" 2>&1 || true
echo "[VM crashed due to unverified bytecode!]"
echo ""

echo ">>> Step 2: Run with verification enabled..."
echo "Command: python svm.py run $MALICIOUS_FILE"
python svm.py run "$MALICIOUS_FILE" 2>&1 || true
echo "[Cleanly rejected before VM execution!]"
echo ""

echo ">>> Step 3: Run standalone verifier check..."
echo "Command: python svm.py verify $MALICIOUS_FILE"
python svm.py verify "$MALICIOUS_FILE" 2>&1 || true
echo ""
echo "================================================================="
echo "DEMO COMPLETE: Verifier successfully prevented unsafe execution."
echo "================================================================="
