"""
Command Handler — Nex's brain powered by Ollama LLM with real tool execution.
Supports: shell commands, files, web search, system stats, memory, voice control.
"""

import asyncio
import datetime
import json
import os
import platform
import time
from collections import defaultdict
from pathlib import Path

import edge_tts
import httpx
import psutil

from nex.core.event_bus import EventBus
from nex.utils.logger import setup_logger

logger = setup_logger(__name__)

EDGE_TTS_VOICE = "en-US-AndrewMultilingualNeural"

OLLAMA_URL = "http://localhost:11434"
MODEL_FAST = "qwen2.5:1.5b"    # ~1s responses for simple queries
MODEL_STRONG = "llama3.2"       # fuller reasoning for complex tasks
MAX_HISTORY = 10
MAX_TOOL_ROUNDS = 5

# Simple queries that should use the fast model
_SIMPLE_PATTERNS = [
    "what time", "what's the time", "what day", "what date",
    "hello", "hey", "hi ", "good morning", "good evening", "good night",
    "how are you", "what's up", "thanks", "thank you",
    "who are you", "what are you", "your name",
    "what can you", "tell me about yourself", "help",
    "how's the weather", "what's the weather",
]

# Complex queries that need the strong model (tool use)
_COMPLEX_PATTERNS = [
    "search", "create", "open", "run", "find", "write", "delete",
    "install", "download", "upload", "execute", "launch", "kill",
    "read file", "list", "fetch", "analyze", "look at", "camera",
    "detect", "identify", "stock", "price",
]


def _pick_model(message: str) -> str:
    """Route simple queries to the fast model, complex ones to the strong model."""
    lower = message.strip().lower()
    word_count = len(lower.split())
    # Explicit complex patterns always use strong model
    for p in _COMPLEX_PATTERNS:
        if p in lower:
            return MODEL_STRONG
    # Short messages → fast model
    if word_count <= 12:
        for p in _SIMPLE_PATTERNS:
            if p in lower:
                return MODEL_FAST
    # Short conversational messages → fast
    if word_count <= 6:
        return MODEL_FAST
    return MODEL_STRONG

# Rate limiting
RATE_LIMIT_MAX = 20       # commands per window
RATE_LIMIT_WINDOW = 60    # seconds

# Auto-lock
AUTO_LOCK_TIMEOUT = 900   # 15 minutes in seconds

SYSTEM_PROMPT = """You are Nex — a tactical AI assistant on the user's Mac. Think JARVIS: sharp, efficient, zero fluff.

RULES:
- Max 1-3 sentences. Never ramble. Expand ONLY if explicitly asked.
- NEVER use the user's name in responses. NEVER say "Sure!", "Of course!", "I'd be happy to..." — just DO it.
- Declarative statements, not questions. "Opening Safari." not "Shall I open Safari?"
- No markdown, no bullet points, no asterisks. This is spoken aloud.
- When executing a task: confirm with one word. "Done." or "Opening Safari."
- When answering questions: data first, context second, opinions never.

Environment: {platform} | User: {user} | Home: {home} | {date} {time}

Tools: Use tools when asked to DO something. Never fake output. Non-destructive actions: execute immediately. Destructive actions: state intent, ask once.
{memory_context}"""

