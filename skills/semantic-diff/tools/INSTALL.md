# semdiff — Install

## Default: slim CLI (recommended — every host, ~18M, no MCP/cryptography)

```bash
bash skills/semantic-diff/tools/install.sh
```

Installs only the core runtime (`tree-sitter` + the 4 per-language grammars) and
wires the `semdiff-cli` launcher. The agent re-reads files via Bash:

```bash
skills/semantic-diff/tools/semdiff-cli read path/to/file.py --session <id>
skills/semantic-diff/tools/semdiff-cli clear --session <id>
```

Works identically on Claude Code, Codex, Cursor, Gemini — anything with a shell.
Requires Python ≥ 3.9.

**Reclaiming space after upgrading from a pre-v1.11 install:** the old fat
`tree-sitter-languages` bundle (~86M) pins `tree-sitter<0.22`, so an in-place
`pip install` won't shrink an existing venv (it stays on the working fat
fallback). To get the slim ~18M install, recreate the venv:

```bash
rm -rf skills/semantic-diff/tools/.venv && bash skills/semantic-diff/tools/install.sh
```

## Option A: MCP server (optional — native `read_file_smart` tool)

```bash
bash skills/semantic-diff/tools/install.sh --mcp   # adds mcp + cryptography (~24M)
```

Or manually (Python ≥ 3.10, MCP SDK requirement):

```bash
# 1. Install deps
pip install -r skills/semantic-diff/tools/requirements-mcp.txt

# 2. Clone this repo (or copy the semdiff/ directory)
git clone https://github.com/<org>/semdiff
cd semdiff

# 3. Register with your MCP client
```

### Claude Code

```bash
claude mcp add semdiff \
  --scope project \
  -- python /absolute/path/to/semdiff/semdiff_mcp/server.py
```

Or add manually to the project-local MCP config supported by your client:
```json
{
  "semdiff": {
    "command": "python",
    "args": ["/absolute/path/to/semdiff/semdiff_mcp/server.py"]
  }
}
```

### Cursor / Cline / Zed / Windsurf / Continue

Add to your client's MCP config (format varies slightly per client). All use the
same `command + args` pattern:
```json
{
  "semdiff": {
    "command": "python",
    "args": ["/path/to/semdiff_mcp/server.py"]
  }
}
```

## Option B: Claude Code plugin (one-click install for CC users)

*(Planned — wraps the MCP server with a Claude Code plugin manifest so users
can run `/plugin install semdiff` without editing config.)*

## Option C: CLI-only (no agent integration)

```bash
python -m semdiff.cli read /path/to/file.py --session my-session
```

## Usage — what the agent sees

After install, the agent has access to three new tools:

- `read_file_smart(path, session_id)` — AST-aware file read with session-level
  diff-on-reread.
- `snapshot_clear(session_id)` — drop cached snapshots.
- `snapshot_status(session_id)` — list currently-cached files.

On first read of a file within a session: full file contents.
On subsequent reads: only changed functions/classes + stubs of unchanged ones.

### Measured savings

argparse.py, 2575 lines:
| scenario | tokens | savings |
|---|---:|---:|
| first read (full) | 19,280 | — |
| re-read after 2 method edits | **859** | **95.5%** |
| stable re-read (no changes) | **101** | **99.5%** |

## Option B (built): Claude Code plugin directory

The `plugin/` subdirectory contains a Claude Code plugin manifest that wraps the MCP server.

To install locally:
```bash
# Point Claude Code at the plugin directory
claude plugin install /absolute/path/to/semdiff/plugin
```

Or publish via a plugin marketplace. After install, `/plugin list` shows semdiff
and the MCP tools become available automatically.

The plugin `.mcp.json` launches `semdiff_mcp/server.py` via Python. Requires Python ≥ 3.10 and `pip install -r requirements-mcp.txt` on the user's system.

## Project-local installer

Use the bundled helper to print or apply the relevant install path:

```bash
bash projects/semdiff/install.sh --project
```

It prefers the plugin path when `claude` is available and falls back to the MCP server command.
