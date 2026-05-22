import json
import requests
from pipeline_v2 import compress
import time

def evaluate_compression_rates():
    with open('bench/data/adversarial_qa_10.json', 'r') as f:
        data = json.load(f)
    
    rates = [1.0, 0.5, 0.3]
    results = {rate: {'scores': [], 'latencies': []} for rate in rates}
    
    for item in data:
        context = item['context']
        question = item['question']
        answer = item['answer']
        
        for rate in rates:
            if rate < 1.0:
                ctx = compress(context, rate)
            else:
                ctx = context
            
            prompt = f"CONTEXT: {ctx}\n\nQUESTION: {question}\nANSWER:"
            
            start_time = time.time()
            response = requests.post(
                'http://127.0.0.1:11434/api/generate',
                json={
                    'model': 'phi4:14b',
                    'prompt': prompt,
                    'stream': False
                }
            )
            end_time = time.time()
            
            latency = end_time - start_time
            
            if response.status_code == 200:
                generated_answer = response.json()['response']
                score = 1 if generated_answer.strip() == answer.strip() else 0
            else:
                score = 0
            
            results[rate]['scores'].append(score)
            results[rate]['latencies'].append(latency)
    
    for rate in rates:
        avg_score = sum(results[rate]['scores']) / len(results[rate]['scores'])
        avg_latency = sum(results[rate]['latencies']) / len(results[rate]['latencies'])
        print(f"Rate {rate}: Avg Score={avg_score:.3f}, Avg Latency={avg_latency:.3f}s")

evaluate_compression_rates()
