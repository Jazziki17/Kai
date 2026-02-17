"""
CLI Tools — File operations, bash, search, glob, and data tools for the agentic loop.
"""

import asyncio
import os
import subprocess
import glob as globlib
from pathlib import Path

from nex.cli import renderer
from nex.cli import data_tools


# ─── Tool Definitions (Ollama format) ──────────────────────

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read file content. Returns full file or a line range.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path (absolute or relative to cwd)"},
            "start_line": {"type": "integer", "description": "Optional start line (1-indexed)"},
            "end_line": {"type": "integer", "description": "Optional end line (1-indexed)"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Full file content to write"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "str_replace",
        "description": "Replace an exact unique string in a file. Fails if the string appears 0 or 2+ times.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_str": {"type": "string", "description": "Exact string to find (must be unique)"},
            "new_str": {"type": "string", "description": "Replacement string"},
        }, "required": ["path", "old_str", "new_str"]},
    }},
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a shell command. Returns stdout + stderr. Timeout 30s.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "Search file contents with regex (like ripgrep). Returns matches with line numbers.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory or file to search in (default: cwd)"},
            "file_glob": {"type": "string", "description": "Optional glob filter e.g. '*.py'"},
        }, "required": ["pattern"]},
    }},
    {"type": "function", "function": {
        "name": "glob",
        "description": "Find files matching a glob pattern relative to cwd.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Glob pattern e.g. '**/*.ts' or 'src/**/*.py'"},
        }, "required": ["pattern"]},
    }},
    {"type": "function", "function": {
        "name": "list_directory",
        "description": "List files and directories in a path. Respects .gitignore.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directory path (default: cwd)"},
        }, "required": []},
    }},
    # ─── Data Processing Tools ────────────────────────────
    {"type": "function", "function": {
        "name": "inspect_file",
        "description": "Inspect a data file (Excel, CSV, JSON, SQLite, Parquet). Shows columns, types, row counts, sample data. Always use this before processing data files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to data file (.xlsx, .csv, .json, .db, .parquet, .tsv)"},
            "sample_rows": {"type": "integer", "description": "Number of sample rows to show (default: 5)"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "run_python",
        "description": "Execute a Python script to process data. Use for merging, filtering, transforming, aggregating Excel/CSV/JSON files. The script runs in the project directory. Always inspect files first to know exact column names. Output files to the current directory.",
        "parameters": {"type": "object", "properties": {
            "script": {"type": "string", "description": "Full Python script to execute"},
            "description": {"type": "string", "description": "Short description of what the script does"},
        }, "required": ["script"]},
    }},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": "Execute SQL against data files or SQLite databases. For CSV/Excel files, they are auto-loaded into temporary SQLite tables (table name = filename without extension). For .db files, queries run directly.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "SQL query to execute"},
            "source_paths": {"type": "array", "items": {"type": "string"}, "description": "Paths to data files to load as tables (.csv, .xlsx, .db)"},
            "output_path": {"type": "string", "description": "Optional path to save results (.csv or .xlsx)"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "run_node",
        "description": "Execute a Node.js script for JSON processing, API calls, or JS-native operations.",
        "parameters": {"type": "object", "properties": {
            "script": {"type": "string", "description": "Full JavaScript/Node.js script to execute"},
            "description": {"type": "string", "description": "Short description of what the script does"},
        }, "required": ["script"]},
    }},
    {"type": "function", "function": {
        "name": "preview_data",
        "description": "Show a readable ASCII table preview of a data file (Excel, CSV, JSON, Parquet). Shows first N rows in a formatted table.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to data file"},
            "rows": {"type": "integer", "description": "Number of rows to preview (default: 10)"},
            "sheet": {"type": "string", "description": "Sheet name for Excel files (default: first sheet)"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "save_output",
        "description": "Save a result file to ./output/ directory and optionally open it. Use after processing to deliver the final output to the user.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to the result file to save"},
        }, "required": ["path"]},
    }},
]


# ─── Tool Executor ─────────────────────────────────────────

