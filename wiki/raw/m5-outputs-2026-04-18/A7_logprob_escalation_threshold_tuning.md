---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, batch3]
---

To empirically calibrate the `min_avg_logprob` threshold in `verify_logprob.py`, follow this methodology:

1. **Data Collection**:  
   Run ComCom on a diverse set of inputs to collect N samples of `(avg_logprob, quality_score)` pairs. Ensure the dataset includes varied question types and difficulty levels to capture different log probability distributions.

2. **Define Correctness Class**:  
   Establish a binary classification where `quality_score` above a predefined threshold (e.g., 0.7) indicates a "correct answer." This creates labeled data for ROC analysis.

3. **ROC Curve Construction**:  
   Vary the `min_avg_logprob` threshold from its minimum observed value to -1.5 (current default). For each threshold:
   - Classify answers as "accepted" if `avg_logprob >= threshold`.
   - Compute precision (fraction of accepted answers that are correct) and recall (fraction of correct answers accepted).
   - Plot precision vs. recall to visualize trade-offs.

4. **F1 Score Maximization**:  
   Calculate the F1 score for each threshold, which balances precision and recall. Select the threshold with the highest F1 score as it optimally preserves answer quality while minimizing incorrect acceptances.

5. **Validation**:  
   Test the selected threshold on a held-out dataset to ensure generalizability across different input distributions.

This approach ensures the threshold is tuned to real-world performance, balancing accuracy and model confidence effectively.
