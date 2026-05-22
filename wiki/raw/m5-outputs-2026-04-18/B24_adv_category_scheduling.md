---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round6]
---

```json
[
  {
    "id": 1,
    "scenario": "Time Zone Confusion",
    "question": "Two team members are scheduling a meeting between New York (EST) and Tokyo (JST). If the meeting is set for 2 PM EST, what time should it be in Tokyo?",
    "correct_answer": "3 AM JST",
    "distractors": ["11 AM JST", "5 PM JST", "9 AM JST"],
    "explanation": "New York (EST) is UTC-5 and Tokyo (JST) is UTC+9. The time difference is 14 hours ahead. Adding 14 hours to 2 PM EST results in 4 AM JST, but daylight saving adjustments may cause a slight variation.",
    "difficulty_level": "Medium"
  },
  {
    "id": 2,
    "scenario": "AM/PM Flip",
    "question": "A flight departs at 10:30 PM local time in Los Angeles (PST). What is the departure time in New York (EST)?",
    "correct_answer": "1:30 AM EST",
    "distractors": ["9:30 AM EST", "7:30 PM EST", "12:30 AM EST"],
    "explanation": "Los Angeles (PST) is UTC-8 and New York (EST) is UTC-5. The time difference is 3 hours ahead. Adding 3 hours to 10:30 PM PST results in 1:30 AM EST.",
    "difficulty_level": "Easy"
  },
  {
    "id": 3,
    "scenario": "Shift Handoff",
    "question": "A hospital shift ends at 8 PM and the next begins at 8 AM. What is the total duration of a 24-hour period covered by these shifts?",
    "correct_answer": "12 hours",
    "distractors": ["24 hours", "16 hours", "8 hours"],
    "explanation": "The first shift covers from 8 PM to midnight (4 hours), and the second from 8 AM to 4 PM (8 hours). The total is 12 hours, leaving a gap between midnight and 8 AM.",
    "difficulty_level": "Hard"
  },
  {
    "id": 4,
    "scenario": "Overlapping Windows",
    "question": "Two events occur simultaneously: one starts at 9 AM in London (BST) and another at 10 AM in Paris (CEST). What is the time difference between them?",
    "correct_answer": "No overlap, 1 hour apart",
    "distractors": ["They are simultaneous", "2 hours apart", "3 hours apart"],
    "explanation": "London (BST) is UTC+1 and Paris (CEST) is UTC+2. The time difference is 1 hour ahead. Thus, the events occur an hour apart with no overlap.",
    "difficulty_level": "Medium"
  },
  {
    "id": 5,
    "scenario": "Time Zone Conversion",
    "question": "A conference call starts at 6 PM in Sydney (AEST). What time is it in Singapore (SGT)?",
    "correct_answer": "4 PM SGT",
    "distractors": ["5 PM SGT", "3 PM SGT", "7 PM SGT"],
    "explanation": "Sydney (AEST) is UTC+10 and Singapore (SGT) is UTC+8. The time difference is 2 hours behind. Subtracting 2 hours from 6 PM AEST results in 4 PM SGT.",
    "difficulty_level": "Easy"
  }
]
```
