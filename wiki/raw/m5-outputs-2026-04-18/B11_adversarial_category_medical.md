---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round5]
---

```json
[
  {
    "id": 1,
    "context": "The prescribed dosage for the medication is 500 mg once daily.",
    "question": "What is the correct dosage of the medication?",
    "answer": "500 mg once daily",
    "why_hard": "This question tests understanding of dosage units (mg vs mcg) and frequency (daily vs weekly). Confusion between mg and mcg could lead to underdosing or overdosing, while misinterpreting frequency could result in incorrect administration schedules."
  },
  {
    "id": 2,
    "context": "The recommended dose for the supplement is 1000 mcg once weekly.",
    "question": "How often should the supplement be taken?",
    "answer": "Once weekly",
    "why_hard": "This question focuses on frequency interpretation. Patients may confuse 'once weekly' with 'once daily,' leading to incorrect dosing schedules."
  },
  {
    "id": 3,
    "context": "The patient was prescribed 25 mcg of the medication, but the label reads 25 mg.",
    "question": "What is the correct dosage in milligrams?",
    "answer": "0.025 mg",
    "why_hard": "This question highlights the critical difference between mcg and mg. A failure to convert units correctly could result in a thousandfold dosing error."
  },
  {
    "id": 4,
    "context": "The medication should be taken once daily, but the patient received instructions for once weekly.",
    "question": "What is the correct frequency for taking the medication?",
    "answer": "Once daily",
    "why_hard": "This question tests comprehension of dosing frequency. Misinterpreting 'daily' as 'weekly' could lead to undertreatment."
  },
  {
    "id": 5,
    "context": "The prescribed dose is 0.5 mg twice daily, but the patient interpreted it as 500 mcg twice weekly.",
    "question": "What is the correct dosage and frequency?",
    "answer": "0.5 mg twice daily",
    "why_hard": "This question combines unit conversion (mg vs mcg) and frequency interpretation (daily vs weekly). Confusion in either area could lead to significant dosing errors."
  }
]
```
