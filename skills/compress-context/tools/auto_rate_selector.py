def skip_heuristics(context):
    words = context.split()
    return len(words) < 5

def select_rate(context, question=None) -> float:
    def count_numbers(text):
        import re
        return len(re.findall(r'\d+\.?\d*|\.\d+', text))
    
    if skip_heuristics(context):
        return 1.0
    if question and ("summarize" in question.lower() or "overview" in question.lower()):
        return 0.5
    words = context.split()
    numeric_density = count_numbers(context) / len(words) if words else 0
    return 0.9 if numeric_density > 0.05 else 0.7
