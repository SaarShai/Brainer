---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
import re

intents = [
    {
        "name": "greeting",
        "patterns": [r"\b(hello|hi|hey|welcome)\b", r"\bgood (morning|afternoon|evening)\b"]
    },
    {
        "name": "goodbye",
        "patterns": [r"\b(goodbye|bye|farewell|see you)\b"]
    },
    {
        "name": "thanks",
        "patterns": [r"\b(thank(s)?|appreciate|grateful)\b", r"\byou're welcome\b"]
    },
    {
        "name": "help",
        "patterns": [r"\b(help|support|assist|advice)\b", r"\bI need help\b"]
    },
    {
        "name": "affirmation",
        "patterns": [r"\b(yes|okay|sure|definitely)\b", r"\bI agree\b"]
    },
    {
        "name": "denial",
        "patterns": [r"\b(no|not|never|refuse)\b", r"\bI disagree\b"]
    },
    {
        "name": "info_request",
        "patterns": [r"\b(what is|tell me about|explain|describe)\b", r"\bcan you help me with\b"]
    },
    {
        "name": "define",
        "patterns": [r"\b(define|meaning of|explanation for)\b"]
    },
    {
        "name": "how",
        "patterns": [r"\b(how to|how do I|method|process)\b"]
    },
    {
        "name": "why",
        "patterns": [r"\b(why is|reason|because)\b"]
    },
    {
        "name": "when",
        "patterns": [r"\b(when does|time|schedule|date)\b"]
    },
    {
        "name": "where",
        "patterns": [r"\b(where is|location|place|address)\b"]
    },
    {
        "name": "who",
        "patterns": [r"\b(who is|person|individual|character)\b"]
    },
    {
        "name": "which",
        "patterns": [r"\b(which one|choice|option|alternative)\b"]
    },
    {
        "name": "what",
        "patterns": [r"\b(what are|types of|kinds of|examples of)\b"]
    }
]

def classify_prompt(text):
    results = {
        "detected_intents": [],
        "confidence": 0.0
    }
    
    # Check for non-standard characters that might affect confidence
    non_standard_chars = [c for c in text if not (c.isalnum() or c.isspace())]
    
    for intent in intents:
        score = 0
        for pattern in intent["patterns"]:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
            if compiled_pattern.search(text):
                score += 1
                
        if score > 0:
            results["detected_intents"].append({
                "intent": intent["name"],
                "score": score
            })
    
    # Calculate confidence based on matches and text complexity
    base_confidence = 100.0
    num_matches = sum([intent["score"] for intent in results["detected_intents"]])
    
    # Apply penalties for non-standard characters
    penalty = min(5 * len(non_standard_chars), 30)
    confidence_adjustment = max(min(base_confidence - penalty + (num_matches * 2), 98.0), 70.0)
    
    results["confidence"] = round(confidence_adjustment, 2)
    
    return results

# Example usage
if __name__ == "__main__":
    text = "Can you explain how to make a cake?"
    print(classify_prompt(text))
```
