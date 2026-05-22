def extract_features(text):
    """
    Extracts features from text for B49 compress_rate_auto model.
    
    Args:
        text (str): Input text to analyze
        
    Returns:
        dict: Dictionary containing extracted features:
            - digit_density: ratio of digits in text
            - clause_count: number of clauses (split by . or ,)
            - question_type: factoid, reasoning, or summary
            - domain_keywords: list of matched domain-specific keywords
            
    Features:
    1. Digit Density: Measures proportion of numeric characters
    2. Clause Count: Identifies sentence complexity via punctuation
    3. Question Type: Classifies query type using keyword analysis
    4. Domain Keywords: Matches text against predefined domain terms
    """
    
    # 1. Calculate digit density
    total_chars = len(text)
    digits = sum(1 for c in text if c.isdigit())
    digit_density = digits / total_chars if total_chars > 0 else 0
    
    # 2. Count clauses (split by . or ,)
    clauses = [c.strip() for c in re.split(r'[.,]', text) if c.strip()]
    clause_count = len(clauses)
    
    # 3. Determine question type
    question_type = 'factoid'
    if any(word in text.lower() for word in ['why', 'how']):
        question_type = 'reasoning'
    elif any(word in text.lower() for word in ['summarize', 'explain']):
        question_type = 'summary'
        
    # 4. Extract domain keywords
    # Define domain-specific keyword sets
    tech_keywords = {'algorithm', 'software', 'hardware'}
    business_keywords = {'strategy', 'finance', 'market'}
    medical_keywords = {'diagnosis', 'treatment', 'symptom'}
    
    # Split text into words and check against domains
    words = set(text.lower().split())
    domain_keywords = []
    
    if words & tech_keywords:
        domain_keywords.append('tech')
    if words & business_keywords:
        domain_keywords.append('business')
    if words & medical_keywords:
        domain_keywords.append('medical')
        
    return {
        'digit_density': digit_density,
        'clause_count': clause_count,
        'question_type': question_type,
        'domain_keywords': domain_keywords
    }
