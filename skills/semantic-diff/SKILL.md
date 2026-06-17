---
name: semantic-diff
description: AST-node-level diff for file re-reads. Use whenever you'd re-read a file you've read before — the skill returns only the changed AST nodes, not the full file. 95.5% token savings measured on argparse.py (2575 lines, 2 method edits). Default runtime is a Bash CLI (works on every host); an optional MCP server adds a native read_file_smart tool. Supports Python, JavaScript, TypeScript, Rust.
effort: low
tools: [Bash, Read]
---

# semantic-diff (semdiff)

## What it does

Maintains a per-session AST snapshot of every file you read through it. On a
re-read of the same file, it returns only the changed nodes (functions, classes,
methods, structs) plus a compact summary of unchanged structure — not the full
file. Tree-sitter under the hood.

Measured on argparse.py (2575 lines, 19,280 tokens unfiltered):
- 2 method edits → 859 tokens returned (95.5% savings).
- No edits, stable re-read → ~100 tokens returned (99.5% savings).

Break-even is the **second** re-read of a file within a session — one-shot reads
gain nothing, so route a file through it only when you expect to read it again.

## Supported languages

Python, JavaScript, TypeScript, Rust (`.py .js .jsx .mjs .ts .tsx .rs`).
Other extensions fall back to a normal full read. Additional grammars by PR.

## Usage — CLI (default, every host)

`./install.sh` wires this automatically. The agent re-reads a file via the
launcher instead of the native Read tool:

```bash
# first read of a file in a session → full contents, caches the AST
skills/semantic-diff/tools/semdiff-cli read path/to/file.py --session <id>
# later reads in the same session → only changed nodes + unchanged summary
skills/semantic-diff/tools/semdiff-cli read path/to/file.py --session <id>
# drop the session's snapshots to force a fresh full read
skills/semantic-diff/tools/semdiff-cli clear --session <id>
```

Use a stable `--session` per working context (e.g. the task or branch). Add
`--meta` to print mode/counts to stderr. The launcher prefers a skill-local
`.venv` if present, else system `python3`; no MCP, no `cryptography`.

## Usage — MCP (optional, opt-in)

For a native `read_file_smart` tool (Claude Code, Cursor, etc.) instead of the
Bash CLI — heavier (`mcp` pulls `cryptography` ~24M):

```bash
bash skills/semantic-diff/tools/install.sh --mcp   # installs mcp + registers server
```

Then call `read_file_smart(path, session_id)`, `snapshot_clear(session_id)`,
`snapshot_status(session_id)`. See `tools/semdiff_mcp/server.py` for signatures
and `tools/INSTALL.md` for per-host registration.

## Files

```
tools/
├── semdiff/             # AST diff library (core.py: get_parser slim+fallback)
├── semdiff-cli          # portable Bash launcher (default runtime)
├── semdiff_mcp/         # optional MCP server
├── requirements.txt     # slim CORE: tree-sitter + 4 grammars (~9-18M)
├── requirements-mcp.txt # optional: + mcp/cryptography
├── plugin/              # CC plugin wrapper (.claude-plugin/, .mcp.json)
├── tests/
├── install.sh           # default = slim CLI; --mcp adds the server
└── INSTALL.md           # per-host install
```
