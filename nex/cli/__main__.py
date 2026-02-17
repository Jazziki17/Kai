"""
Nex CLI — Terminal-native agentic coding assistant.
Entry point: python -m nex.cli
"""

import argparse
import asyncio
import os
import platform
import readline
import signal
import sys
import datetime
from pathlib import Path

from nex.cli import renderer
from nex.cli.agent import Agent
from nex.cli.session import Session
from nex.cli import data_tools


DEFAULT_MODEL = "llama3.2"

SYSTEM_PROMPT_TEMPLATE = """You are Nex — an expert software engineer and data processing agent working directly in the user's terminal.
You have full access to their codebase at {cwd}.
You can read files, write files, run shell commands, search code, manage projects, and process data files.

Rules:
- When asked to DO something (create file, edit code, run command) you MUST use tools. Never claim you did something without doing it.
- Read existing code before writing new code. Match the style and patterns already in the project.
- Prefer str_replace over write_file for targeted edits — it's safer and uses less context.
- After making changes, verify them (run tests, check output) when appropriate.
- Be concise. Show your work through tool calls, not lengthy explanations.
- If approaching context limits, mention it proactively.

Data Processing Rules:
- ALWAYS inspect_file before processing any data file. Never guess column names.
- Use run_python for merges, transforms, filters, aggregations on Excel/CSV/JSON files.
- Use run_sql when the user explicitly wants SQL, or for complex joins.
- After processing, use preview_data to show results and save_output to deliver files.
- Output goes to ./output/ — never modify original files in-place.
- Show the Python/SQL script before running it. The user should learn from the code.
- If a script fails, diagnose the error, fix the script, and retry (up to 3 times).
- After merges/transforms, report row counts, match rates, and data quality.

Platform: {platform}
User: {user}
Date: {date}
Working directory: {cwd}
{project_config}"""


def build_system_prompt(cwd: str) -> str:
    """Build the system prompt, including NEX.md if present."""
    config_text = ""
    for config_name in ["NEX.md", "CLAUDE.md", ".nex/config.md"]:
        config_path = Path(cwd) / config_name
        if config_path.exists():
            try:
                content = config_path.read_text(encoding="utf-8")[:4000]
                config_text = f"\nProject config ({config_name}):\n{content}"
                break
            except Exception:
                pass

    return SYSTEM_PROMPT_TEMPLATE.format(
        cwd=cwd,
        platform=f"{platform.system()} {platform.release()}",
        user=os.getenv("USER", "unknown"),
        date=datetime.datetime.now().strftime("%A, %B %d, %Y"),
        project_config=config_text,
    )


# ─── Slash Commands ────────────────────────────────────────

SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/compact": "Compact context (optional: /compact <focus instructions>)",
    "/clear": "Clear conversation context",
    "/context": "Show token usage (/context --verbose for details)",
    "/model": "Switch model (/model <name>)",
    "/status": "Show session info and modified files",
    "/sessions": "List saved sessions",
    "/resume": "Resume a saved session (/resume <id>)",
    "/scripts": "List saved data processing scripts",
    "/init": "Create a NEX.md config file in the project root",
    "/quit": "Exit Nex CLI",
}


