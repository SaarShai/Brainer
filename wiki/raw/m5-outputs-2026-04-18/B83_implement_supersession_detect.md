---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round11-partial]
---

```python
import json
from datetime import datetime
import argparse
from itertools import combinations

def parse_wiki_pages(directory):
    pages = []
    for filename in directory.glob("*.json"):
        with open(filename, 'r') as f:
            content = json.load(f)
            page = {
                'title': content.get('title', ''),
                'date': datetime.fromisoformat(content['date']),
                'tags': set(content.get('tags', [])),
                'concepts': set(content.get('concepts', [])),
                'numbers': content.get('numbers', {})
            }
            pages.append(page)
    return pages

def compare_pages(page1, page2):
    newer = max(page1, page2, key=lambda x: x['date'])
    older = min(page1, page2, key=lambda x: x['date'])
    
    if newer['tags'] != older['tags']:
        return False
        
    if not newer['concepts'].intersection(older['concepts']):
        return False
    
    for key in newer['numbers']:
        if key in older['numbers']:
            diff = abs(newer['numbers'][key] - older['numbers'][key])
            avg = (newer['numbers'][key] + older['numbers'][key]) / 2
            if avg == 0:
                continue
            percent_diff = (diff / avg) * 100
            if percent_diff > 10:
                return True
    return False

def main():
    parser = argparse.ArgumentParser(description='Detect potential supersessions between wiki pages.')
    parser.add_argument('directory', type=str, help='Path to directory containing wiki pages')
    parser.add_argument('--no-dry-run', action='store_false', dest='dry_run',
                      help='Actually perform the supersession (default: dry run)')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Enable verbose output')
    parser.add_argument('--version', action='version', version='%(prog)s 1.0')
    
    args = parser.parse_args()
    
    pages = parse_wiki_pages(args.directory)
    
    if len(pages) < 2:
        print("Not enough pages to compare")
        return
    
    for page_pair in combinations(pages, 2):
        if compare_pages(*page_pair):
            newer = max(page_pair, key=lambda x: x['date'])
            older = min(page_pair, key=lambda x: x['date'])
            
            if args.verbose:
                print(f"Potential supersession detected:")
                print(f"- Newer page: {newer['title']} ({newer['date'].isoformat()})")
                print(f"- Older page: {older['title']} ({older['date'].isoformat()})")
                print("-"*50)
            else:
                print(f"Potential supersession: {newer['title']} may supersede {older['title']}")
                
    return

if __name__ == "__main__":
    main()
```
