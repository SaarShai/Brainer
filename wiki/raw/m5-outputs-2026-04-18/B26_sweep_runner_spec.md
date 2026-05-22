---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round7]
---

```python
import json
from collections import defaultdict
import numpy as np
from scipy.stats import norm

# Load results from JSON files
results = []
for file in glob.glob("adversarial_*.json"):
    with open(file) as f:
        data = json.load(f)
        results.extend(data)

# Aggregate per-category stats
category_stats = defaultdict(lambda: {"pass": 0, "fail": 0})
overall_pass = 0
overall_fail = 0

for result in results:
    category = result["category"]
    if result["status"] == "pass":
        category_stats[category]["pass"] += 1
        overall_pass += 1
    else:
        category_stats[category]["fail"] += 1
        overall_fail += 1

# Calculate pass rates and confidence intervals
total_tests = overall_pass + overall_fail
overall_rate = overall_pass / total_tests if total_tests > 0 else 0

# Calculate 95% CI using normal approximation
std_error = np.sqrt(overall_rate * (1 - overall_rate) / total_tests)
ci_lower = overall_rate - 1.96 * std_error
ci_upper = overall_rate + 1.96 * std_error

# Generate markdown report
md = "# Adversarial Testing Results\n\n"
md += "## Overall Performance\n\n"
md += f"Total tests: {total_tests}\n"
md += f"Pass rate: {overall_rate:.2%} ± {std_error:.2%}\n"
md += f"95% CI: [{ci_lower:.2%}, {ci_upper:.2%}]\n\n"

md += "## Per-Category Results\n\n"
md += "| Category | Pass | Fail | Pass Rate |\n"
md += "|----------|------|------|-----------|\n"

for category, stats in category_stats.items():
    total = stats["pass"] + stats["fail"]
    rate = stats["pass"] / total if total > 0 else 0
    md += f"| {category} | {stats['pass']} | {stats['fail']} | {rate:.2%} |\n"

# Save report
with open("adversarial_results.md", "w") as f:
    f.write(md)
```
