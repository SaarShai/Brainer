---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, batch3]
---

### Analysis

To detect temporal shifts in text, we propose combining three heuristics:

1. **Phrase Structure Matching**: Look for "from X to Y" patterns using regex. This captures explicit time shifts:
   - `r'\b(from|extended from|moved from)\s+(\w+)\s+to\s+(\w+)\b'`
   - Matches: "moved from Tuesday to Wednesday", "extended from Feb to March"

2. **Time Entity Recognition**: Use regex to identify valid temporal entities for X and Y:
   - Days: `r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b'`
   - Months: `r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b'`
   - Seasons: `r'\b(Spring|Summer|Fall|Autumn|Winter)\b'`

3. **Tense Contrast Detection**: Identify past-present contrasts using regex:
   - Past tense verbs followed by present tense indicators:
     `r'\b(was|were)\s+\w+\s+(now|currently)\s+\w+'`
   - Matches: "was X, now Y"

**Avoiding False Positives**:

- Exclude casual time mentions without shift indicators
- Filter out non-temporal uses of "from X to Y"
- Ignore cases where X and Y are not valid temporal entities

### Pseudocode

```python
def detect_temporal_shift(sentence):
    # Check for "from X to Y" pattern
    from_to_match = re.search(r'\b(from|extended from|moved from)\s+(\w+)\s+to\s+(\w+)\b', sentence)
    if from_to_match:
        x = from_to_match.group(2)
        y = from_to_match.group(3)
        # Validate X and Y as temporal entities
        if is_temporal(x) and is_temporal(y):
            return True

    # Check for past-present tense contrast
    tense_match = re.search(r'\b(was|were)\s+\w+\s+(now|currently)\s+\w+', sentence)
    if tense_match:
        return True

    return False

def is_temporal(entity):
    days = r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b'
    months = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b'
    seasons = r'\b(Spring|Summer|Fall|Autumn|Winter)\b'
    return re.fullmatch(days, entity) or re.fullmatch(months, entity) or re.fullmatch(seasons, entity)
```
