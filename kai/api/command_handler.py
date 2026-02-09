"""
Command Handler — Kai's brain powered by Ollama LLM with real tool execution.
The LLM can run shell commands, create/read files, open apps, and more.
"""

import asyncio
import datetime
import json
import os
import platform
from pathlib import Path

import httpx

from kai.core.event_bus import EventBus
from kai.utils.logger import setup_logger

logger = setup_logger(__name__)

OLLAMA_URL = "http://localhost:11434"
MODEL = "llama3.2"
MAX_HISTORY = 20
MAX_TOOL_ROUNDS = 5  # Max back-and-forth tool calls per request

SYSTEM_PROMPT = """You are Kai, a personal AI assistant running locally on the user's Mac.
You are inspired by Jarvis from Iron Man — intelligent, helpful, slightly witty, and always respectful.
Keep responses concise (1-3 sentences) unless the user asks for detail.
You speak in a natural, conversational tone.

Current system info:
- Platform: {platform}
- Machine: {machine}
- User: {user}
- Home directory: {home}
- Current time: {time}
- Current date: {date}

IMPORTANT RULES:
- When the user asks you to DO something (create a file, run a command, open an app, etc.), you MUST use the provided tools to actually do it. Do NOT just say you did it — call the tool.
- When you use a tool, report what actually happened based on the tool result.
- You have full access to the local machine through tools. Use them.
- Do NOT use markdown formatting in your spoken responses — speak naturally."""

# ─── Tool Definitions (Ollama format) ─────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Execute a shell command on the local machine and return stdout/stderr. Use this for any terminal operation: creating files, moving files, installing software, checking system info, running scripts, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g. 'echo hello > ~/Desktop/test.txt', 'ls -la ~/Documents', 'brew install wget')",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create or overwrite a file with the given content at the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute file path (e.g. '/Users/jazz/Desktop/notes.txt'). Use ~ for home directory.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read and return the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute file path to read. Use ~ for home directory.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and folders in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Use ~ for home directory.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for files by name using macOS Spotlight.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The filename or partial name to search for.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open a macOS application or file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Application name (e.g. 'Safari', 'Finder') or file path to open.",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


def _build_system_prompt() -> str:
    now = datetime.datetime.now()
    return SYSTEM_PROMPT.format(
        platform=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        user=os.getenv("USER", "unknown"),
        home=str(Path.home()),
        time=now.strftime("%I:%M %p"),
        date=now.strftime("%A, %B %d, %Y"),
    )


