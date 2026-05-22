---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round5]
---

Here's a design for a Wikipedia search system using SQLite FTS5:

1. **Database Schema**:
```sql
CREATE VIRTUAL TABLE wiki_pages USING fts5(
    page_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tokenize = 'porter'
);
```

2. **Data Ingestion**:
- Parse Wikipedia XML dump
- Extract page ID, title, and content
- Insert into FTS table with:
```python
def insert_wikipedia_page(cursor, page_id, title, content):
    cursor.execute(
        "INSERT INTO wiki_pages VALUES (?, ?, ?)",
        (page_id, title, content)
    )
```

3. **Query Construction**:
- Support free-text search with optional field scoping via DSL:
  - `title:searchterm` to limit to titles
  - `content:searchterm` for body text
  - `*` wildcard support
  - `"exact phrase"` matching

4. **Search Execution**:
```python
def search_wikipedia(query, filters=None):
    query = f"({query})"  # Enclose in parentheses
    
    if filters:
        filter_clauses = []
        for field, value in filters.items():
            filter_clauses.append(f"{field}:{value}")
        query += " AND " + " AND ".join(filter_clauses)
    
    conn = sqlite3.connect("wikipedia.db")
    cursor = conn.cursor()
    
    cursor.execute(
        f"SELECT rowid, title, snippet(content) FROM wiki_pages WHERE content MATCH ? LIMIT 10",
        (query,)
    )
    
    results = []
    for row in cursor:
        page_id = row[0]
        title = row[1]
        preview = row[2].replace('<b>', '').replace('</b>', '')  # Clean up FTS highlighting
        results.append((page_id, title, preview))
        
    conn.close()
    return results
```

5. **Features**:
- Full-text search with stemming ( Porter tokenizer )
- Field-specific filtering
- Phrase matching
- Wildcard support
- Highlighting via FTS5 snippet function

6. **Example Usage**:
```python
results = search_wikipedia(
    "quantum mechanics",
    filters={"title": "physics"}
)
for page_id, title, preview in results:
    print(f"{page_id}: {title}\n{preview}\n")
```

This design provides a performant and flexible Wikipedia search system with tier-1 indexing capabilities. The FTS5 engine handles the heavy lifting of text processing and indexing, while the application layer manages query construction and result formatting.

The implementation supports:
- Efficient full-text search
- Field-specific filtering
- Highlighting of matches
- Limited to 10 results per query
- Clean, readable output format

To improve this system further, you could add:
- More sophisticated ranking algorithms
- Additional metadata fields in the index
- Caching layer for frequent queries
- Batch processing optimizations
