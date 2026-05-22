---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round8]
---

```python
import argparse
from typing import List, Dict, Any
import os

# Dataset configurations
DATASETS: List[str] = [
    "adversarial1", 
    "adversarial2",
    "coqa",
    "squad",
    "bbc"
]

# Tool configurations
TOOLS: List[str] = [
    "comcom",
    "semdiff",
    "context-keeper"
]

class Models:
    @staticmethod
    def get_model_name(provider: str) -> str:
        if provider == "ollama":
            return os.getenv("OLLAMA_MODEL", "llama2")
        elif provider == "anthropic":
            return os.getenv("ANTHROPIC_MODEL", "claude-3-opus-20240229")
        elif provider == "openai":
            return os.getenv("OPENAI_MODEL", "gpt-4")
        else:
            raise ValueError(f"Unknown model provider: {provider}")

    @staticmethod
    def get_api_call(provider: str) -> Any:
        if provider == "ollama":
            from ollama import generate
            return generate
        elif provider == "anthropic":
            from anthropic import Anthropic
            return Anthropic(os.getenv("ANTHROPIC_API_KEY")).claude.completion
        elif provider == "openai":
            from openai import OpenAI
            return OpenAI(os.getenv("OPENAI_API_KEY")).chat.completions.create
        else:
            raise ValueError(f"Unknown API provider: {provider}")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run benchmarks on QA models")
    parser.add_argument('--dataset', type=str, required=True,
                       choices=DATASETS + ["all"],
                       help='Dataset to use or "all" for all datasets')
    parser.add_argument('--tool', type=str, required=True,
                       choices=TOOLS,
                       help='Tool to evaluate with')
    parser.add_argument('--mode', type=str, required=True,
                       choices=['A_full', 'B_v1', 'C_v2', 'D_adaptive'],
                       help='Evaluation mode')
    parser.add_argument('--model_provider', type=str, required=True,
                       choices=['ollama', 'anthropic', 'openai'],
                       help='Model provider')
    parser.add_argument('--output_dir', type=str, default="results",
                       help='Output directory for results')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Validate inputs
    if args.dataset == "all":
        datasets = DATASETS
    else:
        if args.dataset not in DATASETS:
            raise ValueError(f"Invalid dataset: {args.dataset}")
        datasets = [args.dataset]
        
    # Get model configuration
    model_name = Models.get_model_name(args.model_provider)
    api_call = Models.get_api_call(args.model_provider)
    
    # Run benchmarks
    for dataset in datasets:
        print(f"Running benchmark on {dataset} with {model_name}")
        # TODO: Implement actual benchmarking logic
        
if __name__ == "__main__":
    main()
```

This Python script provides a structured approach to running benchmarks across multiple QA models and tools. It supports:

1. **Datasets**: All adversarial datasets plus CoQA, SQuAD, and BBC
2. **Tools**: comcom, semdiff, context-keeper
3. **Models**: Ollama, Anthropic, OpenAI via environment variables
4. **Modes**: A_full, B_v1, C_v2, D_adaptive

The script includes:
- Argument parsing for dataset selection (including "all" option)
- Model configuration management
- API call handling based on provider
- Error checking and validation
- Extensible structure for adding benchmarking logic

Key features:
- Uses environment variables for model access keys
- Supports multiple datasets and tools
- Modular design for easy extension
- Input validation for all parameters
