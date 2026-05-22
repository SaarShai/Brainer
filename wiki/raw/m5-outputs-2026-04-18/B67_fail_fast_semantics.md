---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

ComCom should refuse to compress and trigger a hard error in scenarios where compression might compromise safety, legality, or data integrity. These situations require immediate attention to prevent potential harm or non-compliance with regulations.

1. **Legal/Medical Data**: When handling sensitive information like patient records or legal documents, ComCom must ensure data remains unaltered. Compression errors here could lead to data loss or corruption, violating privacy laws (e.g., HIPAA) and endangering lives. A hard error ensures the user addresses the issue before proceeding.

2. **Financial Transactions**: Errors in compressing financial data can cause monetary discrepancies or security breaches. Hard errors prevent unauthorized access or transaction failures, safeguarding assets and maintaining trust.

3. **Mission-Critical Systems**: In aerospace or defense, any compression failure could lead to system malfunctions with catastrophic consequences. A hard error ensures operators address issues promptly, preventing accidents.

4. **Encrypted/Sensitive Data**: Compressing encrypted data might expose sensitive information. A hard error prevents potential breaches by alerting users to handle such data securely.

ComCom detects these scenarios through metadata tags or user prompts, ensuring critical processes aren't compromised silently. This approach prioritizes safety, compliance, and integrity over silent failures.
