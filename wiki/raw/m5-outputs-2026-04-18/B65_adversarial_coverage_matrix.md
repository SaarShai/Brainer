---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

### Matrix Mapping Adversarial Categories to Compression Features

The following matrix maps adversarial categories to the compression features they stress. This helps identify overlaps (shared stresses) and gaps (unstressed features).

| **Adversarial Category**       | **Compression Features Stressed**                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------------|
| **Evasion Attacks**           | Robustness, Latency, Integrity                                                                |
| **Poisoning Attacks**         | Integrity, Resource Utilization, Privacy Preservation                                           |
| **Model Stealing Attacks**    | Security, Transparency, Scalability                                                           |
| **Data Manipulation Attacks** | Robustness, Compression Ratio, Privacy Preservation                                            |
| **Backdoor Attacks**          | Integrity, Latency, Resource Utilization                                                      |
| **Membership Inference Attacks** | Privacy Preservation, Transparency, Robustness                                              |
| **Model Inversion Attacks**   | Privacy Preservation, Scalability, Security                                                   |

### Analysis of Overlaps and Gaps

1. **Overlaps:**
   - **Robustness:** Targeted by Evasion Attacks and Data Manipulation Attacks.
   - **Integrity:** Targeted by Poisoning Attacks and Backdoor Attacks.
   - **Privacy Preservation:** Targeted by Poisoning Attacks, Data Manipulation Attacks, Membership Inference Attacks, and Model Inversion Attacks.

2. **Gaps:**
   - **Transparency:** Only stressed by Model Stealing Attacks and Membership Inference Attacks.
   - **Scalability:** Only stressed by Model Stealing Attacks and Model Inversion Attacks.
   - **Security:** Targeted by Model Stealing Attacks and Model Inversion Attacks but not others.

This matrix highlights critical areas for defense (e.g., Robustness, Privacy Preservation) and potential gaps in research or implementation (e.g., Transparency, Scalability). Addressing these can improve overall system resilience against adversarial attacks.
