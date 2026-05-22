---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
import importlib
import json
import random
import requests
from typing import Dict, Any
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_eval(dataset_key: str, tool_name: str, model: str, n: int, runs: int = 1) -> None:
    adapter_module = importlib.import_module(f'bench.adapters.{dataset_key}')
    adapter = adapter_module.Adapter()
    
    tool_runners = {
        'comcom': lambda data: comcom.compress(data),
        'semdiff': lambda data: semdiff.read_smart(data),
        'baseline': lambda data: baseline.identity(data)
    }
    
    if tool_name not in tool_runners:
        raise ValueError(f"Unknown tool: {tool_name}")
        
    results = []
    for run_id in range(runs):
        data = adapter.get_data(n)
        
        # Get baseline and tool outputs
        baseline_output = tool_runners['baseline'](data)
        tool_output = tool_runners[tool_name](data)
        
        if tool_name == 'ollama':
            try:
                response = requests.post(
                    f"http://localhost:1143/api/generate",
                    json={
                        "model": model,
                        "prompt": data,
                        "temperature": 0.7
                    }
                )
                tool_output = response.json()['response']
            except Exception as e:
                logger.error(f"Ollama API error: {e}")
                continue
                
        # Score outputs
        baseline_score = adapter.score(data, baseline_output)
        tool_score = adapter.score(data, tool_output)
        
        delta = tool_score - baseline_score
        
        results.append({
            'run_id': run_id,
            'dataset_key': dataset_key,
            'tool_name': tool_name,
            'model': model,
            'n': n,
            'baseline_score': baseline_score,
            'tool_score': tool_score,
            'delta': delta
        })
        
    # Bootstrap confidence interval for deltas
    deltas = [r['delta'] for r in results]
    bootstrap_means = []
    for _ in range(1000):
        resample = random.choices(deltas, k=len(deltas))
        bootstrap_means.append(np.mean(resample))
    
    ci_low, ci_high = np.percentile(bootstrap_means, [2.5, 97.5])
    
    # Emit results
    with open('results.jsonl', 'a') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
            
    # Generate markdown summary
    summary = {
        'metric': 'score_delta',
        'value': np.mean(deltas),
        'confidence_interval': [ci_low, ci_high],
        'success_rate': len(results)/runs,
        'metadata': {
            'dataset_key': dataset_key,
            'tool_name': tool_name,
            'model': model
        }
    }
    
    with open('results.md', 'a') as f:
        f.write(f"""
## Run Results

- Dataset: {dataset_key}
- Tool: {tool_name}
- Model: {model}
- Runs: {runs}

| Metric | Value |
|--------|-------|
| Mean Score Delta | {summary['value']:.4f} |
| CI (95%) | ({ci_low:.4f}, {ci_high:.4f}) |
| Success Rate | {summary['success_rate']:.2f}
        
        """)
```
