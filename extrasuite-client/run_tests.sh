#!/bin/bash
# Usage: ./run_tests.sh [scenario] [server]
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

SERVER="${2:-http://localhost:8001}"
python3 -c "import certifi" 2>/dev/null || pip3 install -q certifi

export PYTHONPATH="$PWD/src"
if [ -n "$1" ]; then
    exec python3 tests/manual_auth_flow_test.py --server "$SERVER" --scenario "$1"
else
    exec python3 tests/manual_auth_flow_test.py --server "$SERVER"
fi
