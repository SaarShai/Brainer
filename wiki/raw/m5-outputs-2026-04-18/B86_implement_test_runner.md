---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```bash
#!/bin/bash
set -e

# Set up variables for tracking test results
total_tests=0
passed_tests=0
failed_tests=0

echo "Running tests..."

# Run all test files in the tests directory
for test_file in tests/*.py tests/test_*.py; do
    if [ ! -f "$test_file" ]; then
        continue
    fi
    
    echo "Running $test_file..."
    pytest -v "$test_file" > "${test_file}.log" 2>&1
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        passed_tests=$((passed_tests + 1))
        echo "Passed: $test_file"
    else
        failed_tests=$((failed_tests + 1))
        echo "Failed: $test_file (See ${test_file}.log for details)"
    fi
    
    total_tests=$((total_tests + 1))
done

# Output test summary
echo -e "\nTest Summary:"
echo "Total tests run: $total_tests"
echo "Passed: $passed_tests"
echo "Failed: $failed_tests"

if [ $failed_tests -gt 0 ]; then
    echo "Some tests failed. Check log files for details."
    exit 1
fi

exit 0
```
