---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round6]
---

```markdown
---
name: "L3 SOP Template"
dependencies:
  - "dependency1.md"
  - "dependency2.md"
---

# L3 Standard Operating Procedure: [SOP Name]

## Trigger
**When:** [Brief description of when this SOP is triggered]  
**Why:** [Purpose or objective of the procedure]

## Steps

### Step 1: [Step Title]
- **Action:** [Description of action to perform]
- **Expected Outcome:** [What should happen after completing this step]
- **Notes/Considerations:** [Any important details or caveats]

### Step 2: [Step Title]
- **Action:** [Description of action to perform]
- **Expected Outcome:** [What should happen after completing this step]
- **Notes/Considerations:** [Any important details or caveats]

## Success Signal
**Indicator:** [Specific signal confirming successful completion]  
**Verification:** [How to confirm success, e.g., logs, UI confirmation, etc.]

## Failure Recovery
**Actions:**
1. [Step 1 for recovery]
2. [Step 2 for recovery]
3. [Step 3 for recovery]

**Escalation Path:**
- [Contact or team to notify if recovery fails]
- [Alternative escalation steps]

---

### Example SOP:

```markdown
---
name: "Incident Response"
dependencies:
  - "alerting.md"
  - "communications.md"
---

# L3 Standard Operating Procedure: Incident Response

## Trigger
**When:** An alert is triggered by monitoring systems indicating a critical system failure.  
**Why:** To ensure rapid response and minimize downtime.

## Steps

### Step 1: Acknowledge the Alert
- **Action:** Log into the monitoring dashboard and acknowledge the alert.
- **Expected Outcome:** Alert status changes to "Acknowledged."
- **Notes/Considerations:** Ensure all relevant team members are notified via communication channels.

### Step 2: Assess Impact
- **Action:** Review system logs, metrics, and user reports to determine the scope of the issue.
- **Expected Outcome:** Clear understanding of affected systems and users.
- **Notes/Considerations:** Prioritize critical services first.

## Success Signal
**Indicator:** Affected systems return to normal operational status.  
**Verification:** Confirm through monitoring dashboards and user feedback.

## Failure Recovery
**Actions:**
1. Rollback changes if the issue was caused by recent deployments.
2. Deploy a hotfix if the root cause is identified.
3. Engage on-call support or external vendors if internal resources are insufficient.

**Escalation Path:**
- Notify the Incident Management Team Lead.
- If unresolved within 30 minutes, escalate to Executive Support.
```

This schema balances human readability with machine parseability by using structured headers and YAML front matter for metadata.
