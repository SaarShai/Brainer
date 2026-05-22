---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round8]
---

To enhance the classify_prompt.py script, we propose adding 10 new regex patterns to capture additional user intents:

1. **Login Help**
   - Pattern: r'\b(login|access)\b.*\b(help|issue|problem)'

2. **Account Recovery**
   - Pattern: r'\b(recover|reset).*\b(account|password)'

3. **Feature Request**
   - Pattern: r'\b(feature|add|include)\b.*\b(request|suggestion)'

4. **Content Feedback**
   - Pattern: r'\b(feedback|improve).*\b(content|article)'

5. **Collaboration Request**
   - Pattern: r'\b(collaborate|partner)\b.*\b(request|opportunity)'

6. **Wiki Structure Feedback**
   - Pattern: r'\b(structure|organization).*\b(feedback|improve)'

7. **Bug Report**
   - Pattern: r'\b(bug|error)\b.*\b(report|found)'

8. **Performance Issue**
   - Pattern: r'\b(slow|unresponsive).*\b(site|performance)'

9. **Security Concern**
   - Pattern: r'\b(security|vulnerability)\b.*\b(issue|report)'

10. **Translation Assistance**
    - Pattern: r'\b(translate|language).*\b(help|assistance)'

These patterns address specific user intents such as technical support, feature suggestions, feedback, and security issues, enhancing the script's ability to categorize a wider range of prompts accurately.
