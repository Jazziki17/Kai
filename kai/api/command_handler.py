"""
Command Handler — Kai's brain powered by Ollama LLM.
Routes user commands through a local LLM for intelligent responses,
with local tool execution for system actions (files, apps, notes, etc.).
Also speaks responses via macOS TTS.
"""

import asyncio
import datetime
import os
import platform
from pathlib import Path

import httpx

from kai.core.event_bus import EventBus
from kai.utils.logger import setup_logger

logger = setup_logger(__name__)

OLLAMA_URL = "http://localhost:11434"
MODEL = "llama3.2"
MAX_HISTORY = 20  # Keep last N messages for context

SYSTEM_PROMPT = """You are Kai, a personal AI assistant running locally on the user's Mac.
You are inspired by Jarvis from Iron Man — intelligent, helpful, slightly witty, and always respectful.
Keep responses concise (1-3 sentences) unless the user asks for detail.
You speak in a natural, conversational tone. You can be warm and personable.

Current system info:
- Platform: {platform}
- Machine: {machine}
- User: {user}
- Home directory: {home}
- Current time: {time}
- Current date: {date}

You have these capabilities:
- Answer questions and have conversations (your primary function)
- Tell the time and date (already in your context above)
- Take and list notes (stored locally)
- Open macOS applications
- Search for files using Spotlight
- List directory contents
- Do basic math
- Provide system information

When the user asks you to perform an action (open an app, take a note, find a file), just describe what you're doing naturally — the system will execute the action automatically.
Do NOT use markdown formatting, bullet points, or numbered lists in your responses — speak naturally as if talking to someone."""


