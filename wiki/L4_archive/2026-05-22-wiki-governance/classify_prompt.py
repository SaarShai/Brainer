import re

def classify_prompt(user_text):
    # Define patterns and associated intents/skills
    patterns = [
        ('plan', r'\b(plan|strategy|schedule|organize|timeline)\b', 'project_management'),
        ('decision', r'\b(decide|choose|option|evaluate|consider)\b', 'decision_making'),
        ('debug', r'\b(error|bug|fix|issue| troubleshoot)\b', 'problem_solving'),
        ('ask', r'\b(what|how|why|when|where|who|which|can|could|should)\b', 'information_retrieval')
    ]
    
    # Initialize counters
    matches = {'plan':0, 'decision':0, 'debug':0, 'ask':0}
    
    # Check each pattern against the text
    for intent, pattern, skill in patterns:
        if re.search(pattern, user_text.lower()):
            matches[intent] += 1
    
    # Determine primary intent based on most matches
    max_count = max(matches.values())
    if max_count == 0:
        primary_intent = 'ask'
    else:
        primary_intent = [k for k, v in matches.items() if v == max_count][0]
    
    # Calculate confidence (number of matched keywords / total words)
    word_count = len(user_text.split())
    confidence = round((max_count / word_count) * 100) if word_count > 0 else 50
    
    # Default to 'ask' if no clear intent
    if max_count == 0:
        primary_intent = 'ask'
        confidence = 30
    
    return {
        'intent': primary_intent,
        'confidence': confidence,
        'suggested_skill': next((skill for intent, pattern, skill in patterns if intent == primary_intent), 'general')
    }