TOOLS = [
    {"type": "function", "function": {
        "name": "run_shell_command",
        "description": "Execute a shell command on the local machine. Use for any terminal operation.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell command to execute"}
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "create_file",
        "description": "Create or overwrite a file at the specified path with content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path (use ~ for home)"},
            "content": {"type": "string", "description": "File content"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read and return the contents of a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path to read"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "list_directory",
        "description": "List files and folders in a directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directory path"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "Search for files by name using macOS Spotlight.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Filename to search for"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "open_application",
        "description": "Open a macOS application or file.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "App name or file path"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "get_system_stats",
        "description": "Get current system performance: CPU, RAM, disk, battery.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the internet via DuckDuckGo. Use when you need current info or don't know something.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_webpage",
        "description": "Fetch and read the text content of a webpage URL.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "Full URL to fetch"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "remember",
        "description": "Store a fact in persistent memory. Use when user shares personal info or asks you to remember something.",
        "parameters": {"type": "object", "properties": {
            "fact": {"type": "string", "description": "The fact to remember"},
        }, "required": ["fact"]},
    }},
    {"type": "function", "function": {
        "name": "recall",
        "description": "Search persistent memory for stored facts.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Optional search term"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "set_user_name",
        "description": "Remember the user's name to address them personally.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "User's name"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "cleanup_memory",
        "description": "Clean up old, expired memories and return stats about memory usage.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Get current weather and forecast for a location.",
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string", "description": "City name or location (e.g. 'London', 'New York')"},
        }, "required": ["location"]},
    }},
    {"type": "function", "function": {
        "name": "get_news",
        "description": "Get latest news headlines, optionally filtered by topic.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "News topic to search for (e.g. 'technology', 'sports'). Leave empty for top headlines."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_stock_price",
        "description": "Get current stock price and change for a ticker symbol.",
        "parameters": {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "Stock ticker symbol (e.g. 'AAPL', 'GOOGL')"},
        }, "required": ["symbol"]},
    }},
    {"type": "function", "function": {
        "name": "create_task",
        "description": "Create a new task or to-do item. Use when the user mentions something they need to do, a reminder, or an action item.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "Task title"},
            "priority": {"type": "string", "description": "Priority: high, medium, or low", "enum": ["high", "medium", "low"]},
            "due": {"type": "string", "description": "Optional due date (e.g. 'tomorrow', '2026-03-01')"},
        }, "required": ["title"]},
    }},
    {"type": "function", "function": {
        "name": "list_tasks",
        "description": "List all current tasks/to-dos, optionally filtered by status.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "description": "Filter: all, pending, or completed", "enum": ["all", "pending", "completed"]},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "complete_task",
        "description": "Mark a task as completed by its number.",
        "parameters": {"type": "object", "properties": {
            "task_number": {"type": "integer", "description": "The task number to complete (from list_tasks)"},
        }, "required": ["task_number"]},
    }},
    {"type": "function", "function": {
        "name": "identify_objects",
        "description": "Use the camera to detect and identify objects in view. Can also analyze an image file.",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string", "description": "camera (default) or file path to image"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "classify_image",
        "description": "Classify what the camera sees into categories.",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string", "description": "camera or file path"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "segment_scene",
        "description": "Analyze the camera view with pixel-level segmentation to identify all distinct objects and regions.",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string", "description": "camera or file path"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "enroll_voice",
        "description": "Start voice authentication enrollment. The user will be asked to speak 3 phrases to create a voice profile.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "reset_voice_auth",
        "description": "Reset voice authentication, deleting the stored voice profile.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]


class CommandHandler:
    def __init__(self, event_bus: EventBus, memory_manager=None):
        self.event_bus = event_bus
        self.memory = memory_manager
        self.history: list[dict] = []
        self.tts_process: asyncio.subprocess.Process | None = None

        # Rate limiting: source -> list of timestamps
        self._rate_log: dict[str, list[float]] = defaultdict(list)

        # Auto-lock
        self._last_command_time: float = time.monotonic()
        self._locked = False
        self._lock_check_task: asyncio.Task | None = None

    async def start(self):
        self.event_bus.subscribe("system.command", self._on_command)
        self.event_bus.subscribe("system.ready", self._on_system_ready)
        self._lock_check_task = asyncio.create_task(self._auto_lock_loop())
        logger.info("Command handler ready.")

    async def _auto_lock_loop(self):
        """Periodically check for inactivity and lock if needed."""
        while True:
            await asyncio.sleep(60)
            if not self._locked:
                elapsed = time.monotonic() - self._last_command_time
                if elapsed >= AUTO_LOCK_TIMEOUT:
                    self._locked = True
                    logger.info("Auto-locked after inactivity")
                    await self.event_bus.publish("system.locked", {})

    def _check_rate_limit(self, source: str) -> bool:
        """Returns True if the command should be allowed, False if rate limited."""
        now = time.monotonic()
        # Prune old entries
        self._rate_log[source] = [
            t for t in self._rate_log[source] if now - t < RATE_LIMIT_WINDOW
        ]
        if len(self._rate_log[source]) >= RATE_LIMIT_MAX:
            return False
        self._rate_log[source].append(now)
        return True

    async def _on_system_ready(self, data: dict):
        """Silent startup — no TTS, no narration. Visual-only."""
        logger.info("System ready — standing by silently.")

    def _build_system_prompt(self) -> str:
        now = datetime.datetime.now()
        ctx = ""
        if self.memory:
            mc = self.memory.get_context_for_llm()
            if mc:
                ctx = f"\nThings you know about the user:\n{mc}"
        return SYSTEM_PROMPT.format(
            platform=f"{platform.system()} {platform.release()}",
            user=os.getenv("USER", "unknown"),
            home=str(Path.home()),
            time=now.strftime("%I:%M %p"),
            date=now.strftime("%A, %B %d, %Y"),
            memory_context=ctx,
        )

    async def _on_command(self, data: dict):
        command = data.get("command", "").strip()
        if not command:
            return

        source = data.get("source", "unknown")

        # Rate limiting
        if not self._check_rate_limit(source):
            logger.warning(f"Rate limited: {source}")
            await self.event_bus.publish("command.response", {
                "text": "Too many commands. Please slow down.",
                "command": command,
            })
            return

        # Auto-lock check: voice commands require re-verification when locked
        if self._locked and source == "microphone":
            logger.info("Command blocked — system is locked")
            await self.event_bus.publish("command.response", {
                "text": "I'm currently locked due to inactivity. Please speak again to verify your identity.",
                "command": command,
            })
            return

        # Unlock on any valid command
        if self._locked:
            self._locked = False
            await self.event_bus.publish("system.unlocked", {})

        self._last_command_time = time.monotonic()

        logger.info(f"Command received: {command}")
        try:
            response = await self._process_with_tools(command)
            if response:
                await self.event_bus.publish("command.response", {"text": response, "command": command})
                asyncio.create_task(self._speak(response))
        except Exception as e:
            logger.error(f"Command error: {e}", exc_info=True)
            try:
                await self.event_bus.publish("command.response", {"text": f"Sorry, something went wrong: {e}", "command": command})
            except Exception:
                pass

    async def _process_with_tools(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
        messages = [{"role": "system", "content": self._build_system_prompt()}, *self.history]
        model = _pick_model(user_message)
        logger.info(f"Model selected: {model}")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for round_num in range(MAX_TOOL_ROUNDS):
                    # Fast model: no tools, short responses. Strong model: tools + longer.
                    payload = {"model": model, "messages": messages, "stream": False}
                    if model == MODEL_FAST:
                        payload["options"] = {"num_predict": 200, "temperature": 0.3}
                    else:
                        payload["tools"] = TOOLS
                        payload["options"] = {"num_predict": 400, "temperature": 0.4}
                    resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                    resp.raise_for_status()
                    msg = resp.json().get("message", {})
                    tool_calls = msg.get("tool_calls")
                    if not tool_calls:
                        reply = msg.get("content", "").strip() or "Done."
                        # Filter raw JSON tool calls that leaked into text
                        reply = self._filter_json_artifacts(reply)
                        # Remove filler/fluff for conciseness
                        reply = self._remove_fluff(reply)
                        self.history.append({"role": "assistant", "content": reply})
                        return reply
                    logger.info(f"Tool round {round_num + 1}: {len(tool_calls)} call(s)")
                    messages.append(msg)
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        name = func.get("name", "")
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try: args = json.loads(args)
                            except json.JSONDecodeError: args = {}
                        logger.info(f"  Tool: {name}")
                        await self.event_bus.publish("tool.executing", {"name": name, "round": round_num + 1})
                        result = await self._execute_tool(name, args)
                        # Publish tool output for workspace pane
                        sanitized_args = {k: (str(v)[:200] if v else "") for k, v in args.items()}
                        await self.event_bus.publish("tool.output", {
                            "name": name,
                            "output": result[:3000],
                            "args": sanitized_args,
                        })
                        await self.event_bus.publish("tool.completed", {"name": name, "success": not result.startswith("Error")})
                        messages.append({"role": "tool", "content": result})
                return "I completed the actions."
        except httpx.ConnectError:
            return self._fallback(user_message)
        except httpx.TimeoutException:
            return "Sorry, that took too long. Try again?"
        except Exception as e:
            logger.error(f"Ollama error: {e}", exc_info=True)
            return self._fallback(user_message)

    async def _execute_tool(self, name: str, args: dict) -> str:
        try:
            match name:
                case "run_shell_command": return await self._tool_shell(args.get("command", ""))
                case "create_file": return await self._tool_create_file(args.get("path", ""), args.get("content", ""))
                case "read_file": return await self._tool_read_file(args.get("path", ""))
                case "list_directory": return await self._tool_list_dir(args.get("path", "~"))
                case "search_files": return await self._tool_search(args.get("query", ""))
                case "open_application": return await self._tool_open_app(args.get("name", ""))
                case "get_system_stats": return self._tool_system_stats()
                case "web_search": return await self._tool_web_search(args.get("query", ""))
                case "fetch_webpage": return await self._tool_fetch_webpage(args.get("url", ""))
                case "remember":
                    return self.memory.remember_fact(args.get("fact", "")) if self.memory else "Memory unavailable."
                case "recall":
                    return self.memory.recall_facts(args.get("query", "")) if self.memory else "Memory unavailable."
                case "set_user_name":
                    return self.memory.set_user_name(args.get("name", "")) if self.memory else "Memory unavailable."
                case "cleanup_memory":
                    return self.memory.cleanup_memory() if self.memory else "Memory unavailable."
                case "get_weather": return await self._tool_weather(args.get("location", ""))
                case "get_news": return await self._tool_news(args.get("topic", ""))
                case "get_stock_price": return await self._tool_stock(args.get("symbol", ""))
                case "create_task":
                    return self.memory.create_task(args.get("title", ""), args.get("priority", "medium"), args.get("due")) if self.memory else "Memory unavailable."
                case "list_tasks":
                    return self.memory.list_tasks(args.get("status", "pending")) if self.memory else "Memory unavailable."
                case "complete_task":
                    return self.memory.complete_task(args.get("task_number", 0)) if self.memory else "Memory unavailable."
                case "identify_objects": return await self._tool_detect(args.get("source", "camera"))
                case "classify_image": return await self._tool_classify(args.get("source", "camera"))
                case "segment_scene": return await self._tool_segment(args.get("source", "camera"))
                case "enroll_voice": return await self._tool_enroll_voice()
                case "reset_voice_auth": return await self._tool_reset_voice_auth()
                case _: return f"Unknown tool: {name}"
        except Exception as e:
            return f"Error: {e}"

    # ─── Autonomy & Safety ─────────────────────────────────

    # Commands that are always blocked (too dangerous for LLM autonomy)
    BLOCKED_PATTERNS = [
        "mkfs", "dd if=", "> /dev/", ":(){ :|:", "chmod -R 777 /",
        "shutdown", "reboot", "halt", "init 0", "init 6",
    ]

    # Commands that require user confirmation (destructive but sometimes needed)
    DESTRUCTIVE_PATTERNS = [
        "rm ", "rm\t", "rmdir", "kill ", "killall", "pkill",
        "sudo ", "mv /", "chmod", "chown", "diskutil",
        "launchctl", "defaults write", "networksetup",
    ]

    def _classify_command(self, command: str) -> str:
        """Classify a shell command: 'safe', 'destructive', or 'blocked'."""
        cmd_lower = command.strip().lower()
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return "blocked"
        for pattern in self.DESTRUCTIVE_PATTERNS:
            if pattern in cmd_lower:
                return "destructive"
        return "safe"

    # ─── Tool Implementations ────────────────────────────

    async def _tool_shell(self, command: str) -> str:
        if not command: return "Error: no command."
        tier = self._classify_command(command)
        if tier == "blocked":
            return f"BLOCKED: The command '{command}' is too dangerous to execute autonomously. This type of system-level operation requires manual execution."
        if tier == "destructive":
            await self.event_bus.publish("command.response", {
                "text": f"I need to run a potentially destructive command: `{command}`. Please confirm via the UI or repeat your request to proceed.",
                "command": "_confirmation_request",
                "awaiting_confirmation": True,
                "pending_command": command,
            })
            return f"CONFIRMATION REQUIRED: The command '{command}' could modify or delete data. I've asked the user to confirm. Tell them what you intend to do and why."
        try:
            proc = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=str(Path.home()))
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            out, err = stdout.decode().strip(), stderr.decode().strip()
            result = out
            if err: result += f"\n[stderr]: {err}" if result else f"[stderr]: {err}"
            if not result: result = f"Command completed (exit code {proc.returncode})"
            return result[:2000]
        except asyncio.TimeoutError: return "Error: timed out (30s)."
        except Exception as e: return f"Error: {e}"

    async def _tool_create_file(self, path: str, content: str) -> str:
        if not path: return "Error: no path."
        p = Path(os.path.expanduser(path))
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"File created at {p} ({len(content)} bytes)"
        except Exception as e: return f"Error: {e}"

    async def _tool_read_file(self, path: str) -> str:
        if not path: return "Error: no path."
        p = Path(os.path.expanduser(path))
        if not p.exists(): return f"Error: not found: {p}"
        try:
            c = p.read_text(encoding="utf-8")
            return c[:3000] if c else "(empty file)"
        except Exception as e: return f"Error: {e}"

    async def _tool_list_dir(self, path: str) -> str:
        p = Path(os.path.expanduser(path or "~"))
        if not p.is_dir(): return f"Error: not a directory: {p}"
        try:
            entries = sorted(p.iterdir())
            lines = [f"  [{'dir' if e.is_dir() else 'file'}] {e.name}" for e in entries[:30]]
            r = f"{p} ({len(entries)} items):\n" + "\n".join(lines)
            return r
        except Exception as e: return f"Error: {e}"

    async def _tool_search(self, query: str) -> str:
        if not query: return "Error: no query."
        try:
            proc = await asyncio.create_subprocess_exec("mdfind", "-name", query, "-limit", "10", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            results = [r for r in stdout.decode().strip().split("\n") if r]
            if not results: return f"No files matching '{query}'."
            return f"Found {len(results)}:\n" + "\n".join(f"  {r}" for r in results)
        except Exception: return f"Search failed."

    async def _tool_open_app(self, name: str) -> str:
        if not name: return "Error: no name."
        try:
            proc = await asyncio.create_subprocess_exec("open", "-a", name, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0: return f"Opened {name}."
            proc2 = await asyncio.create_subprocess_exec("open", os.path.expanduser(name), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc2.communicate(), timeout=5)
            return f"Opened {name}." if proc2.returncode == 0 else f"Could not open '{name}'."
        except Exception as e: return f"Error: {e}"

    def _tool_system_stats(self) -> str:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        battery = psutil.sensors_battery()
        lines = [f"CPU: {cpu}%", f"Memory: {mem.percent}% ({mem.used // (1024**3):.1f}/{mem.total // (1024**3):.1f} GB)", f"Disk: {disk.percent}% ({disk.used // (1024**3):.1f}/{disk.total // (1024**3):.1f} GB)"]
        if battery:
            lines.append(f"Battery: {battery.percent}% ({'plugged' if battery.power_plugged else 'on battery'})")
        return "\n".join(lines)

    async def _tool_web_search(self, query: str) -> str:
        if not query: return "Error: no query."
        try:
            from nex.api.web_tools import web_search
            return await web_search(query)
        except Exception as e: return f"Search failed: {e}"

    async def _tool_fetch_webpage(self, url: str) -> str:
        if not url: return "Error: no URL."
        try:
            from nex.api.web_tools import fetch_webpage
            return await fetch_webpage(url)
        except Exception as e: return f"Fetch failed: {e}"

    async def _tool_weather(self, location: str) -> str:
        if not location: return "Error: no location specified."
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"https://wttr.in/{location}?format=j1")
                resp.raise_for_status()
            data = resp.json()
            cur = data["current_condition"][0]
            desc = cur.get("weatherDesc", [{}])[0].get("value", "Unknown")
            temp_c = cur.get("temp_C", "?")
            temp_f = cur.get("temp_F", "?")
            humidity = cur.get("humidity", "?")
            wind = cur.get("windspeedKmph", "?")
            feels = cur.get("FeelsLikeC", "?")
            result = f"Weather in {location}: {desc}, {temp_c}°C ({temp_f}°F), feels like {feels}°C, humidity {humidity}%, wind {wind} km/h."
            # Add 3-day forecast
            forecasts = data.get("weather", [])[:3]
            for day in forecasts:
                date = day.get("date", "?")
                hi = day.get("maxtempC", "?")
                lo = day.get("mintempC", "?")
                desc_f = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "") if len(day.get("hourly", [])) > 4 else ""
                result += f"\n  {date}: {lo}-{hi}°C, {desc_f}"
            return result
        except Exception as e: return f"Weather lookup failed: {e}"

    async def _tool_news(self, topic: str = "") -> str:
        try:
            query = topic if topic else "top news today"
            from nex.api.web_tools import web_search
            return await web_search(f"{query} news", max_results=5)
        except Exception as e: return f"News fetch failed: {e}"

    async def _tool_stock(self, symbol: str) -> str:
        if not symbol: return "Error: no stock symbol."
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}",
                    params={"interval": "1d", "range": "5d"},
                    headers={"User-Agent": "Nex/0.1"}
                )
                resp.raise_for_status()
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result: return f"No data found for '{symbol}'."
            meta = result[0].get("meta", {})
            price = meta.get("regularMarketPrice", "?")
            prev = meta.get("chartPreviousClose", 0)
            currency = meta.get("currency", "USD")
            change = round(price - prev, 2) if isinstance(price, (int, float)) and prev else "?"
            pct = round((change / prev) * 100, 2) if isinstance(change, (int, float)) and prev else "?"
            direction = "up" if isinstance(change, (int, float)) and change > 0 else "down"
            return f"{symbol.upper()}: {price} {currency} ({direction} {abs(change) if isinstance(change, (int,float)) else change}, {pct}%)"
        except Exception as e: return f"Stock lookup failed: {e}"

    async def _tool_detect(self, source: str) -> str:
        try:
            from nex.api.vision_tools import detect_objects
            return await detect_objects(source)
        except Exception as e:
            return f"Vision error: {e}"

    async def _tool_classify(self, source: str) -> str:
        try:
            from nex.api.vision_tools import classify_image
            return await classify_image(source)
        except Exception as e:
            return f"Vision error: {e}"

    async def _tool_segment(self, source: str) -> str:
        try:
            from nex.api.vision_tools import segment_scene
            return await segment_scene(source)
        except Exception as e:
            return f"Vision error: {e}"

    async def _tool_enroll_voice(self) -> str:
        """Trigger voice enrollment via MicListener."""
        try:
            from nex.api.server import engine
            if engine and hasattr(engine, '_mic_listener') and engine._mic_listener:
                engine._mic_listener.start_enrollment()
                return "Voice enrollment started. Please speak 3 different phrases clearly. I'll confirm each one."
            return "Microphone is not available. Cannot enroll voice."
        except Exception as e:
            return f"Error starting enrollment: {e}"

    async def _tool_reset_voice_auth(self) -> str:
        """Reset voice authentication profile."""
        try:
            from nex.api.voice_auth import VoiceAuth
            va = VoiceAuth()
            return va.reset()
        except ImportError:
            return "Voice authentication module not available."
        except Exception as e:
            return f"Error resetting voice auth: {e}"

    @staticmethod
    def _remove_fluff(text: str) -> str:
        """Strip common LLM filler phrases for concise output."""
        import re
        patterns = [
            r"^(Sure|Of course|Absolutely|Certainly|Great|Alright)[,!\.]\s*",
            r"^(I'd be happy to|Let me|I'll|I can)\s+",
            r",?\s*(?:jazz|my friend|dear user|sir|ma'am)[\.,!]?",
            r"^Hey there[,!]\s*",
            r"\s*Is there anything else.*$",
            r"\s*Let me know if.*$",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _filter_json_artifacts(reply: str) -> str:
        """Strip raw JSON tool-call blobs that Ollama sometimes leaks into text."""
        stripped = reply.strip()
        # If entire reply is a JSON object/array with tool-call keys, discard it
        if stripped.startswith(("{", "[")) and stripped.endswith(("}", "]")):
            try:
                parsed = json.loads(stripped)
                # Detect tool-call shaped objects
                if isinstance(parsed, dict) and ("name" in parsed or "function" in parsed or "parameters" in parsed):
                    return "Done."
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and "name" in parsed[0]:
                    return "Done."
            except json.JSONDecodeError:
                pass
        # If reply contains an embedded JSON tool call block alongside text, strip the JSON
        import re
        cleaned = re.sub(
            r'\{"(?:name|function|tool_call)":\s*"[^"]*"[^}]*\}',
            '', reply
        ).strip()
        return cleaned if cleaned else reply

    def _fallback(self, text: str) -> str:
        lower = text.lower()
        if any(lower.startswith(g) for g in ("good morning", "hello", "hey", "hi")):
            return "Hello! Ollama seems offline right now."
        if "time" in lower:
            return f"It's {datetime.datetime.now().strftime('%I:%M %p')}."
        return f"I heard: \"{text}\". Ollama is offline."

    async def _speak(self, text: str):
        if self.tts_process and self.tts_process.returncode is None:
            try: self.tts_process.kill()
            except ProcessLookupError: pass
        clean = text.replace('"', '').replace("'", "").replace("\n", ". ")
        if len(clean) > 300: clean = clean[:300] + "... and more."
        tmp = f"/tmp/nex_tts_{id(text)}.mp3"
        try:
            for attempt in range(3):
                try:
                    communicate = edge_tts.Communicate(clean, EDGE_TTS_VOICE)
                    await communicate.save(tmp)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (2 ** attempt))
            self.tts_process = await asyncio.create_subprocess_exec(
                "afplay", tmp,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await self.tts_process.wait()
        except Exception as e:
            logger.warning(f"TTS failed: {e}")
        finally:
            if os.path.exists(tmp): os.remove(tmp)
