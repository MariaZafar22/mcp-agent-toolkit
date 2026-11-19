"""
agent.py - MCP-powered AI agent (Day 17 task)

Flow:
    user request
        -> agent asks the LLM (with the MCP tool list)
        -> LLM decides which tool to call
        -> agent calls the tool on the MCP server
        -> result goes back to the LLM
        -> (repeat for multi-step) -> final answer

Usage:
    python agent.py "What is 25 * 48?"            # one request
    python agent.py                                 # interactive chat
    python agent.py --demo "..."                    # offline mode, no API key needed
    python agent.py --auto-approve "..."            # don't ask before write tools

Environment variables:
    ANTHROPIC_API_KEY   your key (if missing, the agent falls back to --demo mode)
    ANTHROPIC_MODEL     optional, default: claude-sonnet-5-5
"""

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_PATH = Path(__file__).parent / "server.py"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
API_URL = "https://api.anthropic.com/v1/messages"
MAX_STEPS = 8  # safety: stop endless tool loops

# SAFETY: tools that change something on disk need the user's approval.
WRITE_TOOLS = {"save_note"}

SYSTEM_PROMPT = (
    "You are a helpful assistant connected to an MCP server that provides tools. "
    "Use the tools whenever they help. For multi-step requests, call tools one after "
    "another and use earlier results in later calls. If a tool returns an error, "
    "explain it simply or try a corrected call. Finish with a short, clear answer."
)


# ------------------------------------------------------------------ helpers
def banner(title: str) -> None:
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def result_to_text(result) -> str:
    parts = [c.text for c in result.content if getattr(c, "text", None)]
    return "\n".join(parts) if parts else "(empty result)"


def ask_permission(name: str, args: dict, auto: bool) -> bool:
    if name not in WRITE_TOOLS or auto:
        return True
    answer = input(f"  [PERMISSION] Allow '{name}' with {args}? (y/n): ").strip().lower()
    return answer in ("y", "yes")


async def run_tool(session: ClientSession, name: str, args: dict, auto: bool) -> tuple[str, bool]:
    """Call one MCP tool. Returns (text, is_error)."""
    print(f"\n  >> TOOL CALL : {name}({json.dumps(args, ensure_ascii=False)})")
    if not ask_permission(name, args, auto):
        print("  << DENIED by user")
        return "The user denied permission for this tool call.", True
    try:
        result = await session.call_tool(name, args)
    except Exception as e:  # protocol / connection errors
        text, is_error = f"Tool call failed: {e}", True
    else:
        is_error = bool(getattr(result, "is_error", getattr(result, "isError", False)))  # v2 / v1 names
        text = result_to_text(result)
    label = "ERROR " if is_error else "RESULT"
    print(f"  << TOOL {label}: {text}")
    return text, is_error


# --------------------------------------------------------------- Claude mode
def call_claude(api_key: str, messages: list, tools: list) -> dict:
    body = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "tools": tools,
            "messages": messages,
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Anthropic API error {e.code}: {e.read().decode()[:300]}")


async def run_with_claude(session, tools, user_text, api_key, auto) -> str:
    claude_tools = [
        {
            "name": t.name,
            "description": t.description or "",
            # mcp v2 calls it input_schema, mcp v1 calls it inputSchema
            "input_schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema"),
        }
        for t in tools
    ]
    messages = [{"role": "user", "content": user_text}]

    for step in range(1, MAX_STEPS + 1):
        reply = await asyncio.to_thread(call_claude, api_key, messages, claude_tools)
        messages.append({"role": "assistant", "content": reply["content"]})

        tool_uses = [b for b in reply["content"] if b["type"] == "tool_use"]
        if not tool_uses:  # no tool needed -> this is the final answer
            return "".join(b.get("text", "") for b in reply["content"] if b["type"] == "text")

        print(f"\n--- step {step}: Claude decided to use {len(tool_uses)} tool(s) ---")
        tool_results = []
        for tu in tool_uses:
            text, is_error = await run_tool(session, tu["name"], tu["input"], auto)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": text,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "Stopped: too many steps (safety limit reached)."