class CommandHandler:
    """Processes commands via Ollama LLM with tool calling for real actions."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.history: list[dict] = []
        self.tts_process: asyncio.subprocess.Process | None = None

    async def start(self):
        self.event_bus.subscribe("system.command", self._on_command)
        logger.info("Command handler ready.")

    async def _on_command(self, data: dict):
        command = data.get("command", "").strip()
        if not command:
            return

        logger.info(f"Command received: {command}")

        try:
            response = await self._process_with_tools(command)

            if response:
                logger.info(f"Response ready ({len(response)} chars)")
                await self.event_bus.publish("command.response", {
                    "text": response,
                    "command": command,
                })
                asyncio.create_task(self._speak(response))
        except Exception as e:
            logger.error(f"Command processing error: {e}", exc_info=True)
            try:
                await self.event_bus.publish("command.response", {
                    "text": f"Sorry, something went wrong: {e}",
                    "command": command,
                })
            except Exception:
                pass

    async def _process_with_tools(self, user_message: str) -> str:
        """Send message to Ollama with tools. Execute any tool calls. Return final response."""
        self.history.append({"role": "user", "content": user_message})
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        messages = [
            {"role": "system", "content": _build_system_prompt()},
            *self.history,
        ]

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for round_num in range(MAX_TOOL_ROUNDS):
                    resp = await client.post(
                        f"{OLLAMA_URL}/api/chat",
                        json={
                            "model": MODEL,
                            "messages": messages,
                            "tools": TOOLS,
                            "stream": False,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data.get("message", {})

                    tool_calls = msg.get("tool_calls")

                    if not tool_calls:
                        # No tool calls — this is the final text response
                        reply = msg.get("content", "").strip()
                        if reply:
                            self.history.append({"role": "assistant", "content": reply})
                            return reply
                        return "Done."

                    # Execute each tool call
                    logger.info(f"Tool round {round_num + 1}: {len(tool_calls)} call(s)")
                    messages.append(msg)  # Add assistant message with tool_calls

                    for tc in tool_calls:
                        func = tc.get("function", {})
                        name = func.get("name", "")
                        args = func.get("arguments", {})

                        # If arguments came as string, parse it
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}

                        logger.info(f"  Executing tool: {name}({args})")
                        result = await self._execute_tool(name, args)
                        logger.info(f"  Result: {result[:200]}")

                        messages.append({
                            "role": "tool",
                            "content": result,
                        })

                # If we exhausted tool rounds, ask for a summary
                return "I completed the actions. Let me know if you need anything else."

        except httpx.ConnectError:
            logger.warning("Ollama not reachable — falling back")
            return self._fallback(user_message)
        except httpx.TimeoutException:
            logger.warning("Ollama timed out")
            return "Sorry, that took too long. Try again?"
        except Exception as e:
            logger.error(f"Ollama error: {e}", exc_info=True)
            return self._fallback(user_message)

    # ─── Tool Execution ──────────────────────────────────

    async def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool by name and return the result string."""
        try:
            if name == "run_shell_command":
                return await self._tool_shell(args.get("command", ""))
            elif name == "create_file":
                return await self._tool_create_file(args.get("path", ""), args.get("content", ""))
            elif name == "read_file":
                return await self._tool_read_file(args.get("path", ""))
            elif name == "list_directory":
                return await self._tool_list_dir(args.get("path", ""))
            elif name == "search_files":
                return await self._tool_search(args.get("query", ""))
            elif name == "open_application":
                return await self._tool_open_app(args.get("name", ""))
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            return f"Error: {e}"

    async def _tool_shell(self, command: str) -> str:
        """Execute a shell command and return output."""
        if not command:
            return "Error: no command provided."

        logger.info(f"  Shell: {command}")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.home()),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            out = stdout.decode().strip()
            err = stderr.decode().strip()

            result = ""
            if out:
                result += out
            if err:
                result += f"\n[stderr]: {err}" if result else f"[stderr]: {err}"
            if not result:
                result = f"Command completed (exit code {proc.returncode})"
            elif proc.returncode != 0:
                result += f"\n[exit code {proc.returncode}]"

            # Truncate very long output
            if len(result) > 2000:
                result = result[:2000] + "\n... (truncated)"

            return result
        except asyncio.TimeoutError:
            return "Error: command timed out after 30 seconds."
        except Exception as e:
            return f"Error executing command: {e}"

    async def _tool_create_file(self, path: str, content: str) -> str:
        """Create or overwrite a file."""
        if not path:
            return "Error: no path provided."
        expanded = os.path.expanduser(path)
        p = Path(expanded)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"File created successfully at {expanded} ({len(content)} bytes)"
        except Exception as e:
            return f"Error creating file: {e}"

    async def _tool_read_file(self, path: str) -> str:
        """Read a file's contents."""
        if not path:
            return "Error: no path provided."
        expanded = os.path.expanduser(path)
        p = Path(expanded)
        if not p.exists():
            return f"Error: file not found at {expanded}"
        try:
            content = p.read_text(encoding="utf-8")
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            return content if content else "(empty file)"
        except Exception as e:
            return f"Error reading file: {e}"

    async def _tool_list_dir(self, path: str) -> str:
        """List directory contents."""
        if not path:
            path = "~"
        expanded = os.path.expanduser(path)
        p = Path(expanded)
        if not p.is_dir():
            return f"Error: '{expanded}' is not a directory."
        try:
            entries = sorted(p.iterdir())
            if not entries:
                return f"{expanded} is empty."
            lines = []
            for e in entries[:30]:
                kind = "dir" if e.is_dir() else "file"
                lines.append(f"  [{kind}] {e.name}")
            result = f"{expanded} ({len(entries)} items):\n" + "\n".join(lines)
            if len(entries) > 30:
                result += f"\n  ... and {len(entries) - 30} more"
            return result
        except Exception as e:
            return f"Error listing directory: {e}"

    async def _tool_search(self, query: str) -> str:
        """Search files via Spotlight."""
        if not query:
            return "Error: no search query."
        try:
            proc = await asyncio.create_subprocess_exec(
                "mdfind", "-name", query, "-limit", "10",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            results = [r for r in stdout.decode().strip().split("\n") if r]
            if not results:
                return f"No files found matching '{query}'."
            return f"Found {len(results)} result(s):\n" + "\n".join(f"  {r}" for r in results)
        except Exception:
            return f"Search failed for '{query}'."

    async def _tool_open_app(self, name: str) -> str:
        """Open a macOS application or file."""
        if not name:
            return "Error: no app name provided."
        try:
            proc = await asyncio.create_subprocess_exec(
                "open", "-a", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                return f"Opened {name} successfully."
            # Try as file/path
            proc2 = await asyncio.create_subprocess_exec(
                "open", os.path.expanduser(name),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc2.communicate(), timeout=5)
            if proc2.returncode == 0:
                return f"Opened {name}."
            return f"Could not open '{name}': {stderr.decode().strip()}"
        except Exception as e:
            return f"Error opening {name}: {e}"

    # ─── Fallback ────────────────────────────────────────

    def _fallback(self, text: str) -> str:
        lower = text.lower().strip()
        if any(lower.startswith(g) for g in ("good morning", "hello", "hey", "hi")):
            return "Hello! Ollama seems to be offline — I can't think very well right now."
        if "time" in lower:
            return f"It's {datetime.datetime.now().strftime('%I:%M %p')}."
        return f"I heard: \"{text}\". Ollama is offline — try 'ollama serve'."

    # ─── TTS ─────────────────────────────────────────────

    async def _speak(self, text: str):
        """Speak text using macOS TTS."""
        if platform.system() != "Darwin":
            return
        if self.tts_process and self.tts_process.returncode is None:
            try:
                self.tts_process.kill()
            except ProcessLookupError:
                pass

        clean = text.replace('"', '').replace("'", "").replace("\n", ". ")
        if len(clean) > 300:
            clean = clean[:300] + "... and more."

        try:
            self.tts_process = await asyncio.create_subprocess_exec(
                "say", "-v", "Samantha", "-r", "195", clean,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning(f"TTS failed: {e}")
