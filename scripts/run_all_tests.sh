#!/bin/bash
set -e

echo "=================================================="
echo "    WineHackathon Modular Monorepo Test Suite     "
echo "=================================================="

FAILED=0

run_service_test() {
    local service_dir=$1
    local python_path=$2
    local test_path=$3

    echo ""
    echo ">>> Running tests for: $service_dir"
    echo "--------------------------------------------------"
    if PYTHONPATH="$python_path" pytest "$test_path" -v; then
        echo " [PASS] $service_dir"
    else
        echo " [FAIL] $service_dir"
        FAILED=1
    fi
}

# 1. Application Layer (Database, Repositories, Models, Taste Matrix, DTOs)
run_service_test "application" "." "application/tests"

# 2. Unified Backend Gateway (FastAPI, 5-scan limit, /v1/eval/predict)
run_service_test "backend" "." "backend/tests"

# 3. Dedicated Sommelier Service (Onboarding, 4D Taste Matrix, WebSockets)
run_service_test "sommelier" "." "sommelier/tests"

# 4. Dedicated ML Service (Vector Index, HMAC verification, Feature Extractor)
run_service_test "ml" "." "ml/tests"

echo ""
echo "=================================================="
if [ $FAILED -eq 0 ]; then
    echo " ALL MODULAR MONOREPO TEST SUITES PASSED! [100%]"
    echo "=================================================="
    exit 0
else
    echo " SOME TESTS FAILED!"
    echo "=================================================="
    exit 1
fi
