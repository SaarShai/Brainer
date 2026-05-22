---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round8]
---

To design a session-level quality score from confidence scores:

1. **Normalization**: Convert all confidence scores to a 0-1 scale for consistency.

2. **Weighting**: Assign weights based on importance:
   - Context-keeper (accuracy): Higher weight (e.g., 70%)
   - Compress skip/keep (efficiency): Lower weight (e.g., 30%)

3. **Aggregation**:
   - Compute weighted average:  
     \( \text{Quality Score} = (\text{Context Score} \times 0.7) + (\text{Compress Score} \times 0.3) \)

4. **Presentation**: Display on a 1-10 scale or percentage, with explanations for clarity.

5. **Testing**: Validate with real data to ensure it reflects user needs accurately.

This approach ensures both accuracy and efficiency are considered, providing a balanced and understandable quality metric.