async def handle_slash(command: str, session: Session, agent: Agent, cwd: str) -> bool:
    """Handle a slash command. Returns True if handled."""
    parts = command.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    match cmd:
        case "/help":
            print()
            for name, desc in SLASH_COMMANDS.items():
                print(f"  {renderer.CYAN}{name:<16}{renderer.RESET}{renderer.DIM}{desc}{renderer.RESET}")
            print()

        case "/compact":
            await session.compact(agent, instructions=arg)

        case "/clear":
            session.clear()

        case "/context":
            session.show_context(verbose="--verbose" in arg or "-v" in arg)

        case "/model":
            if arg:
                agent.model = arg.strip()
                session.model = arg.strip()
                renderer.success(f"Switched to model: {arg.strip()}")
            else:
                renderer.info(f"  Current model: {session.model}")
                renderer.info(f"  Usage: /model <name>  (e.g. /model llama3.2)")

        case "/status":
            renderer.info(f"  Session: {session.id}")
            renderer.info(f"  Model: {session.model}")
            renderer.info(f"  Directory: {cwd}")
            renderer.info(f"  Messages: {len(session.transcript)}")
            renderer.info(f"  Compactions: {session.compactions}")
            session.show_context()

        case "/sessions":
            sessions = Session.list_sessions()
            if not sessions:
                renderer.info("  No saved sessions.")
            else:
                print()
                for s in sessions:
                    short_cwd = renderer._shorten_path(s["cwd"])
                    print(f"  {renderer.CYAN}{s['id']}{renderer.RESET}  {renderer.DIM}{short_cwd}  ·  {s['messages']} msgs  ·  {s['last_active']}{renderer.RESET}")
                print()

        case "/resume":
            if not arg:
                renderer.info("  Usage: /resume <session-id>")
            else:
                loaded = Session.load(arg.strip(), build_system_prompt(cwd))
                if loaded:
                    # Return the loaded session — caller needs to handle this
                    renderer.success(f"Resumed session {arg.strip()}")
                    return loaded  # Special return
                else:
                    renderer.error(f"Session '{arg.strip()}' not found.")

        case "/scripts":
            print(data_tools.list_scripts(cwd))

        case "/init":
            config_path = Path(cwd) / "NEX.md"
            if config_path.exists():
                renderer.info(f"  NEX.md already exists at {config_path}")
            else:
                project_name = Path(cwd).name
                template = f"""# Project: {project_name}

## Tech Stack
- Language:
- Framework:
- Testing:

## Coding Standards
-

## Architecture
-

## When Compacting, Always Preserve:
- Full list of modified files
- Current task status
- Any test results
"""
                config_path.write_text(template)
                renderer.success(f"Created {config_path}")

        case "/quit" | "/exit" | "/q":
            return "quit"

        case _:
            # Check for custom commands in .nex/commands/
            custom_path = Path(cwd) / ".nex" / "commands" / f"{cmd.lstrip('/')}.md"
            if custom_path.exists():
                try:
                    template = custom_path.read_text(encoding="utf-8")
                    # Replace $ARGUMENTS placeholder
                    template = template.replace("$ARGUMENTS", arg)
                    return template  # Return as message to send to agent
                except Exception:
                    renderer.error(f"Failed to load custom command: {cmd}")
            else:
                renderer.error(f"Unknown command: {cmd}. Type /help for available commands.")

    return True


# ─── Main REPL ─────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Nex — Terminal-native coding assistant")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help="Ollama model to use")
    parser.add_argument("--auto-approve", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--resume", "-r", metavar="ID", help="Resume a saved session")
    parser.add_argument("prompt", nargs="*", help="Optional initial prompt")
    args = parser.parse_args()

    cwd = os.getcwd()
    system_prompt = build_system_prompt(cwd)

    # Initialize or resume session
    if args.resume:
        session = Session.load(args.resume, system_prompt)
        if not session:
            renderer.error(f"Session '{args.resume}' not found.")
            sys.exit(1)
        renderer.info(f"  Resumed session {session.id}")
    else:
        session = Session(args.model, cwd, system_prompt)

    agent = Agent(args.model, cwd, session, auto_approve=args.auto_approve)

    # Handle Ctrl+C gracefully
    def handle_sigint(sig, frame):
        agent.interrupt()

    signal.signal(signal.SIGINT, handle_sigint)

    # Show banner
    renderer.banner(args.model, cwd)

    if args.auto_approve:
        print(f"  {renderer.BG_RED}{renderer.WHITE}{renderer.BOLD} WARNING {renderer.RESET} {renderer.RED}Auto-approve mode — all actions execute without confirmation{renderer.RESET}\n")

    # If initial prompt was provided as CLI args
    initial_prompt = " ".join(args.prompt) if args.prompt else None

    # ─── REPL Loop ─────────────────────────────
    while True:
        try:
            if initial_prompt:
                user_input = initial_prompt
                print(f"{renderer.prompt()}{user_input}")
                initial_prompt = None
            else:
                user_input = input(renderer.prompt()).strip()

            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                result = await handle_slash(user_input, session, agent, cwd)
                if result == "quit":
                    break
                elif isinstance(result, Session):
                    # Session was replaced via /resume
                    session = result
                    agent = Agent(session.model, cwd, session, auto_approve=args.auto_approve)
                    continue
                elif isinstance(result, str) and result is not True:
                    # Custom command returned a prompt — send to agent
                    user_input = result
                else:
                    continue

            # Run the agent
            await agent.run(user_input)

            # Auto-save
            session.save()

            # Check for compaction need
            if session.needs_compaction():
                renderer.info(f"  {renderer.YELLOW}Context at {session.context_usage:.0%} — auto-compacting...{renderer.RESET}")
                await session.compact(agent)

        except EOFError:
            break
        except KeyboardInterrupt:
            print()  # New line after ^C
            continue

    # Save on exit
    session.save()
    print(f"\n  {renderer.DIM}Session saved: {session.id}{renderer.RESET}\n")


def run():
    """Entry point for the CLI."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
