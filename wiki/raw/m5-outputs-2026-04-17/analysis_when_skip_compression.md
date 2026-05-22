---
type: raw
source: m5-max (deepseek-r1:32b)
date: 2026-04-17
tags: [m5-generated]
---

### Analysis: When to Skip ComCom Entirely

ComCom should be skipped entirely (rate=0.5) for content with specific signatures where compression is net-negative even with self-verify escalation:

1. **Dense Numeric Tables**  
   - These include spreadsheets, financial reports, or datasets with rows of numbers.  
   - Issue: ComCom's language model struggles to preserve numeric precision and alignment. Self-verify may miss subtle errors in number sequences, leading to data corruption.  

2. **Code Blocks**  
   - Source code in programming languages (e.g., Python, Java).  
   - Issue: Code syntax is rigid; even minor alterations can break functionality. ComCom's model lacks understanding of programming semantics, risking logical errors that self-verify cannot detect.  

3. **Legal Text**  
   - Contracts, patents, or legal documents with precise terminology.  
   - Issue: Legal language requires exact wording for enforceability. ComCom may paraphrase terms incorrectly, altering legal meaning despite self-verify checks.  

4. **Highly Structured Data**  
   - JSON, XML, or CSV files with strict formatting rules.  
   - Issue: Structural integrity is critical; compression risks breaking nested hierarchies or field alignments. Self-verify may not detect format violations.  

### Pre-Filter Detector

A lightweight detector can identify these signatures using simple heuristics:

1. **Numeric Tables**:  
   - Check for high density of numbers (e.g., >50% digits in a block).  

2. **Code Blocks**:  
   - Detect syntax markers like `{}`, `()`, or keywords like `def`, `class`.  

3. **Legal Text**:  
   - Look for legal terms (e.g., "hereby", "whereas", "shall").  

4. **Structured Data**:  
   - Identify delimiters like `<`, `>`, `[`, `]`, `{`, `}`, or commas in CSV.  

This detector ensures ComCom is skipped only where harmful, preserving savings elsewhere while avoiding quality loss.
