"""
Terminal renderer — colors, spinners, diffs, status line.
"""

import sys
import os
import threading
import time
import difflib

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GRAY = "\033[90m"

BG_RED = "\033[41m"
BG_GREEN = "\033[42m"

# Symbols
DOT_ACTION = "⏺"
DOT_THINKING = "✻"
DOT_SUCCESS = "✓"
DOT_ERROR = "✗"
DOT_TOOL = "⏺"
ARROW = "⎿"
CHEVRON = "❯"


class Spinner:
    """Animated spinner for long-running operations."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text: str = "Thinking"):
        self.text = text
        self._running = False
        self._thread = None
        self._start_time = 0.0

    def start(self):
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        # Clear spinner line
        sys.stderr.write(f"\r\033[K")
        sys.stderr.flush()

    def update(self, text: str):
        self.text = text

    def _spin(self):
        i = 0
        while self._running:
            elapsed = time.time() - self._start_time
            frame = self.FRAMES[i % len(self.FRAMES)]
            line = f"\r{YELLOW}{frame}{RESET} {DIM}{self.text}{RESET} {GRAY}({elapsed:.0f}s){RESET}"
            sys.stderr.write(f"\033[K{line}")
            sys.stderr.flush()
            time.sleep(0.08)
            i += 1


def banner(model: str, cwd: str):
    """Print startup banner."""
    print(f"\n{BOLD}{CYAN}  N E X{RESET}  {DIM}Terminal Agent{RESET}")
    print(f"{DIM}  Model: {RESET}{model}  {DIM}│  Dir: {RESET}{_shorten_path(cwd)}")
    print(f"{DIM}  Type {RESET}/help{DIM} for commands, {RESET}Ctrl+C{DIM} to exit{RESET}")
    print(f"{DIM}  {'─' * 50}{RESET}\n")


def prompt():
    """Render the input prompt."""
    return f"{BOLD}{BLUE}{CHEVRON}{RESET} "


def user_message(text: str):
    """Display user input."""
    # Already shown via input(), no need to re-render
    pass


def assistant_text(text: str):
    """Render assistant response text."""
    print(f"\n{text}\n")


def tool_start(name: str, args_summary: str = ""):
    """Show tool invocation."""
    desc = f"({args_summary})" if args_summary else ""
    print(f"  {YELLOW}{DOT_TOOL}{RESET} {DIM}{name}{RESET}{GRAY} {desc}{RESET}")


def tool_result(name: str, summary: str, success: bool = True):
    """Show tool result."""
    icon = f"{GREEN}{DOT_SUCCESS}" if success else f"{RED}{DOT_ERROR}"
    print(f"  {icon}{RESET} {DIM}{summary}{RESET}")


def thinking(text: str = "Thinking..."):
    """Show thinking state."""
    print(f"  {YELLOW}{DOT_THINKING}{RESET} {DIM}{ITALIC}{text}{RESET}")


def error(text: str):
    """Show error message."""
    print(f"\n  {RED}{DOT_ERROR} {text}{RESET}\n")


def success(text: str):
    """Show success message."""
    print(f"\n  {GREEN}{DOT_SUCCESS} {text}{RESET}\n")


def info(text: str):
    """Show info message."""
    print(f"  {DIM}{text}{RESET}")


def context_status(input_tokens: int, max_tokens: int, model: str):
    """Show context usage inline."""
    pct = (input_tokens / max_tokens * 100) if max_tokens > 0 else 0
    bar_width = 20
    filled = int(pct / 100 * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    color = GREEN if pct < 70 else (YELLOW if pct < 90 else RED)
    print(f"  {DIM}Context: {color}{bar}{RESET} {DIM}{pct:.0f}% ({input_tokens:,}/{max_tokens:,} tokens) · {model}{RESET}")


def compact_notice():
    """Show compaction notice."""
    print(f"\n  {YELLOW}* Conversation compacted{RESET} {DIM}(/history for full transcript){RESET}\n")


def show_diff(old_content: str, new_content: str, filepath: str):
    """Display a colored diff between old and new content."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(old_lines, new_lines, fromfile=filepath, tofile=filepath, lineterm="")

    added = 0
    removed = 0
    lines = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            lines.append(f"{DIM}{line.rstrip()}{RESET}")
        elif line.startswith("@@"):
            lines.append(f"{CYAN}{line.rstrip()}{RESET}")
        elif line.startswith("+"):
            lines.append(f"{GREEN}{line.rstrip()}{RESET}")
            added += 1
        elif line.startswith("-"):
            lines.append(f"{RED}{line.rstrip()}{RESET}")
            removed += 1
        else:
            lines.append(f"{DIM}{line.rstrip()}{RESET}")

    if lines:
        print(f"\n  {DIM}{'─' * 50}{RESET}")
        for line in lines:
            print(f"  {line}")
        print(f"  {DIM}{'─' * 50}{RESET}")
        print(f"  {GREEN}+{added}{RESET} {RED}-{removed}{RESET}")
    return added, removed


def script_preview(code: str, lang: str = "python", description: str = ""):
    """Display a script with a box before execution."""
    lang_colors = {"python": YELLOW, "sql": CYAN, "javascript": GREEN}
    color = lang_colors.get(lang, DIM)
    label = lang.capitalize()
    if description:
        label += f" — {description}"

    print(f"\n  {color}{DOT_ACTION}{RESET} {BOLD}{label}{RESET}")
    print(f"  {DIM}{'─' * 50}{RESET}")
    for line in code.strip().splitlines():
        print(f"  {DIM}│{RESET} {line}")
    print(f"  {DIM}{'─' * 50}{RESET}")


def data_quality_report(title: str, stats: dict):
    """Display a data quality report after merge/transform."""
    print(f"\n  {BOLD}{CYAN}Data Quality Report: {title}{RESET}")
    print(f"  {'━' * 45}")
    for key, val in stats.items():
        if key == "warnings":
            if val:
                print(f"  {YELLOW}Warnings:{RESET}")
                for w in val:
                    print(f"    {YELLOW}• {w}{RESET}")
        else:
            print(f"  {DIM}{key + ':':<30}{RESET} {val}")
    print(f"  {'━' * 45}\n")


def _shorten_path(path: str) -> str:
    """Shorten path for display."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path
