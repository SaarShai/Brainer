---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round4]
---

**Synthetic Evaluation Specification for Context-Keeper Compaction**

**Objective:**  
Evaluate Context-Keeper’s ability to compact context windows while retaining important facts.

**Components:**

1. **Session Generation**
   - **Parameters:**
     - `num_sessions`: Number of synthetic sessions (e.g., 100).
     - `session_length`: Average number of messages per session (e.g., 50).
     - `fact_density`: Percentage of messages containing facts (e.g., 20%).
   - **Process:**
     - Create unique session IDs.
     - Generate messages with alternating user and bot roles, including timestamps and metadata (user ID, device).
     - Embed known facts in bot responses at specified intervals.
   - **Output:**  
     List of synthetic sessions with structured data.

2. **Compaction Process**
   - **With Context-Keeper:**
     - Apply compaction algorithm to retain important facts beyond the window.
   - **Without Context-Keeper:**
     - Use sliding window (e.g., last 1024 tokens) without prioritization.
   - **Parameters:**
     - `compaction_window`: Tokens retained post-compaction (e.g., 512).
   - **Output:**  
     Compacted context windows for each session.

3. **Recall Evaluation**
   - **QA Pair Generation:**
     - Extract known facts from sessions.
     - Create questions targeting these facts, ensuring specificity.
   - **Evaluation Process:**
     - Run QA on both compacted versions (with and without Context-Keeper).
     - Track correct answers based on known facts.
   - **Metrics:**
     - Accuracy: Percentage of correct answers.
     - Precision/Recall/F1-score for nuanced error analysis.

**Implementation Notes:**

- **Fact Identification:** Tag important messages during session generation to include in QA pairs.
- **Parameterization:** Allow variation in session length, compaction window size, and QA pairs per fact for comprehensive testing.
- **Fair Comparison:** Ensure identical initial setups except for compaction logic to isolate method effects.

**Documentation:**

- Include detailed steps, parameters, and expected outputs for reproducibility.
