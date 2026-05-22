import re

def should_compress(text):
    """
    Determine if text compression should be skipped based on specific criteria.
    
    Args:
        text (str): Input text to evaluate for compression eligibility.
        
    Returns:
        dict: Dictionary with 'skip' (bool) and 'reason' (str) keys.
    """
    # Check digit density
    digits = len(re.findall(r'\d', text))
    if len(text) > 0 and digits / len(text) > 0.2:
        return {'skip': True, 'reason': 'High digit density'}
    
    # Check table density
    lines = text.split('\n')
    total_lines = len(lines)
    table_lines = sum(1 for line in lines if '|' in line)
    if total_lines > 0 and (table_lines / total_lines) > 0.3:
        return {'skip': True, 'reason': 'High table density'}
    
    # Check code fence count
    fences = len(re.findall(r'```', text))
    if fences > 2:
        return {'skip': True, 'reason': 'Too many code fences'}
    
    # Check legal-text markers
    lower_text = text.lower()
    if re.search(r'\b(hereunder|shall|pursuant to|whereas)\b', lower_text):
        return {'skip': True, 'reason': 'Legal text detected'}
    
    # No reasons to skip
    return {'skip': False, 'reason': ''}
