"""
Agent — Agentic loop that talks to Ollama with tool use.
Runs tools, feeds results back, continues until final text response.
"""

import json
import time
import asyncio

import httpx

from nex.cli import renderer, tools
from nex.cli.session import Session

OLLAMA_URL = "http://localhost:11434"
MAX_TOOL_ROUNDS = 10


class Agent:
    """The core agentic loop: user message → model → tools → model → ... → response."""

    def __init__(self, model: str, cwd: str, session: "Session", auto_approve: bool = False):
        self.model = model
        self.cwd = cwd
        self.session = session
        self.auto_approve = auto_approve
        self._interrupted = False

    def interrupt(self):
        """Signal the agent to stop after the current step."""
        self._interrupted = True

    async def run(self, user_message: str) -> str | None:
        """
        Execute the agentic loop for a user message.
        Returns the final assistant text response.
        """
        self._interrupted = False

        # Add user message to transcript
        self.session.add_message("user", user_message)

        # Build messages for API
        messages = self.session.build_messages()

        spinner = renderer.Spinner("Thinking")
        spinner.start()

        total_tool_calls = 0
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for round_num in range(MAX_TOOL_ROUNDS):
                    if self._interrupted:
                        spinner.stop()
                        renderer.info("Interrupted.")
                        return None

                    # Call Ollama
                    payload = {
                        "model": self.model,
                        "messages": messages,
                        "tools": tools.TOOLS,
                        "stream": False,
                    }

                    try:
                        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                        resp.raise_for_status()
                    except httpx.ConnectError:
                        spinner.stop()
                        renderer.error("Cannot connect to Ollama. Is it running? (ollama serve)")
                        return None
                    except httpx.TimeoutException:
                        spinner.stop()
                        renderer.error("Request timed out. The model may be overloaded.")
                        return None

                    data = resp.json()
                    msg = data.get("message", {})
                    tool_calls = msg.get("tool_calls")

                    # Track token usage from response
                    eval_count = data.get("eval_count", 0)
                    prompt_eval = data.get("prompt_eval_count", 0)
                    self.session.update_tokens(prompt_eval, eval_count)

                    if not tool_calls:
                        # Final text response
                        spinner.stop()
                        reply = msg.get("content", "").strip() or "Done."
                        elapsed = time.time() - start_time

                        self.session.add_message("assistant", reply)
                        renderer.assistant_text(reply)

                        # Show stats
                        stats = []
                        if total_tool_calls > 0:
                            stats.append(f"{total_tool_calls} tool call{'s' if total_tool_calls != 1 else ''}")
                        stats.append(f"{elapsed:.1f}s")
                        renderer.info(f"  {renderer.DIM}{'  ·  '.join(stats)}{renderer.RESET}")

                        return reply

                    # Process tool calls
                    spinner.stop()
                    messages.append(msg)

                    for tc in tool_calls:
                        func = tc.get("function", {})
                        name = func.get("name", "")
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}

                        total_tool_calls += 1

                        # Display tool call
                        args_summary = _summarize_args(name, args)
                        renderer.tool_start(name, args_summary)

                        # Execute tool
                        result = await tools.execute(name, args, self.cwd, self.auto_approve)

                        # Append tool result to messages
                        messages.append({"role": "tool", "content": result})

                    # Continue loop — model will process tool results
                    spinner = renderer.Spinner(f"Processing ({round_num + 2}/{MAX_TOOL_ROUNDS})")
                    spinner.start()

                # Exceeded max tool rounds
                spinner.stop()
                renderer.info(f"Reached maximum tool rounds ({MAX_TOOL_ROUNDS}).")
                return "Completed."

        except Exception as e:
            spinner.stop()
            renderer.error(f"Agent error: {e}")
            return None


def _summarize_args(name: str, args: dict) -> str:
    """Create a short summary of tool args for display."""
    match name:
        case "read_file":
            p = args.get("path", "")
            r = ""
            if args.get("start_line"):
                r = f" L{args['start_line']}-{args.get('end_line', '...')}"
            return f"{p}{r}"
        case "write_file":
            return args.get("path", "")
        case "str_replace":
            return args.get("path", "")
        case "bash":
            cmd = args.get("command", "")
            return cmd[:60] + ("..." if len(cmd) > 60 else "")
        case "search_files":
            return f"/{args.get('pattern', '')}/"
        case "glob":
            return args.get("pattern", "")
        case "list_directory":
            return args.get("path", ".")
        case "inspect_file":
            return args.get("path", "")
        case "run_python":
            return args.get("description", "script")[:50]
        case "run_sql":
            q = args.get("query", "")
            return q[:60] + ("..." if len(q) > 60 else "")
        case "run_node":
            return args.get("description", "script")[:50]
        case "preview_data":
            return args.get("path", "")
        case "save_output":
            return args.get("path", "")
        case _:
            return ""
