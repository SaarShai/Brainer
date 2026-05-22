---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round8]
---

**Design: Wiki Page Supersession Detection System**

The proposed system automatically detects when a newly written wiki page supersedes an older one using three heuristics:

1. **Same Type + Domain**: Both pages must belong to the same category (e.g., "Smartphones") and domain (e.g., technology).

2. **Overlapping Concept Tags**: The new page shares a significant number of keywords or topics with the old page, indicating similar content focus.

3. **Newer Numbers > Older Numbers by >10%**: Metrics like views or edits on the new page exceed the old page's metrics by more than 10%, suggesting higher engagement.

**Implementation Approach:**

- **Feature Extraction**: Extract domain, type, concept tags, and numerical metrics (views, edits) for both pages.
- **Tag Similarity Calculation**: Use TF-IDF or cosine similarity to measure tag overlap between new and old pages.
- **Metric Comparison**: Calculate the percentage increase in metrics for the new page compared to the old one.
- **Classification Model**: Train a logistic regression or neural network model using features like domain match (binary), tag similarity score (continuous), and metric ratio (continuous) to predict supersession.

**Risks of False Positives:**

1. **Overlapping Tags Misclassification**: Pages with similar tags but different focuses may be incorrectly flagged as superseding each other.
2. **Metric Bias**: Popularity metrics might reflect external factors (e.g., current events) rather than content quality, leading to incorrect supersession detection.
3. **Temporal Bias**: A newer page written during a peak usage period might show inflated metrics without being genuinely superior.

**Mitigation Strategies:**

- Incorporate content quality metrics (e.g., edit history, references).
- Set thresholds for tag similarity and metric increases to reduce false positives.
- Continuously monitor and adjust model parameters based on feedback.

This system provides a robust framework for detecting page supersession while acknowledging the need for ongoing refinement to minimize errors.
