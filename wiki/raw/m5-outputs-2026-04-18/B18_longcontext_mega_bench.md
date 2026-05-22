---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round6]
---

To extend `bench/` for long-context retrieval tasks (>10K tokens), we'll design a modular evaluation framework focusing on efficiency and scalability:

```
# Directory structure
bench/
  ├── long_retrieval/
  │   ├── datasets/
  │   │   └── longbench_subset.jsonl
  │   ├── adapters/
  │   │   └── longbench_adapter.py
  │   ├── evaluators/
  │   │   └── retrieval_evaluator.py
  │   └── utils/
  │       ├── memory_utils.py
  │       └── tokenization_utils.py
```

### Key Components:

1. **Datasets**: Pull LongBench subset containing long-form documents (e.g., research papers, books) and associated queries. Store in JSONL format with fields:
   - `id`: Unique identifier
   - `query`: User query (short)
   - `context`: Long document (~10K+ tokens)
   - `answers`: List of answer spans

2. **Adapters**: Convert LongBench data into model-agnostic format, handling:
   - Tokenization-aware splitting for long contexts
   - Memory-efficient storage using on-disk caching
   - Batch processing to minimize peak memory usage

3. **Evaluators**: Implement retrieval metrics focused on long-context scenarios:
   - Recall@K: Proportion of correct answers in top K retrieved chunks
   - Context Efficiency: Ratio of used context tokens to total available
   - Memory Footprint: Peak RAM usage during evaluation

4. **Utils**:
   - `memory_utils.py`: Track and enforce memory budgets
   - `tokenization_utils.py`: Handle long-context tokenization edge cases

### Implementation Notes:

- Use streaming JSONL readers to avoid loading entire dataset into memory
- Implement chunking strategies (e.g., sliding window, paragraph-based) for efficient retrieval
- Optimize for both CPU and GPU evaluation paths
- Add logging for memory usage statistics during evaluation runs

This design balances fidelity to LongBench while addressing practical constraints of long-context processing.
