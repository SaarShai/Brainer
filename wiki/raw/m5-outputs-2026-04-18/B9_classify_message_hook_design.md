---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round5]
---

```python
import re
from typing import Optional, Dict, Any

class UserPromptSubmitHook:
    def __init__(self):
        # Regex catalog for pattern matching
        self.regex_catalog = {
            'decision': r'\b(decide|choose|option[s]?|best way)\b',
            'plan': r'\b(plan|strategy|outline|schedule)\b',
            'debug': r'\b(debug|error|fix|issue|bug)\b',
            'ask': r'^what |^how |^why |^when |^where |^who '
        }
        
    def match_pattern(self, message: str) -> Optional[str]:
        """Match message against regex patterns and return category."""
        for category, pattern in self.regex_catalog.items():
            if re.search(pattern, message, re.IGNORECASE):
                return category
        return None

    def inject_template_hint(self, message: str, category: str) -> str:
        """Inject template hint into the prompt."""
        return f"[RoutingHint={category}] {message}"

    def process_message(
        self, 
        message: str,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """Process incoming message and inject routing hints."""
        try:
            category = self.match_pattern(message)
            if category:
                modified_prompt = self.inject_template_hint(message, category)
                
                # Log stdout for debugging
                print(f"[UserPromptSubmitHook] Detected {category} in message. Injected hint.")
                
                return {
                    'message': modified_prompt,
                    'user_id': user_id,
                    'session_id': session_id,
                    'metadata': {'routing_category': category}
                }
            else:
                # No pattern matched, pass through
                print(f"[UserPromptSubmitHook] No pattern detected. Passing through.")
                return {
                    'message': message,
                    'user_id': user_id,
                    'session_id': session_id,
                    'metadata': {'routing_category': None}
                }
        except Exception as e:
            # Error handling
            print(f"[UserPromptSubmitHook] Error processing message: {str(e)}")
            raise

# Example usage:
hook = UserPromptSubmitHook()
result = hook.process_message(
    "Help me debug my code",
    user_id="user123",
    session_id="session456"
)
print(result)  # Output shows injected hint and routing metadata
```
