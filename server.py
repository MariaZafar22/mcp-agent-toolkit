"""
server.py - My first MCP server (Day 17 task)

This server exposes 6 tools to any MCP client / AI agent:
    1. calculator       - safely evaluate a math expression
    2. get_current_time - current date/time in a timezone
    3. word_count       - count words/characters in a text
    4. save_note        - save a text note to disk   (WRITE tool)
    5. list_notes       - list all saved notes
    6. read_note        - read one saved note

Run it directly to check that it starts:
    python server.py
(it will wait silently for an MCP client on stdin/stdout - that is normal)

Or inspect it visually:
    npx @modelcontextprotocol/inspector python server.py
"""

import ast
import operator
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The MCP Python SDK renamed FastMCP -> MCPServer in v2. Support both versions.
try:
    from mcp.server.mcpserver import MCPServer as _Server  # mcp >= 2.0
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

mcp = _Server("my-first-mcp-server")

# SAFETY: notes can only be written inside this one folder (sandbox).
NOTES_DIR = Path(__file__).parent / "notes"
NOTES_DIR.mkdir(exist_ok=True)

MAX_NOTE_CHARS = 5000


def log(msg: str) -> None:
    # stdout is reserved for the MCP protocol, so server logs go to stderr.
    print(f"[server] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- calculator
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent too large (max 100).")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Only numbers and + - * / ** % // ( ) are allowed.")


@mcp.tool()
def calculator(expression: str) -> str:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression such as "25 * 48 + 10" or "(5 + 3) ** 2".
    """
    log(f"calculator({expression!r})")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree.body)
    except ZeroDivisionError:
        raise ToolError("Division by zero is not allowed.")
    except SyntaxError:
        raise ToolError(f"'{expression}' is not a valid math expression.")
    except ValueError as e:
        raise ToolError(str(e))
    return f"{expression} = {result}"


# ---------------------------------------------------------------------- time
@mcp.tool()
def get_current_time(timezone: str = "Asia/Karachi") -> str:
    """Get the current date and time in a given IANA timezone.

    Args:
        timezone: IANA timezone name, e.g. "Asia/Karachi", "UTC", "America/New_York".
    """
    log(f"get_current_time({timezone!r})")
    try:
        now = datetime.now(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError(
            f"Unknown timezone '{timezone}'. Use a name like 'Asia/Karachi' or 'UTC'."
        )
    return now.strftime(f"%A, %d %B %Y, %I:%M %p ({timezone})")


# ---------------------------------------------------------------- word count
@mcp.tool()
def word_count(text: str) -> str:
    """Count the words, characters and sentences in a piece of text.

    Args:
        text: The text to analyse.
    """
    log(f"word_count(len={len(text)})")
    words = len(text.split())
    chars = len(text)
    sentences = len([s for s in re.split(r"[.!?]+", text) if s.strip()])
    return f"words={words}, characters={chars}, sentences={sentences}"


# --------------------------------------------------------------------- notes
def _note_path(title: str) -> Path:
    """Turn a title into a safe filename inside NOTES_DIR (blocks path traversal)."""
    safe = re.sub(r"[^A-Za-z0-9_\- ]", "", title).strip().replace(" ", "_")
    if not safe:
        raise ToolError("Note title must contain letters or numbers.")
    return NOTES_DIR / f"{safe[:60]}.txt"


@mcp.tool()
def save_note(title: str, content: str) -> str:
    """Save a text note to disk (creates or overwrites the note).

    Args:
        title: Short title of the note, e.g. "math_result".
        content: The text to store in the note.
    """
    log(f"save_note({title!r})")
    if len(content) > MAX_NOTE_CHARS:
        raise ToolError(f"Note too long (max {MAX_NOTE_CHARS} characters).")
    path = _note_path(title)
    path.write_text(content, encoding="utf-8")
    return f"Saved note '{path.stem}' ({len(content)} characters)."


@mcp.tool()
def list_notes() -> str:
    """List the titles of all saved notes."""
    log("list_notes()")
    names = sorted(p.stem for p in NOTES_DIR.glob("*.txt"))
    return "Saved notes: " + ", ".join(names) if names else "No notes saved yet."


@mcp.tool()
def read_note(title: str) -> str:
    """Read the content of a saved note.

    Args:
        title: Title of the note to read.
    """
    log(f"read_note({title!r})")
    path = _note_path(title)
    if not path.exists():
        raise ToolError(f"Note '{title}' does not exist. Use list_notes to see all notes.")
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    log("MCP server starting (stdio transport) - waiting for a client...")
    mcp.run()  # default transport = stdio