async def execute(name: str, args: dict, cwd: str, auto_approve: bool = False) -> str:
    """Execute a tool and return the result string."""
    try:
        match name:
            case "read_file":
                return _read_file(args.get("path", ""), cwd, args.get("start_line"), args.get("end_line"))
            case "write_file":
                return await _write_file(args.get("path", ""), args.get("content", ""), cwd, auto_approve)
            case "str_replace":
                return await _str_replace(args.get("path", ""), args.get("old_str", ""), args.get("new_str", ""), cwd, auto_approve)
            case "bash":
                return await _bash(args.get("command", ""), cwd, auto_approve)
            case "search_files":
                return _search_files(args.get("pattern", ""), cwd, args.get("path"), args.get("file_glob"))
            case "glob":
                return _glob(args.get("pattern", ""), cwd)
            case "list_directory":
                return _list_directory(args.get("path", "."), cwd)
            # ─── Data Tools ──────────────────────────
            case "inspect_file":
                return data_tools.inspect_file(args.get("path", ""), cwd, args.get("sample_rows", 5))
            case "run_python":
                return await data_tools.run_python(args.get("script", ""), cwd, args.get("description", ""), auto_approve)
            case "run_sql":
                return await data_tools.run_sql(args.get("query", ""), cwd, args.get("source_paths"), args.get("output_path", ""), auto_approve)
            case "run_node":
                return await data_tools.run_node(args.get("script", ""), cwd, args.get("description", ""), auto_approve)
            case "preview_data":
                return data_tools.preview_data(args.get("path", ""), cwd, args.get("rows", 10), args.get("sheet"))
            case "save_output":
                return data_tools.save_output(args.get("path", ""), cwd, auto_approve)
            case _:
                return f"Error: unknown tool '{name}'"
    except Exception as e:
        return f"Error: {e}"


# ─── Tool Implementations ──────────────────────────────────

