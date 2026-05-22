---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, batch3]
---

To design a task completion detector for context-keeper v2, we'll implement a weighted scoring system based on four heuristics: user positive-close signals, recent successful tests/builds, todo completion, and commits with non-trivial diffs. Each heuristic contributes to a score that determines if the skill-crystallizer should be triggered.

### Heuristic Breakdown:

1. **User Positive-Close Signals (30%)**: Detect when users explicitly indicate task completion using phrases like "done," "complete," or similar.
2. **Recent Successful Tests/Builds (30%)**: Check for successful test runs or builds within the last 5-10 minutes, indicating functionality is working as intended.
3. **TodoWrite All-Complete (25%)**: Verify all todos in the codebase are marked as complete, suggesting no remaining tasks.
4. **Commit with Non-Trivial Diff (15%)**: Identify commits that modify multiple files or significant portions of code, indicating substantial progress.

### Weighted Scoring System:

Each heuristic is assigned a weight based on its reliability and significance:
- User signals: 30%
- Successful tests: 30%
- Todo completion: 25%
- Commits: 15%

The total score is the sum of each heuristic's contribution. A threshold of **70%** ensures high precision, triggering the skill-crystallizer only when most strong indicators are met.

### Implementation Considerations:

- **Detection Methods**: Use NLP for user signals, session logs for tests, code parsing for todos, and version control events for commits.
- **Time Window**: Define 'recent' as 5-10 minutes to capture timely actions.
- **Edge Cases**: Handle scenarios where users may signal completion without tests or commit without closing todos by relying on multiple indicators.

This system balances precision with flexibility, ensuring the skill-crystallizer is triggered accurately upon task completion.