def _build_system_prompt() -> str:
    """Build the system prompt with current time/date."""
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
    """Processes text commands via Ollama LLM and publishes responses via EventBus."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.notes_dir = Path.home() / ".kai" / "data" / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.history: list[dict] = []  # Conversation history
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
            # Check for local actions first (side effects)
            action_context = await self._execute_local_action(command)

            # Get LLM response
            response = await self._ask_llm(command, action_context)

            if response:
                logger.info(f"Response ready ({len(response)} chars)")
                # Publish response to UI
                await self.event_bus.publish("command.response", {
                    "text": response,
                    "command": command,
                })

                # Speak the response (fire and forget)
                asyncio.create_task(self._speak(response))
        except Exception as e:
            logger.error(f"Command processing error: {e}", exc_info=True)
            # Still try to send error response
            try:
                await self.event_bus.publish("command.response", {
                    "text": f"Sorry, something went wrong: {e}",
                    "command": command,
                })
            except Exception:
                pass

    async def _ask_llm(self, user_message: str, action_context: str | None = None) -> str:
        """Send message to Ollama and get a response."""
        # Add user message to history
        if action_context:
            # Include action result in the user message context
            augmented = f"{user_message}\n\n[System executed action: {action_context}]"
            self.history.append({"role": "user", "content": augmented})
        else:
            self.history.append({"role": "user", "content": user_message})

        # Trim history
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        # Build messages
        messages = [
            {"role": "system", "content": _build_system_prompt()},
            *self.history,
        ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": MODEL,
                        "messages": messages,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data.get("message", {}).get("content", "").strip()

                if reply:
                    self.history.append({"role": "assistant", "content": reply})
                    return reply
                else:
                    return "I processed that, but didn't generate a response."

        except httpx.ConnectError:
            logger.warning("Ollama not reachable — falling back to local processing")
            return await self._fallback_process(user_message, action_context)
        except httpx.TimeoutException:
            logger.warning("Ollama request timed out")
            return "Sorry, I took too long thinking about that. Try again?"
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return await self._fallback_process(user_message, action_context)

    async def _fallback_process(self, text: str, action_context: str | None = None) -> str:
        """Fallback when Ollama is unavailable — basic pattern matching."""
        if action_context:
            return action_context

        lower = text.lower().strip().rstrip("?!.,")

        # Basic greetings
        greetings = {
            "good morning": "Good morning! How can I help you today?",
            "good afternoon": "Good afternoon! What can I do for you?",
            "good evening": "Good evening! How can I help?",
            "hello": "Hello! What do you need?",
            "hey": "Hey! What's up?",
            "hi": "Hi there!",
        }
        for greeting, reply in greetings.items():
            if lower.startswith(greeting):
                return reply

        # Time/date
        if "time" in lower:
            return f"It's {datetime.datetime.now().strftime('%I:%M %p')}."
        if "date" in lower:
            return f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}."

        return f"I heard: \"{text}\". Ollama seems to be offline — try starting it with 'ollama serve'."

    async def _execute_local_action(self, text: str) -> str | None:
        """Execute local system actions based on command. Returns context string or None."""
        lower = text.lower().strip()

        # Take a note
        if lower.startswith(("take a note", "note ", "remember ")):
            content = text
            for prefix in ["take a note ", "take a note: ", "note ", "note: ", "remember ", "remember: "]:
                if lower.startswith(prefix):
                    content = text[len(prefix):].strip()
                    break
            if content and content != text:
                return self._save_note(content)
            return None

        # Show notes
        if lower in ("show notes", "list notes", "my notes", "notes"):
            return self._list_notes()

        # Open app (macOS)
        if lower.startswith("open "):
            target = text[5:].strip()
            return await self._open_app(target)

        # Search files
        if lower.startswith(("find ", "search ", "locate ")):
            query = text.split(" ", 1)[1].strip() if " " in text else ""
            if query:
                return await self._find_files(query)
            return None

        # List directory
        if lower.startswith(("ls ", "list ")):
            path = text.split(" ", 1)[1].strip() if " " in text else "~"
            return await self._list_directory(path)

        # Calculator
        if lower.startswith(("calc ", "calculate ")):
            expr = text.split(" ", 1)[1].strip()
            return self._calculate(expr)

        return None

    def _save_note(self, content: str) -> str:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.notes_dir / f"note_{timestamp}.txt"
        path.write_text(
            f"Note — {datetime.datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n{content}\n",
            encoding="utf-8",
        )
        return f"Note saved: '{content[:50]}...'" if len(content) > 50 else f"Note saved: '{content}'"

    def _list_notes(self) -> str:
        notes = sorted(self.notes_dir.glob("*.txt"), reverse=True)
        if not notes:
            return "No notes found."
        lines = []
        for n in notes[:10]:
            first_line = n.read_text(encoding="utf-8").strip().split("\n")[-1][:60]
            lines.append(f"{n.stem}: {first_line}")
        return f"{len(notes)} note(s) found. Latest: {lines[0]}"

    async def _open_app(self, target: str) -> str:
        if platform.system() != "Darwin":
            return f"Cannot open apps — not on macOS."
        try:
            proc = await asyncio.create_subprocess_exec(
                "open", "-a", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                return f"Opened {target} successfully."
            else:
                # Try as file path
                proc2 = await asyncio.create_subprocess_exec(
                    "open", os.path.expanduser(target),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc2.communicate(), timeout=5)
                if proc2.returncode == 0:
                    return f"Opened {target}."
                return f"Could not find or open '{target}'."
        except Exception as e:
            return f"Error opening {target}: {e}"

    async def _find_files(self, query: str) -> str:
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
            return f"Found {len(results)} file(s) matching '{query}': {', '.join(Path(r).name for r in results[:5])}"
        except Exception:
            return f"File search failed for '{query}'."

    async def _list_directory(self, path: str) -> str:
        expanded = os.path.expanduser(path)
        p = Path(expanded)
        if not p.is_dir():
            return f"'{path}' is not a directory."
        entries = sorted(p.iterdir())[:20]
        if not entries:
            return f"'{path}' is empty."
        names = [e.name for e in entries[:10]]
        return f"{path} contains {len(list(p.iterdir()))} items. First few: {', '.join(names)}"

    def _calculate(self, expr: str) -> str:
        try:
            allowed = set("0123456789+-*/().% ")
            if not all(c in allowed for c in expr):
                return f"Cannot calculate '{expr}' — only basic math is supported."
            result = eval(expr)
            return f"Calculation result: {expr} = {result}"
        except Exception:
            return f"Could not calculate '{expr}'."

    async def _speak(self, text: str):
        """Speak text using macOS TTS (say command)."""
        if platform.system() != "Darwin":
            return

        # Kill any previous TTS
        if self.tts_process and self.tts_process.returncode is None:
            try:
                self.tts_process.kill()
            except ProcessLookupError:
                pass

        # Clean text for speech — remove special characters that confuse say
        clean = text.replace('"', '').replace("'", "").replace("\n", ". ")
        # Truncate very long responses for speech
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
