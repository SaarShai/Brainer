---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

### Migration Path from Context-Keeper v1 to v2

#### 1. **Migration Tool**
- Create a standalone Python tool `migrate.py` that converts v1 sessions to v2 format:
  - Reads markdown files from `sessions/`
  - Parses content into structured data
  - Writes data to appropriate L0-L4 directories in v2 format
- Key features:
  - Dry-run mode (`--dry-run`) to preview changes without modifying files
  - Verbose output (`--verbose`) for detailed progress reporting
  - Skip already migrated files (`--skip-migrated`)

#### 2. **Compatibility Shim**
- Implement a compatibility layer in the main application code:
```python
class ContextKeeperShim:
    def __init__(self):
        self.v1_path = "sessions/"
        self.v2_path = "context/"

    def get_session(self, session_id):
        # Try v2 format first
        v2_file = f"{self._get_v2_path(session_id)}.md"
        if os.path.exists(v2_file):
            return self._read_v2_file(v2_file)
        
        # Fallback to v1 format
        v1_file = f"{self.v1_path}{session_id}.md"
        if os.path.exists(v1_file):
            return self._read_v1_file(v1_file)
        
        raise FileNotFoundError(f"No session found for ID: {session_id}")

    def _get_v2_path(self, session_id):
        # Calculate L0-L4 path based on session_id
        hash = str(uuid.uuid5(uuid.NAMESPACE_URL, session_id))
        return os.path.join(
            self.v2_path,
            hash[:2],  # L1
            hash[2:4],  # L2
            hash[4:6],  # L3
            hash[6:8]   # L4
        )

    def _read_v1_file(self, path):
        # Convert v1 markdown to structured data
        with open(path, 'r') as f:
            content = f.read()
        return {
            'content': content,
            'metadata': self._parse_v1_metadata(content)
        }

    def _parse_v1_metadata(self, content):
        # Extract metadata from v1 markdown format
        metadata = {}
        lines = content.split('\n')
        for line in lines:
            if line.startswith('#'):
                key, value = line[2:].split(':', 1)
                metadata[key.strip()] = value.strip()
        return metadata
```

#### 3. **Migration Process**
- Run `python migrate.py --verbose` to convert all v1 sessions to v2 format
- Verify data integrity by comparing session counts and content hashes
- Remove old v1 files after successful migration (`--delete-v1` flag)

#### 4. **Deprecation Plan**
- Keep compatibility shim for at least one major version
- Add deprecation warnings when accessing v1 sessions
- Phase out v1 support in a future release

This approach ensures seamless transition while maintaining backward compatibility during the migration period.
