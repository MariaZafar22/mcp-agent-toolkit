# MCP-Powered AI Agent (Day 17)

A small project that shows how **Model Context Protocol (MCP)** lets an AI agent discover and use tools.

- `server.py` - an MCP server with 6 custom tools
- `agent.py` - an AI agent (MCP client) that connects to the server, lets Claude choose tools, and returns a final answer

## 1. What is MCP?

MCP (Model Context Protocol) is an open standard that defines **how AI applications connect to external tools and data**. Instead of writing custom glue code for every tool and every AI app, a tool is written once as an *MCP server*, and any *MCP client* can use it.

**Why it is useful for agents:** tools are discovered at runtime (`list_tools`), have clear JSON-schema inputs, can be reused across apps, and can be updated on the server without changing the agent.

### Function calling vs MCP

| | Function calling | MCP |
|---|---|---|
| What it is | A model feature: the model returns "call function X with args Y" | A protocol: a standard way to expose and connect tools/data |
| Where tools live | Defined inside your app code | In a separate server process, reusable by any client |
| Discovery | You hard-code the tool list | Client asks the server (`tools/list`) |
| Reuse | Per app | Write once, use in many apps |

They work together: the agent gets tool definitions from MCP, the model uses function calling to pick one, and the agent runs it through MCP.

## 2. Architecture

```
 User
  |  "Calculate 25*48 and save it in a note"
  v
+------------------+   tool list + request    +-----------+
|  agent.py        | -----------------------> |  LLM      |
|  (MCP client)    | <----------------------- |  (Claude) |
|                  |   "call calculator(...)" +-----------+
+------------------+
  |  MCP over stdio (JSON-RPC): list_tools / call_tool
  v
+------------------+
|  server.py       |  calculator, get_current_time, word_count,
|  (MCP server)    |  save_note, list_notes, read_note
+------------------+
```

Agent loop: **request -> LLM picks tool -> agent calls tool via MCP -> result back to LLM -> repeat -> final answer** (max 8 steps).

## 3. Tools

| Tool | Input | Output | Type |
|---|---|---|---|
| `calculator` | `expression: str` | `"25 * 48 = 1200"` | read-only |
| `get_current_time` | `timezone: str` (default `Asia/Karachi`) | formatted date/time | read-only |
| `word_count` | `text: str` | words, characters, sentences | read-only |
| `save_note` | `title: str`, `content: str` | confirmation | **writes a file** |
| `list_notes` | none | list of note titles | read-only |
| `read_note` | `title: str` | note content | read-only |

## 4. Setup

Requires Python 3.10+.

```bash
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
```

## 5. Run

**Start / check the server** (it waits silently for a client - that is normal; press Ctrl+C to stop):

```bash
python server.py
```

**Inspect the tools visually** (optional, needs Node.js):

```bash
npx @modelcontextprotocol/inspector python server.py
```

**Run the agent with a real LLM (Claude):**

```bash
# Windows PowerShell:  $env:ANTHROPIC_API_KEY="sk-ant-..."
# Mac/Linux:           export ANTHROPIC_API_KEY="sk-ant-..."

python agent.py "What is 25 * 48 + 10?"
python agent.py "Calculate 25 * 48, get the time in Asia/Karachi, and save both results in a note called day17"
python agent.py                      # interactive chat mode
```

**Run without any API key** (offline demo, a simple rule-based planner plays the role of the LLM):

```bash
python agent.py --demo "Calculate 25 * 48, get the time in Asia/Karachi, and save everything in a note called day17"
```

Add `--auto-approve` to skip the permission question before `save_note`.

## 6. Error handling

- Tools raise `ToolError` with a clear message (division by zero, unknown timezone, missing note, bad title). The server marks the result as an error.
- The agent passes `is_error: true` back to the LLM so it can explain the problem or retry with corrected input.
- API/network errors are caught and shown as `Agent error: ...` instead of crashing.

## 7. Permissions and safety

- **Human approval:** `save_note` is a write tool, so the agent asks `y/n` before running it (skip with `--auto-approve`).
- **Sandbox:** notes can only be written inside the `notes/` folder; titles are sanitised so `../../etc/passwd` becomes `etcpasswd.txt` (no path traversal).
- **No `eval`:** the calculator parses the expression with `ast` and only allows numbers and math operators.
- **Limits:** max 5000 characters per note, max exponent 100, max 8 agent steps.
- **Least privilege:** the server exposes only these six tools - no shell, no arbitrary file access.
- **Secrets:** the API key comes from an environment variable and is never stored in the repo.

## 8. Example multi-step workflow

Request: *"Calculate 25 * 48, get the time in Asia/Karachi, and save everything in a note called day17"*

1. `calculator("25 * 48")` -> `1200`
2. `get_current_time("Asia/Karachi")` -> current date/time
3. `save_note("day17", "25 * 48 = 1200 | <time>")` -> saved
4. Final answer summarising all three results

Then: *"read the note called day17"* -> `read_note` returns the saved content.

## 9. Project structure

```
mcp-agent-project/
  server.py          MCP server (tools)
  agent.py           MCP client + AI agent loop
  requirements.txt
  notes/             where save_note stores files
  README.md
```
