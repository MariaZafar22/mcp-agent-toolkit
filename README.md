# MCP Agent Toolkit

A lightweight Python project that demonstrates how the **Model Context Protocol (MCP)** lets an AI agent discover, select, and use external tools.

**What's inside**

- **`server.py`**: an MCP server that exposes 6 custom tools
- **`agent.py`**: an AI agent (MCP client) that connects to the server, lets Claude choose the right tools, and returns a final answer

---

## What is MCP?

The **Model Context Protocol (MCP)** is an open standard that defines how AI applications connect to external tools and data. A tool is written once as an **MCP server**, and any **MCP client** can use it. There is no custom integration code for each application.

**Why it matters for AI agents**

- **Runtime discovery:** the agent asks the server which tools exist (`tools/list`).
- **Clear contracts:** every tool has a JSON-schema description of its inputs.
- **Reusable:** one server works with many clients.
- **Easy to update:** tools can change on the server without touching the agent.

### Function calling vs. MCP

| | **Function calling** | **MCP** |
|---|---|---|
| **What it is** | A model feature: the model replies "call function X with arguments Y" | A protocol: a standard way to expose and connect tools and data |
| **Where tools live** | Inside your application code | In a separate server process |
| **Discovery** | Tool list is hard-coded | Client asks the server at runtime |
| **Reuse** | One application | Write once, use everywhere |

The two work together: the agent receives tool definitions through **MCP**, the model picks a tool using **function calling**, and the agent executes it back through **MCP**.

---

## Architecture

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

**Agent loop:** request, then the LLM picks a tool, the agent calls it through MCP, the result goes back to the LLM, and the cycle repeats until a final answer is ready (maximum 8 steps).

---

## Available Tools

| **Tool** | **Input** | **Output** | **Type** |
|---|---|---|---|
| `calculator` | `expression: str` | `"25 * 48 = 1200"` | Read-only |
| `get_current_time` | `timezone: str` (default `Asia/Karachi`) | Formatted date and time | Read-only |
| `word_count` | `text: str` | Words, characters, sentences | Read-only |
| `save_note` | `title: str`, `content: str` | Confirmation message | **Writes a file** |
| `list_notes` | none | List of saved note titles | Read-only |
| `read_note` | `title: str` | Note content | Read-only |

---

## Getting Started

**Requirements:** Python 3.10 or higher.

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

---

## Usage

**1. Start the server**

```bash
python server.py
```

The server waits silently for a client. This is expected. Press `Ctrl + C` to stop it.

**2. Inspect the tools visually** (optional, requires Node.js)

```bash
npx @modelcontextprotocol/inspector python server.py
```

**3. Run the agent with Claude**

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-..."
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

python agent.py "What is 25 * 48 + 10?"
python agent.py "Calculate 25 * 48, get the time in Asia/Karachi, and save both results in a note called day17"
python agent.py            # interactive chat mode
```

**4. Run without an API key** (offline demo mode)

A simple rule-based planner takes the role of the LLM, so the full tool workflow still works.

```bash
python agent.py --demo "Calculate 25 * 48, get the time in Asia/Karachi, and save everything in a note called day17"
```

Add `--auto-approve` to skip the permission prompt before `save_note`.

---

## Example Multi-Step Workflow

**Request:** *"Calculate 25 * 48, get the time in Asia/Karachi, and save everything in a note called day17"*

1. `calculator("25 * 48")` returns `1200`
2. `get_current_time("Asia/Karachi")` returns the current date and time
3. `save_note("day17", "25 * 48 = 1200 | <time>")` saves the note
4. The agent replies with a short summary of all three results

**Follow-up:** *"read the note called day17"* calls `read_note` and returns the saved content.

---

## Error Handling

- Tools raise a `ToolError` with a clear message (division by zero, unknown timezone, missing note, invalid title).
- The agent passes `is_error: true` back to the LLM, so it can explain the problem or retry with corrected input.
- API and network failures are caught and shown as `Agent error: ...` instead of crashing the program.

---

## Permissions and Safety

- **Human approval:** `save_note` writes to disk, so the agent asks for `y/n` confirmation first (skip with `--auto-approve`).
- **Sandboxed storage:** notes are written only inside the `notes/` folder. Titles are sanitized, so `../../etc/passwd` becomes `etcpasswd.txt`.
- **No `eval`:** the calculator parses expressions with `ast` and allows only numbers and math operators.
- **Hard limits:** 5,000 characters per note, exponent up to 100, and at most 8 agent steps.
- **Least privilege:** only six tools are exposed. There is no shell access and no arbitrary file access.
- **Secrets:** the API key is read from an environment variable and is never stored in the repository.

---

## Project Structure

```
mcp-agent-toolkit/
  server.py          MCP server and tools
  agent.py           MCP client and agent loop
  requirements.txt   Python dependencies
  notes/             Storage for saved notes
  README.md
```

---

## Conclusion

This project shows the complete MCP workflow in a small, readable codebase: a server that publishes tools, an agent that discovers them, and an LLM that decides which ones to call and in what order. It is a solid starting point for building larger agents. Add more tools to `server.py`, connect other MCP servers, or swap in a different model, and the same architecture keeps working.
