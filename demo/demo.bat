@echo off
rem Demonstration of SVM Verifier preventing runtime failures.
rem Shows:
rem 1. Running an unverified malicious file with --unsafe crashes the VM interpreter.
rem 2. Running with verification enabled cleanly catches the violation with diagnostics.

set MALICIOUS_FILE=tests\malicious\stack_underflow_1.bc

echo =================================================================
echo DEMO: Secure Bytecode VM - Static Verifier Demonstration
echo Target: %MALICIOUS_FILE%
echo =================================================================
echo.

echo ^>^>^> Step 1: Run with --unsafe (skipping verification)...
echo Command: python svm.py run --unsafe %MALICIOUS_FILE%
python svm.py run --unsafe %MALICIOUS_FILE%
echo [Notice: VM crashed with unhandled exception!]
echo.

echo ^>^>^> Step 2: Run with verification enabled...
echo Command: python svm.py run %MALICIOUS_FILE%
python svm.py run %MALICIOUS_FILE%
echo [Notice: Cleanly rejected before VM execution!]
echo.

echo ^>^>^> Step 3: Run standalone verifier check...
echo Command: python svm.py verify %MALICIOUS_FILE%
python svm.py verify %MALICIOUS_FILE%
echo.

echo =================================================================
echo DEMO COMPLETE: Verifier successfully prevented unsafe execution.
echo =================================================================
