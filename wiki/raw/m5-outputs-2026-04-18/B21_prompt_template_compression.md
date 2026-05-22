---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round6]
---

### Algorithm for Compressing Structured Prompt Templates

**1. Input Parsing:**
   - **Step 1:** Split the input template into sections using markers (e.g., `###`, `---`).
   - **Step 2:** Identify and extract placeholders (e.g., `<|...|>`).

**2. Redundancy Detection:**
   - **Step 3:** For each section, tokenize text into phrases or words.
   - **Step 4:** Use frequency analysis to identify repeated phrases across sections.

**3. Compression Logic:**
   - **Step 5:** Replace redundant phrases with shorter representations, preserving markers and placeholders.
   - **Step 6:** Apply context-aware compression, adjusting intensity based on section importance (e.g., system prompts > few-shot examples).

**4. Reassembly:**
   - **Step 7:** Combine compressed sections using original markers to maintain structure.

**5. Validation:**
   - **Step 8:** Test the compressed prompt in real-world scenarios.
   - **Step 9:** Measure compression ratio and performance impact.

This algorithm ensures structured prompts are compressed effectively while preserving essential elements, enhancing efficiency without compromising functionality.