def _resolve(path: str, cwd: str) -> Path:
    """Resolve a path relative to cwd."""
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def _read_file(path: str, cwd: str, start_line: int = None, end_line: int = None) -> str:
    if not path:
        return "Error: no path provided."
    p = _resolve(path, cwd)
    if not p.exists():
        return f"Error: file not found: {p}"
    if not p.is_file():
        return f"Error: not a file: {p}"

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {e}"

    lines = content.splitlines()
    total = len(lines)

    if start_line is not None or end_line is not None:
        s = max(1, start_line or 1) - 1
        e = min(total, end_line or total)
        lines = lines[s:e]
        renderer.tool_result("read_file", f"{p} (lines {s+1}-{e} of {total})")
    else:
        if total > 2000:
            lines = lines[:2000]
            renderer.tool_result("read_file", f"{p} ({total} lines, showing first 2000)")
        else:
            renderer.tool_result("read_file", f"{p} ({total} lines)")

    numbered = [f"{i+1:>5} │ {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)


async def _write_file(path: str, content: str, cwd: str, auto_approve: bool) -> str:
    if not path:
        return "Error: no path provided."
    p = _resolve(path, cwd)

    # Show diff if file exists
    old_content = ""
    if p.exists():
        try:
            old_content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if old_content:
        added, removed = renderer.show_diff(old_content, content, str(p))
        desc = f"+{added} -{removed}"
    else:
        desc = f"new file ({len(content)} bytes)"
        renderer.info(f"  Creating {p}")

    if not auto_approve:
        answer = input(f"  {renderer.YELLOW}Write {p}?{renderer.RESET} [{renderer.GREEN}y{renderer.RESET}/{renderer.RED}n{renderer.RESET}] ").strip().lower()
        if answer != "y":
            return "Write cancelled by user."

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        renderer.tool_result("write_file", f"Wrote {p} ({desc})")
        return f"File written: {p} ({desc})"
    except Exception as e:
        return f"Error writing file: {e}"


async def _str_replace(path: str, old_str: str, new_str: str, cwd: str, auto_approve: bool) -> str:
    if not path:
        return "Error: no path provided."
    p = _resolve(path, cwd)
    if not p.exists():
        return f"Error: file not found: {p}"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading: {e}"

    count = content.count(old_str)
    if count == 0:
        return f"Error: string not found in {p}. Make sure the old_str matches exactly."
    if count > 1:
        return f"Error: string found {count} times in {p}. Provide more context to make it unique."

    new_content = content.replace(old_str, new_str, 1)

    renderer.show_diff(content, new_content, str(p))

    if not auto_approve:
        answer = input(f"  {renderer.YELLOW}Apply?{renderer.RESET} [{renderer.GREEN}y{renderer.RESET}/{renderer.RED}n{renderer.RESET}] ").strip().lower()
        if answer != "y":
            return "Edit cancelled by user."

    try:
        p.write_text(new_content, encoding="utf-8")
        renderer.tool_result("str_replace", f"Edited {p}")
        return f"Replaced in {p}"
    except Exception as e:
        return f"Error writing: {e}"


# Dangerous command patterns
_BLOCKED = ["rm -rf /", "mkfs", "dd if=", "> /dev/", ":(){ :|:", "chmod -R 777 /"]
_DESTRUCTIVE = ["rm ", "sudo ", "kill ", "killall", "mv /"]


async def _bash(command: str, cwd: str, auto_approve: bool) -> str:
    if not command:
        return "Error: no command."

    cmd_lower = command.strip().lower()
    for pat in _BLOCKED:
        if pat in cmd_lower:
            return f"BLOCKED: '{command}' is too dangerous."

    needs_confirm = any(pat in cmd_lower for pat in _DESTRUCTIVE)

    if needs_confirm and not auto_approve:
        renderer.info(f"  {renderer.YELLOW}$ {command}{renderer.RESET}")
        answer = input(f"  {renderer.YELLOW}Run?{renderer.RESET} [{renderer.GREEN}y{renderer.RESET}/{renderer.RED}n{renderer.RESET}] ").strip().lower()
        if answer != "y":
            return "Command cancelled by user."
    elif not auto_approve:
        renderer.info(f"  {renderer.DIM}$ {command}{renderer.RESET}")

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        result = out
        if err:
            result += f"\n[stderr]: {err}" if result else f"[stderr]: {err}"
        if not result:
            result = f"(exit code {proc.returncode})"
        renderer.tool_result("bash", f"exit {proc.returncode}", success=proc.returncode == 0)
        return result[:5000]
    except asyncio.TimeoutError:
        return "Error: command timed out (30s)."
    except Exception as e:
        return f"Error: {e}"


def _search_files(pattern: str, cwd: str, path: str = None, file_glob: str = None) -> str:
    if not pattern:
        return "Error: no pattern."

    search_path = _resolve(path, cwd) if path else Path(cwd)
    cmd = ["grep", "-rn", "--include", file_glob or "*", "-E", pattern, str(search_path)]

    # Prefer ripgrep if available
    import shutil
    if shutil.which("rg"):
        cmd = ["rg", "-n", "--no-heading", "-e", pattern, str(search_path)]
        if file_glob:
            cmd.extend(["--glob", file_glob])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, cwd=cwd)
        output = result.stdout.strip()
        if not output:
            return f"No matches for '{pattern}'."
        lines = output.splitlines()
        if len(lines) > 50:
            output = "\n".join(lines[:50]) + f"\n... ({len(lines) - 50} more matches)"
        renderer.tool_result("search_files", f"{len(lines)} matches")
        return output
    except subprocess.TimeoutExpired:
        return "Error: search timed out."
    except Exception as e:
        return f"Error: {e}"


def _glob(pattern: str, cwd: str) -> str:
    if not pattern:
        return "Error: no pattern."
    matches = sorted(globlib.glob(pattern, root_dir=cwd, recursive=True))
    if not matches:
        return f"No files matching '{pattern}'."
    result = "\n".join(matches[:100])
    if len(matches) > 100:
        result += f"\n... ({len(matches) - 100} more)"
    renderer.tool_result("glob", f"{len(matches)} files")
    return result


def _list_directory(path: str, cwd: str) -> str:
    p = _resolve(path or ".", cwd)
    if not p.is_dir():
        return f"Error: not a directory: {p}"

    entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    lines = []
    for entry in entries[:100]:
        if entry.name.startswith("."):
            continue
        prefix = "📁" if entry.is_dir() else "  "
        size = ""
        if entry.is_file():
            sz = entry.stat().st_size
            if sz < 1024:
                size = f" ({sz}B)"
            elif sz < 1024 * 1024:
                size = f" ({sz // 1024}KB)"
            else:
                size = f" ({sz // (1024*1024)}MB)"
        lines.append(f"  {prefix} {entry.name}{size}")

    total = len(list(p.iterdir()))
    header = f"{p} ({total} items)"
    return header + "\n" + "\n".join(lines)