# ---------------------------------------------------------------- demo mode
async def run_demo(session, user_text, auto) -> str:
    """A tiny rule-based 'brain' so the project works without any API key.
    It plays the same role as the LLM: pick tools, use results, answer."""
    low = user_text.lower()
    facts = []  # results collected from tools
    print("\n--- demo planner: choosing tools from keywords ---")

    m = re.search(r"(\d[\d\s.+\-*/()%]*[\d)])", user_text)
    if m and re.search(r"calc|what is|\d\s*[+\-*/%]\s*\d", low):
        text, err = await run_tool(session, "calculator", {"expression": m.group(1).strip()}, auto)
        facts.append(text)

    if "time" in low or "date" in low:
        tz = re.search(r"\b(?:in|for)\s+([A-Z][A-Za-z]+/[A-Za-z_]+|UTC)\b", user_text)
        args = {"timezone": tz.group(1)} if tz else {}
        text, err = await run_tool(session, "get_current_time", args, auto)
        facts.append(text)

    if "word count" in low or "count words" in low:
        q = re.search(r"[\"'](.+?)[\"']", user_text)
        if q:
            text, err = await run_tool(session, "word_count", {"text": q.group(1)}, auto)
            facts.append(text)

    if "list" in low and "note" in low:
        text, err = await run_tool(session, "list_notes", {}, auto)
        facts.append(text)

    if "read" in low and "note" in low:
        t = re.search(r"(?:called|named|titled)\s+[\"']?([\w\- ]+?)[\"']?\s*$", user_text.strip())
        if t:
            text, err = await run_tool(session, "read_note", {"title": t.group(1)}, auto)
            facts.append(text)

    if "save" in low and "note" in low:
        t = re.search(r"(?:called|named|titled)\s+[\"']?([\w\-]+)[\"']?", user_text)
        title = t.group(1) if t else "demo_note"
        content = " | ".join(facts) if facts else "Saved by the demo agent."
        text, err = await run_tool(session, "save_note", {"title": title, "content": content}, auto)
        facts.append(text)

    if not facts:
        return "Demo mode could not match a tool. Try: 'Calculate 25*48 and save it in a note called math'."
    return "Here is what I found:\n- " + "\n- ".join(facts)


# --------------------------------------------------------------------- main
async def handle_request(session, tools, text, demo, api_key, auto) -> None:
    banner("USER REQUEST")
    print(text)
    try:
        if demo:
            answer = await run_demo(session, text, auto)
        else:
            answer = await run_with_claude(session, tools, text, api_key, auto)
    except Exception as e:
        answer = f"Agent error: {e}"
    banner("FINAL ANSWER")
    print(answer)


async def main() -> None:
    parser = argparse.ArgumentParser(description="MCP-powered AI agent")
    parser.add_argument("prompt", nargs="*", help="request for the agent (omit for chat mode)")
    parser.add_argument("--demo", action="store_true", help="offline mode (no API key)")
    parser.add_argument("--auto-approve", action="store_true", help="skip permission prompts")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    demo = args.demo or not api_key
    if demo and not args.demo:
        print("[!] ANTHROPIC_API_KEY not set -> running in DEMO mode (rule-based, offline).")

    server = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            banner("CONNECTED TO MCP SERVER")
            print(f"Server script : {SERVER_PATH.name}")
            print(f"Brain         : {'demo (rule-based)' if demo else MODEL}")

            tools = (await session.list_tools()).tools
            banner(f"AVAILABLE MCP TOOLS ({len(tools)})")
            for t in tools:
                first_line = (t.description or "").strip().splitlines()[0]
                print(f"  - {t.name:<16} {first_line}")

            if args.prompt:
                await handle_request(session, tools, " ".join(args.prompt), demo, api_key, args.auto_approve)
                return

            print("\nChat mode - type a request, or 'exit' to quit.")
            while True:
                try:
                    text = input("\nYou > ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if text.lower() in ("exit", "quit", ""):
                    break
                await handle_request(session, tools, text, demo, api_key, args.auto_approve)


if __name__ == "__main__":
    asyncio.run(main())
