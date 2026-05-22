---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple
import scipy.stats

def load_jsonl_files() -> List[Dict]:
    results = []
    directories = [
        "kaggle_results",
        "projects/compound-compression-pipeline"
    ]
    
    for dir_path in directories:
        for file_name in os.listdir(dir_path):
            if file_name.endswith(".jsonl"):
                with open(os.path.join(dir_path, file_name), 'r') as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            results.append({
                                'timestamp': datetime.fromisoformat(data['timestamp']),
                                'category': data.get('category', 'unknown'),
                                'size_before': data['size_before'],
                                'size_after': data['size_after']
                            })
                        except (KeyError, json.JSONDecodeError):
                            continue
    return results

def calculate_savings(before: int, after: int) -> float:
    if before == 0:
        return 0.0
    return ((before - after) / before) * 100

def compute_confidence_interval(data: List[float]) -> Tuple[float, float]:
    mean = scipy.stats.trim_mean(data, 0.1)
    stderr = scipy.stats.sem(data)
    return scipy.stats.t.interval(0.95, len(data)-1, loc=mean, scale=stderr)

def generate_report(results: List[Dict]) -> str:
    if not results:
        return "No data available."
    
    savings_data = []
    for res in results:
        savings = calculate_savings(res['size_before'], res['size_after'])
        savings_data.append({
            **res,
            'savings': savings
        })
    
    overall_savings = [x['savings'] for x in savings_data]
    overall_ci = compute_confidence_interval(overall_savings)
    
    category_groups = {}
    for data in savings_data:
        cat = data['category']
        if cat not in category_groups:
            category_groups[cat] = []
        category_groups[cat].append(data['savings'])
    
    report = f"# Compression Results Report\n\n"
    report += f"**Overall Savings**: {round(scipy.stats.trim_mean(overall_savings, 0.1), 2)}% ± {round(max(overall_ci)-round(scipy.stats.trim_mean(overall_savings, 0.1), 2), 2)}%\n\n"
    
    for cat, savings in category_groups.items():
        ci = compute_confidence_interval(savings)
        report += f"## Category: {cat}\n"
        report += f"- Mean Saving: {round(scipy.stats.trim_mean(savings, 0.1), 2)}%\n"
        report += f"- CI: ({round(ci[0], 2)}, {round(ci[1], 2)})\n\n"
    
    first_run = min(results, key=lambda x: x['timestamp'])
    last_run = max(results, key=lambda x: x['timestamp'])
    trend_savings = calculate_savings(last_run['size_before'], last_run['size_after']) - calculate_savings(first_run['size_before'], first_run['size_after'])
    
    report += "## Trend Analysis\n"
    if abs(trend_savings) > 1:
        regression_flag = "⚠️ POTENTIAL REGRESSION" if trend_savings < 0 else "✅ IMPROVEMENT"
        report += f"- Significant change detected: {round(trend_savings, 2)}%\n"
        report += f"{regression_flag}\n"
    else:
        report += "- No significant trend detected.\n"
    
    return report

if __name__ == "__main__":
    results = load_jsonl_files()
    report_content = generate_report(results)
    with open("REPORT.md", "w") as f:
        f.write(report_content)
```
