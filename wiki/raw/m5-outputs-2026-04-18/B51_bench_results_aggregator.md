---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round9]
---

```python
import json
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.stats import t
from datetime import datetime

def load_jsonl_files(directory):
    """Load all JSONL files from a directory"""
    data = []
    for file_path in Path(directory).glob("*.jsonl"):
        with open(file_path, "r") as f:
            for line in f:
                data.append(json.loads(line))
    return data

def calculate_confidence_interval(values):
    """Calculate 95% confidence interval"""
    n = len(values)
    mean = np.mean(values)
    stderr = np.std(values) / np.sqrt(n)
    t_critical = t.ppf(0.975, df=n-1)
    margin_error = t_critical * stderr
    return (mean - margin_error, mean + margin_error)

def main():
    # Load data from all sources
    kaggle_data = load_jsonl_files("kaggle_results")
    local_data = load_jsonl_files("local_eval_logs")
    adversarial_data = load_jsonl_files("adversarial_runs")

    # Combine into a single DataFrame
    df = pd.DataFrame(kaggle_data + local_data + adversarial_data)
    
    # Process timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["month"] = df["timestamp"].dt.month
    df["day"] = df["timestamp"].dt.day
    df["week"] = df["timestamp"].dt.isocalendar().week
    
    # Calculate metrics
    metrics = ["accuracy", "f1_score", "precision", "recall"]
    for metric in metrics:
        values = df[metric].values
        mean, ci_low, ci_high = np.mean(values), *calculate_confidence_interval(values)
        
        print(f"**{metric} Analysis:**")
        print(f"- Mean: {mean:.3f}")
        print(f"- 95% CI: [{ci_low:.3f}, {ci_high:.3f}]")
        print("\n")
    
    # Group by date ranges
    df_monthly = df.groupby("month")[metrics].agg(["mean", "count"])
    df_weekly = df.groupby("week")[metrics].agg(["mean", "count"])
    
    # Generate markdown report
    with open("REPORT.md", "w") as f:
        f.write("# Model Performance Report\n")
        
        # Overall performance table
        f.write("\n## Overall Metrics\n")
        f.write("\n| Metric | Mean | 95% CI Lower | 95% CI Upper |\n")
        f.write("|--------|------|--------------|--------------|\n")
        for metric in metrics:
            mean = df[metric].mean()
            ci_low, ci_high = calculate_confidence_interval(df[metric])
            f.write(f"| {metric} | {mean:.3f} | {ci_low:.3f} | {ci_high:.3f} |\n")
        
        # Temporal trends
        f.write("\n## Temporal Trends\n")
        f.write("\n### Monthly Performance\n")
        f.write(df_monthly.to_markdown())
        
        f.write("\n### Weekly Performance\n")
        f.write(df_weekly.to_markdown())

if __name__ == "__main__":
    main()
```

This script:
1. Loads JSONL files from multiple sources
2. Combines and processes the data into a DataFrame
3. Calculates confidence intervals for key metrics
4. Generates temporal aggregations (monthly, weekly)
5. Outputs a structured markdown report with tables and analysis

The report includes:
- Overall performance metrics with CIs
- Monthly and weekly trend tables
- Clear formatting for easy readability
