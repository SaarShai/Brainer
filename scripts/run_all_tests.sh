#!/bin/bash
set -e

echo "Running tests..."

python3 -m unittest discover -s tests -p 'test_*.py'

SEMDIFF_DEPS="$PWD/.token-economy/deps"
if [ -d "$SEMDIFF_DEPS" ]; then
    SEMDIFF_PYTHONPATH="$SEMDIFF_DEPS:$PWD/projects/semdiff"
else
    SEMDIFF_PYTHONPATH="$PWD/projects/semdiff"
fi

if PYTHONPATH="$SEMDIFF_PYTHONPATH" python3 -c "import tree_sitter_languages" >/dev/null 2>&1; then
    for test_file in projects/semdiff/tests/test_*.py; do
        echo "Running $test_file..."
        PYTHONPATH="$SEMDIFF_PYTHONPATH" python3 "$test_file" >/tmp/token-economy-test.log
    done
else
    echo "Skipping semdiff tests: tree-sitter-languages not installed (run stable/INSTALL.sh or pip install --target .token-economy/deps 'tree-sitter<0.22' tree-sitter-languages)."
fi

echo "All tests passed."
exit 0
