---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

```json
[
  {
    "description": "A security system that triggers an alarm only when motion is detected unless it's a false positive or if the user is authorized.",
    "condition": "if (motion_detected) then trigger_alarm else stay_silent, unless (false_positive), only_when (user_authorized)"
  },
  {
    "description": "An automated response system that executes an action if a button is clicked, but only if the user has permission and specific criteria are met.",
    "condition": "if (button_clicked) then execute_action else do_nothing, unless (permission_denied), only_when (criteria_met)"
  },
  {
    "description": "A legal contract that requires payment if goods are delivered on time, but only if no force majeure event occurs and all terms are satisfied.",
    "condition": "if (on_time_delivery) then pay else impose_penalty, unless (force_majeure), only_when (terms_met)"
  },
  {
    "description": "A user interface element that displays a message if a specific query is made, but only if the query is relevant and the context is correct.",
    "condition": "if (query_made) then display_message else ignore_query, unless (irrelevant_query), only_when (context_correct)"
  },
  {
    "description": "An access control system that grants access if a user has the required role, but only in emergencies or if verification is successful.",
    "condition": "if (role_required) then grant_access else deny_access, unless (emergency_mode), only_when (verification_success)"
  }
]
```
