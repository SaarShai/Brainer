---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, batch3]
---

```python
import json
import random
from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np

@dataclass
class EvalResult:
    """Single evaluation result with metadata"""
    dataset_key: str
    tool_name: str
    model: str
    sample_id: int
    prediction: str
    score: float
    metrics: Dict[str, float]

class ToolAdapter:
    """Base class for tool adapters"""
    def __init__(self, model):
        self.model = model
        
    def predict(self, question: str) -> str:
        raise NotImplementedError

class EvalAdapter:
    """Base class for evaluation adapters"""
    def __init__(self, dataset_key: str):
        self.dataset_key = dataset_key
        
    def load_dataset(self, n: int) -> List[Dict]:
        raise NotImplementedError
    
    def score(self, prediction: str, ground_truth: str) -> Dict[str, float]:
        raise NotImplementedError

def bootstrap_ci(results: List[float], sample_size: int=1000) -> Dict:
    """Compute bootstrap confidence intervals"""
    if not results:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    
    scores = np.array(results)
    bootstraps = []
    for _ in range(sample_size):
        resample = random.choices(scores, k=len(scores))
        bootstraps.append(np.mean(resample))
        
    return {
        "mean": np.mean(scores),
        "ci_low": np.percentile(bootstraps, 2.5),
        "ci_high": np.percentile(bootstraps, 97.5)
    }

def run_evaluation(
    dataset_key: str,
    tool_name: str,
    model: Optional[str] = None,
    n: int = 100
) -> Dict:
    """Unified evaluation runner"""
    
    # Initialize adapters
    tool_adapter = _get_tool_adapter(tool_name, model)
    eval_adapter = _get_eval_adapter(dataset_key)
    
    results = []
    dataset = eval_adapter.load_dataset(n)
    
    for idx, sample in enumerate(dataset):
        try:
            prediction = tool_adapter.predict(sample["question"])
            metrics = eval_adapter.score(prediction, sample["answer"])
            
            result = EvalResult(
                dataset_key=dataset_key,
                tool_name=tool_name,
                model=model or "default",
                sample_id=idx,
                prediction=prediction,
                score=metrics.get("overall", 0.0),
                metrics=metrics
            )
            results.append(result)
            
        except Exception as e:
            print(f"Error processing sample {idx}: {str(e)}")
            continue
            
    # Save results
    with open("results.jsonl", "w") as f:
        for res in results:
            f.write(json.dumps(res.__dict__) + "\n")
    
    # Compute bootstrap summary
    scores = [res.score for res in results]
    ci_summary = bootstrap_ci(scores)
    
    return {
        "dataset_key": dataset_key,
        "tool_name": tool_name,
        "model": model or "default",
        "total_samples": len(results),
        "ci_summary": ci_summary,
        "results_path": "results.jsonl"
    }
```
