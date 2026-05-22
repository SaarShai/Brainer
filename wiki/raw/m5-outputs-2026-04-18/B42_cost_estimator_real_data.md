---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round8]
---

```python
import json
from pathlib import Path
import os

class CostSavingsCalculator:
    def __init__(self):
        self.total_calls = 0
        self.skipped_calls = 0
        self.compressed_calls = 0
        self.bytes_before = 0
        self.bytes_after = 0
        
    def load_data(self, data_dir="kaggle_results"):
        jsonl_files = list(Path(data_dir).glob("*.jsonl"))
        
        for file_path in jsonl_files:
            with open(file_path, 'r') as f:
                for line in f:
                    entry = json.loads(line)
                    self.total_calls += 1
                    
                    if entry['skipped']:
                        self.skipped_calls += 1
                    elif entry['compressed']:
                        self.compressed_calls += 1
                        
                    self.bytes_before += entry['bytes_before']
                    self.bytes_after += entry['bytes_after']
                    
    def compute_savings(self):
        if self.total_calls == 0:
            return None
            
        savings = {
            'total_calls': self.total_calls,
            'skipped_ratio': self.skipped_calls / self.total_calls,
            'compressed_ratio': self.compressed_calls / self.total_calls,
            'savings_rate': (self.bytes_before - self.bytes_after) / self.bytes_before
        }
        
        return savings
        
    def estimate_cost_savings(self, cost_per_gb, savings):
        if not savings:
            return 0
            
        total_bytes_saved = (savings['bytes_before'] - savings['bytes_after'])
        total_gb_saved = total_bytes_saved / (1024 ** 3)
        
        return total_gb_saved * cost_per_gb
        
def main():
    calculator = CostSavingsCalculator()
    calculator.load_data()
    
    savings = calculator.compute_savings()
    if not savings:
        print("No data found. Please ensure there are JSONL files in the kaggle_results directory.")
        return
    
    # Example cost per GB ($0.12 is approximate for data transfer costs)
    cost_per_gb = 0.12
    estimated_savings = calculator.estimate_cost_savings(cost_per_gb, savings)
    
    print(f"Total calls analyzed: {savings['total_calls']}")
    print(f"Skipped calls ratio: {savings['skipped_ratio']:.2%}")
    print(f"Compressed calls ratio: {savings['compressed_ratio']:.2%}")
    print(f"Average data savings rate: {savings['savings_rate']:.2%}")
    print(f"Estimated cost savings: ${estimated_savings:.2f}")

if __name__ == "__main__":
    main()
```

This code:
1. Creates a `CostSavingsCalculator` class to process and analyze ComCom run data
2. Loads all JSONL files from the kaggle_results directory
3. Tracks metrics like skipped/compressed calls and bytes transferred before/after compression
4. Computes savings rates based on actual performance
5. Estimates cost savings using real-world compression ratios

The script provides actionable insights by showing:
- Total calls processed
- Percentage of skipped vs compressed calls
- Overall data savings rate
- Estimated dollar savings based on actual transfer costs

To use, ensure your kaggle_results directory contains JSONL files from ComCom runs and run the script.
