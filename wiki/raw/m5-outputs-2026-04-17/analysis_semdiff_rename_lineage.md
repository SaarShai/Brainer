---
type: raw
source: m5-max (deepseek-r1:32b)
date: 2026-04-17
tags: [m5-generated]
---

To detect renames in semdiff while preserving lineage, we propose an algorithm that identifies functions with identical bodies or similar AST structures but different names. This approach balances accuracy and performance by first checking exact body hashes for confident rename detection, then using AST-structure hashing to handle minor changes.

### Algorithm Steps:

1. **Parse Code**: Convert both code versions into lists of function definitions.
2. **Compute Hashes**:
   - For each function, compute an exact body hash (e.g., SHA-1 of the source code).
   - Compute an AST-structure hash by traversing the AST and ignoring identifiers like function names.
3. **Exact Match Check**: Compare exact body hashes between old and new functions. If a match is found, mark as a rename.
4. **AST Structure Comparison**: For unmatched functions, compare AST-structure hashes with a similarity threshold to detect likely renames despite minor changes.

### Pseudocode:

```python
def detect_renames(old_functions, new_functions):
    # Precompute hashes for all functions
    old_hash_map = {f: (hash_body(f), hash_ast_structure(f)) for f in old_functions}
    new_hash_map = {f: (hash_body(f), hash_ast_structure(f)) for f in new_functions}

    renames = []
    matched_new = set()

    # Check exact body matches first
    for old_f, (old_body_hash, _) in old_hash_map.items():
        for new_f, (new_body_hash, _) in new_hash_map.items():
            if new_f not in matched_new and old_body_hash == new_body_hash:
                renames.append((old_f, new_f))
                matched_new.add(new_f)
                break

    # Check AST structure matches with tolerance
    for old_f, (_, old_ast_hash) in old_hash_map.items():
        if old_f not in [r[0] for r in renames]:
            for new_f, (_, new_ast_hash) in new_hash_map.items():
                if new_f not in matched_new and is_similar(old_ast_hash, new_ast_hash):
                    renames.append((old_f, new_f))
                    matched_new.add(new_f)
                    break

    return renames
```

### Trade-offs:

- **False Positives**: AST similarity may incorrectly match unrelated functions with similar structures.
- **False Negatives**: Minor changes (e.g., added comments) can cause exact matches to fail.
- **Performance**: Hashing and comparison operations add computational overhead, especially for large codebases.

This approach prioritizes accuracy by first checking exact matches before falling back to structural comparisons, balancing the need for precise lineage tracking with performance considerations.
