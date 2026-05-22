import sys
import json
from collections import defaultdict

if len(sys.argv) != 2:
    print("Usage: python script.py <path>")
    sys.exit(1)

data = defaultdict(lambda: {'scores': [], 'tokens': [], 'modes': {}})

with open(sys.argv[1], 'r') as f:
    for line in f:
        entry = json.loads(line.strip())
        cond = entry['cond']
        data[cond]['scores'].append(entry['score'])
        data[cond]['tokens'].append(entry['tokens_in'])
        mode = entry['mode']
        if mode in data[cond]['modes']:
            data[cond]['modes'][mode] += 1
        else:
            data[cond]['modes'][mode] = 1

sorted_conds = sorted(data.keys())
print("| cond | mean_tokens | mean_score | modes |")
print("|------|-------------|------------|-------|")

for cond in sorted_conds:
    scores = data[cond]['scores']
    tokens = data[cond]['tokens']
    mean_score = sum(scores) / len(scores)
    mean_tokens = sum(tokens) / len(tokens)
    mode_counts = sorted(data[cond]['modes'].items())
    modes_str = ", ".join([f"{mode}" if count == 1 else f"{mode}_{count}" for mode, count in mode_counts])
    
    print(f"| {cond} | {mean_tokens:.2f} | {mean_score:.2f} | {modes_str} |")