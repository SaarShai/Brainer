---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```json
[
  {
    "id": 1,
    "description": "Access Control System",
    "example": "(isAdmin AND hasToken) OR hasAPIKey vs isAdmin AND (hasToken OR hasAPIKey)",
    "explanation": "In the first expression, access is granted if either both admin rights and a token are present or an API key exists. In the second, access requires admin rights plus either a token or API key."
  },
  {
    "id": 2,
    "description": "Product Availability Check",
    "example": "(inStock AND online) OR preorder vs inStock AND (online OR preorder)",
    "explanation": "The first allows availability if both in stock and online, or on preorder. The second requires the product to be in stock and either online or on preorder."
  },
  {
    "id": 3,
    "description": "Medical Diagnosis",
    "example": "(symptomX AND symptomY) OR positiveTest vs symptomX AND (symptomY OR positiveTest)",
    "explanation": "The first diagnoses if both symptoms are present or the test is positive. The second requires symptom X plus either Y or a positive test."
  },
  {
    "id": 4,
    "description": "Financial Transaction Approval",
    "example": "(approveByManager1 AND approveByManager2) OR autoApprove vs approveByManager1 AND (approveByManager2 OR autoApprove)",
    "explanation": "The first approves if both managers agree or the system does. The second requires manager1's approval plus either manager2 or the system."
  },
  {
    "id": 5,
    "description": "Network Security Access",
    "example": "(hasToken AND inApprovedGroup) OR hasBackupKey vs hasToken AND (inApprovedGroup OR hasBackupKey)",
    "explanation": "The first allows access with token and group, or backup key. The second requires a valid token plus either group membership or backup key."
  }
]
```
