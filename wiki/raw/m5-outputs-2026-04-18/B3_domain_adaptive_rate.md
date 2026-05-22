---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round4]
---

```
function select_rate(prose_density, question_type, numeric_content):
    if prose_density > 70:
        // Text-heavy content requires slower processing
        if question_type == "multiple_choice":
            // Multiple choice questions are quicker to answer
            return 0.7
        else:
            // Longer-form questions need more time
            return 0.5
    else:
        // Less text, faster processing by default
        if question_type == "essay":
            // Essay questions require detailed responses
            return 0.7
        elif question_type == "short_answer":
            // Short answers are quicker than essays
            return 0.9
        else:
            // Default for other question types
            return 0.7

    // Adjustments based on numeric content
    if numeric_content > 50:
        // Numeric-heavy content requires slower processing
        rate = max(rate, 0.5)
    elif numeric_content > 25:
        // Moderate numeric content needs some adjustment
        rate = max(rate, 0.7)

    return rate
```

This decision tree prioritizes prose density as the primary factor, with question type and numeric content serving as secondary modifiers. The logic reflects that text-heavy content generally requires slower processing, while numeric-heavy content also necessitates more time due to its complexity. Question types like essays require more deliberate consideration, while short answers can be processed faster.
