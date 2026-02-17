"""
Data Tools — inspect, run_python, run_sql, run_node, preview_data, save_output.
Autonomous data processing engine for Excel, CSV, SQL, JSON, and more.
"""

import asyncio
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from nex.cli import renderer

SCRIPTS_DIR = ".nex/scripts"
OUTPUT_DIR = "output"
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60
LARGE_TIMEOUT = 300


# ─── Helper: resolve path ─────────────────────────────────

def _resolve(path: str, cwd: str) -> Path:
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def _ensure_lib(lib: str) -> bool:
    """Check if a Python library is available, auto-install if not."""
    try:
        __import__(lib)
        return True
    except ImportError:
        renderer.info(f"  {renderer.YELLOW}Installing {lib}...{renderer.RESET}")
        try:
            subprocess.run(
                ["pip", "install", lib, "-q"],
                capture_output=True, timeout=30,
            )
            return True
        except Exception:
            return False


# ─── inspect_file ──────────────────────────────────────────

def inspect_file(path: str, cwd: str, sample_rows: int = 5) -> str:
    """Inspect a data file: detect type, show structure, columns, sample rows."""
    if not path:
        return "Error: no path provided."
    p = _resolve(path, cwd)
    if not p.exists():
        return f"Error: file not found: {p}"

    ext = p.suffix.lower()
    try:
        if ext in (".xlsx", ".xls"):
            return _inspect_excel(p, sample_rows)
        elif ext in (".csv", ".tsv"):
            return _inspect_csv(p, sample_rows, ext)
        elif ext == ".json":
            return _inspect_json(p, sample_rows)
        elif ext == ".jsonl":
            return _inspect_jsonl(p, sample_rows)
        elif ext == ".parquet":
            return _inspect_parquet(p, sample_rows)
        elif ext == ".db":
            return _inspect_sqlite(p)
        elif ext == ".sql":
            content = p.read_text(encoding="utf-8", errors="replace")[:3000]
            return f"SQL file: {p.name} ({len(content)} chars)\n{content}"
        else:
            size = p.stat().st_size
            return f"File: {p.name} ({size:,} bytes, type: {ext or 'unknown'})"
    except Exception as e:
        return f"Error inspecting {p.name}: {e}"


def _inspect_excel(p: Path, sample_rows: int) -> str:
    _ensure_lib("openpyxl")
    import pandas as pd

    lines = [f"\U0001f4ca {p.name}"]
    xls = pd.ExcelFile(p)
    for i, sheet in enumerate(xls.sheet_names):
        df = pd.read_excel(xls, sheet_name=sheet)
        rows, cols = df.shape
        prefix = "\u2514\u2500\u2500" if i == len(xls.sheet_names) - 1 else "\u251c\u2500\u2500"
        lines.append(f"{prefix} Sheet: \"{sheet}\" ({rows:,} rows \u00d7 {cols} cols)")
        for j, col in enumerate(df.columns):
            dtype = str(df[col].dtype)
            sample = df[col].head(3).tolist()
            sample_str = str(sample)[:60]
            col_prefix = "    \u2514\u2500\u2500" if j == len(df.columns) - 1 else "    \u251c\u2500\u2500"
            lines.append(f"{col_prefix} {col:<20} {dtype:<12} {sample_str}")

    renderer.tool_result("inspect_file", f"{p.name}")
    return "\n".join(lines)


def _inspect_csv(p: Path, sample_rows: int, ext: str) -> str:
    import pandas as pd

    delimiter = "\t" if ext == ".tsv" else ","
    # Try to detect encoding
    encoding = "utf-8"
    try:
        p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        encoding = "latin-1"

    df = pd.read_csv(p, sep=delimiter, encoding=encoding, nrows=1000)
    rows_total = sum(1 for _ in open(p, encoding=encoding, errors="replace")) - 1
    cols = len(df.columns)

    lines = [f"\U0001f4ca {p.name} ({rows_total:,} rows \u00d7 {cols} cols)"]
    lines.append(f"  Delimiter: {'TAB' if delimiter == chr(9) else repr(delimiter)} | Encoding: {encoding}")

    for j, col in enumerate(df.columns):
        dtype = str(df[col].dtype)
        nulls = df[col].isna().sum()
        sample = df[col].head(3).tolist()
        sample_str = str(sample)[:60]
        null_info = f" ({nulls} nulls)" if nulls > 0 else ""
        prefix = "  \u2514\u2500\u2500" if j == len(df.columns) - 1 else "  \u251c\u2500\u2500"
        lines.append(f"{prefix} {col:<20} {dtype:<12}{null_info} {sample_str}")

    renderer.tool_result("inspect_file", f"{p.name} ({rows_total:,} rows)")
    return "\n".join(lines)


def _inspect_json(p: Path, sample_rows: int) -> str:
    content = p.read_text(encoding="utf-8", errors="replace")
    data = json.loads(content)

    lines = [f"\U0001f4ca {p.name}"]
    if isinstance(data, list):
        lines.append(f"  Type: Array ({len(data):,} items)")
        if data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            lines.append(f"  Keys: {', '.join(keys[:15])}")
            if len(keys) > 15:
                lines.append(f"  ... and {len(keys) - 15} more keys")
    elif isinstance(data, dict):
        lines.append(f"  Type: Object ({len(data)} top-level keys)")
        for k in list(data.keys())[:15]:
            v = data[k]
            vtype = type(v).__name__
            if isinstance(v, list):
                vtype = f"array[{len(v)}]"
            elif isinstance(v, dict):
                vtype = f"object({len(v)} keys)"
            lines.append(f"  \u251c\u2500\u2500 {k}: {vtype}")

    renderer.tool_result("inspect_file", f"{p.name}")
    return "\n".join(lines)


def _inspect_jsonl(p: Path, sample_rows: int) -> str:
    lines_data = []
    total = 0
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            total += 1
            if len(lines_data) < sample_rows:
                try:
                    lines_data.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    result = [f"\U0001f4ca {p.name} ({total:,} lines)"]
    if lines_data and isinstance(lines_data[0], dict):
        keys = list(lines_data[0].keys())
        result.append(f"  Keys: {', '.join(keys[:15])}")
    renderer.tool_result("inspect_file", f"{p.name} ({total:,} lines)")
    return "\n".join(result)


def _inspect_parquet(p: Path, sample_rows: int) -> str:
    _ensure_lib("pyarrow")
    import pandas as pd
    df = pd.read_parquet(p)
    rows, cols = df.shape

    lines = [f"\U0001f4ca {p.name} ({rows:,} rows \u00d7 {cols} cols)"]
    for j, col in enumerate(df.columns):
        dtype = str(df[col].dtype)
        prefix = "  \u2514\u2500\u2500" if j == len(df.columns) - 1 else "  \u251c\u2500\u2500"
        lines.append(f"{prefix} {col:<20} {dtype}")

    renderer.tool_result("inspect_file", f"{p.name} ({rows:,} rows)")
    return "\n".join(lines)


def _inspect_sqlite(p: Path) -> str:
    conn = sqlite3.connect(str(p))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]

    lines = [f"\U0001f4ca {p.name} (SQLite database)"]
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM \"{t}\"")
        count = cursor.fetchone()[0]
        cursor.execute(f"PRAGMA table_info(\"{t}\")")
        columns = cursor.fetchall()
        lines.append(f"  \u251c\u2500\u2500 Table: {t} ({count:,} rows)")
        for col in columns:
            cid, name, ctype, notnull, default, pk = col
            pk_mark = " PK" if pk else ""
            lines.append(f"      \u251c\u2500\u2500 {name:<20} {ctype:<12}{pk_mark}")

    conn.close()
    renderer.tool_result("inspect_file", f"{p.name} ({len(tables)} tables)")
    return "\n".join(lines)


# ─── run_python ────────────────────────────────────────────

async def run_python(
    script: str,
    cwd: str,
    description: str = "",
    auto_approve: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Execute a Python script in a subprocess, capture output."""
    if not script:
        return "Error: no script provided."

    # Show the script to the user
    renderer.script_preview(script, "python", description)

    if not auto_approve:
        answer = input(
            f"  {renderer.YELLOW}Run this?{renderer.RESET} "
            f"[{renderer.GREEN}y{renderer.RESET}/"
            f"{renderer.RED}n{renderer.RESET}/"
            f"{renderer.CYAN}e{renderer.RESET}dit] "
        ).strip().lower()
        if answer == "n":
            return "Script cancelled by user."
        elif answer == "e":
            script = _edit_script(script)
            if script is None:
                return "Edit cancelled."

    # Write to temp file
    script_path = Path(cwd) / ".nex" / "tmp"
    script_path.mkdir(parents=True, exist_ok=True)
    script_file = script_path / f"run_{int(time.time())}.py"
    script_file.write_text(script, encoding="utf-8")

    spinner = renderer.Spinner("Running Python script")
    spinner.start()
    start = time.time()

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", str(script_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        elapsed = time.time() - start
        spinner.stop()

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            result = f"Error (exit {proc.returncode}):\n{err}\n{out}"
            renderer.tool_result("run_python", f"failed ({elapsed:.1f}s)", success=False)
        else:
            result = out[:5000]
            if err:
                result += f"\n[stderr]: {err[:1000]}"
            renderer.tool_result("run_python", f"done ({elapsed:.1f}s)")

        return result

    except asyncio.TimeoutError:
        spinner.stop()
        return f"Error: script timed out ({timeout}s)."
    except Exception as e:
        spinner.stop()
        return f"Error running script: {e}"
    finally:
        # Clean up temp file
        try:
            script_file.unlink(missing_ok=True)
        except Exception:
            pass


def _edit_script(script: str) -> str | None:
    """Open script in $EDITOR for user modification."""
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp_path = f.name
    try:
        subprocess.run([editor, tmp_path])
        return Path(tmp_path).read_text(encoding="utf-8")
    except Exception:
        renderer.error(f"Failed to open editor ({editor}).")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ─── run_sql ───────────────────────────────────────────────

async def run_sql(
    query: str,
    cwd: str,
    source_paths: list[str] | None = None,
    output_path: str = "",
    auto_approve: bool = False,
) -> str:
    """Execute SQL against files or SQLite databases."""
    if not query:
        return "Error: no query provided."

    renderer.script_preview(query, "sql")

    if not auto_approve:
        answer = input(
            f"  {renderer.YELLOW}Execute?{renderer.RESET} "
            f"[{renderer.GREEN}y{renderer.RESET}/{renderer.RED}n{renderer.RESET}] "
        ).strip().lower()
        if answer != "y":
            return "SQL cancelled by user."

    # Check if any source is a .db file
    db_path = None
    file_paths = []
    if source_paths:
        for sp in source_paths:
            p = _resolve(sp, cwd)
            if p.suffix.lower() == ".db":
                db_path = p
            else:
                file_paths.append(p)

    spinner = renderer.Spinner("Running SQL query")
    spinner.start()
    start = time.time()

    try:
        _ensure_lib("pandas")
        import pandas as pd

        if db_path and db_path.exists():
            # Mode A: query existing SQLite DB
            conn = sqlite3.connect(str(db_path))
            df = pd.read_sql_query(query, conn)
            conn.close()
            source_info = f"SQLite: {db_path.name}"
        else:
            # Mode B: load files into temp SQLite
            conn = sqlite3.connect(":memory:")
            loaded = []
            for fp in file_paths:
                table_name = fp.stem.replace("-", "_").replace(" ", "_")
                if fp.suffix.lower() in (".xlsx", ".xls"):
                    _ensure_lib("openpyxl")
                    df_tmp = pd.read_excel(fp)
                elif fp.suffix.lower() in (".csv", ".tsv"):
                    sep = "\t" if fp.suffix.lower() == ".tsv" else ","
                    df_tmp = pd.read_csv(fp, sep=sep)
                elif fp.suffix.lower() == ".json":
                    df_tmp = pd.read_json(fp)
                else:
                    continue
                df_tmp.to_sql(table_name, conn, index=False, if_exists="replace")
                loaded.append(f"{fp.name} -> {table_name} ({len(df_tmp):,} rows)")

            df = pd.read_sql_query(query, conn)
            conn.close()
            source_info = " | ".join(loaded) if loaded else "in-memory"

        elapsed = time.time() - start
        spinner.stop()

        rows, cols = df.shape
        result_lines = [f"Query returned {rows:,} rows x {cols} cols"]
        result_lines.append(f"Source: {source_info}")

        # Show preview
        preview = df.head(10).to_string()
        result_lines.append(preview)

        # Save output if requested
        if output_path:
            out_p = _resolve(output_path, cwd)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            if out_p.suffix.lower() in (".xlsx", ".xls"):
                df.to_excel(out_p, index=False)
            else:
                df.to_csv(out_p, index=False)
            result_lines.append(f"Saved: {out_p}")

        renderer.tool_result("run_sql", f"{rows:,} rows ({elapsed:.1f}s)")
        return "\n".join(result_lines)

    except Exception as e:
        spinner.stop()
        return f"SQL Error: {e}"


# ─── run_node ──────────────────────────────────────────────

async def run_node(
    script: str,
    cwd: str,
    description: str = "",
    auto_approve: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Execute a Node.js script in a subprocess."""
    if not script:
        return "Error: no script provided."
    if not shutil.which("node"):
        return "Error: Node.js not found. Install it to use run_node."

    renderer.script_preview(script, "javascript", description)

    if not auto_approve:
        answer = input(
            f"  {renderer.YELLOW}Run this?{renderer.RESET} "
            f"[{renderer.GREEN}y{renderer.RESET}/{renderer.RED}n{renderer.RESET}] "
        ).strip().lower()
        if answer != "y":
            return "Script cancelled by user."

    script_path = Path(cwd) / ".nex" / "tmp"
    script_path.mkdir(parents=True, exist_ok=True)
    script_file = script_path / f"run_{int(time.time())}.js"
    script_file.write_text(script, encoding="utf-8")

    spinner = renderer.Spinner("Running Node.js script")
    spinner.start()
    start = time.time()

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", str(script_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        elapsed = time.time() - start
        spinner.stop()

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            result = f"Error (exit {proc.returncode}):\n{err}\n{out}"
            renderer.tool_result("run_node", f"failed ({elapsed:.1f}s)", success=False)
        else:
            result = out[:5000]
            if err:
                result += f"\n[stderr]: {err[:1000]}"
            renderer.tool_result("run_node", f"done ({elapsed:.1f}s)")

        return result

    except asyncio.TimeoutError:
        spinner.stop()
        return f"Error: script timed out ({timeout}s)."
    except Exception as e:
        spinner.stop()
        return f"Error running script: {e}"
    finally:
        try:
            script_file.unlink(missing_ok=True)
        except Exception:
            pass


# ─── preview_data ──────────────────────────────────────────

def preview_data(path: str, cwd: str, rows: int = 10, sheet: str = None) -> str:
    """Show a readable ASCII table preview of a data file."""
    if not path:
        return "Error: no path provided."
    p = _resolve(path, cwd)
    if not p.exists():
        return f"Error: file not found: {p}"

    _ensure_lib("pandas")
    import pandas as pd

    try:
        ext = p.suffix.lower()
        if ext in (".xlsx", ".xls"):
            _ensure_lib("openpyxl")
            df = pd.read_excel(p, sheet_name=sheet or 0)
        elif ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            df = pd.read_csv(p, sep=sep)
        elif ext == ".json":
            df = pd.read_json(p)
        elif ext == ".parquet":
            _ensure_lib("pyarrow")
            df = pd.read_parquet(p)
        else:
            return f"Cannot preview file type: {ext}"

        total_rows = len(df)
        preview_df = df.head(rows)

        # Build ASCII table
        table = _ascii_table(preview_df)
        table += f"\n{rows if total_rows > rows else total_rows} of {total_rows:,} rows shown"

        renderer.tool_result("preview_data", f"{p.name} ({total_rows:,} rows)")
        return table

    except Exception as e:
        return f"Error previewing {p.name}: {e}"


def _ascii_table(df) -> str:
    """Render a pandas DataFrame as a clean ASCII table."""
    cols = list(df.columns)
    # Calculate column widths
    widths = {}
    for col in cols:
        vals = [str(col)] + [str(v)[:30] for v in df[col].head(20)]
        widths[col] = min(30, max(len(v) for v in vals))

    def row_str(values):
        cells = []
        for col, val in zip(cols, values):
            cells.append(f" {str(val)[:widths[col]]:<{widths[col]}} ")
        return "\u2502" + "\u2502".join(cells) + "\u2502"

    # Top border
    top = "\u250c" + "\u252c".join("\u2500" * (widths[c] + 2) for c in cols) + "\u2510"
    # Header separator
    sep = "\u251c" + "\u253c".join("\u2500" * (widths[c] + 2) for c in cols) + "\u2524"
    # Bottom border
    bot = "\u2514" + "\u2534".join("\u2500" * (widths[c] + 2) for c in cols) + "\u2518"

    lines = [top, row_str(cols), sep]
    for _, row in df.iterrows():
        lines.append(row_str([row[c] for c in cols]))
    lines.append(bot)

    return "\n".join(lines)


# ─── save_output ───────────────────────────────────────────

def save_output(path: str, cwd: str, auto_approve: bool = False) -> str:
    """Move a result file to ./output/ and optionally open it."""
    if not path:
        return "Error: no path provided."
    p = _resolve(path, cwd)
    if not p.exists():
        return f"Error: file not found: {p}"

    output_dir = Path(cwd) / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / p.name

    # Don't move if already in output dir
    if p.parent.resolve() == output_dir.resolve():
        dest = p
    else:
        shutil.copy2(str(p), str(dest))

    size = dest.stat().st_size
    if size < 1024:
        size_str = f"{size}B"
    elif size < 1024 * 1024:
        size_str = f"{size // 1024}KB"
    else:
        size_str = f"{size // (1024 * 1024)}MB"

    renderer.tool_result("save_output", f"Saved: ./{OUTPUT_DIR}/{dest.name} ({size_str})")

    # Offer to open
    if not auto_approve:
        answer = input(
            f"  {renderer.CYAN}Open this file?{renderer.RESET} "
            f"[{renderer.GREEN}y{renderer.RESET}/{renderer.RED}n{renderer.RESET}] "
        ).strip().lower()
        if answer == "y":
            _open_file(dest)

    return f"Saved: {dest} ({size_str})"


def _open_file(path: Path):
    """Open a file with the system default application."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(path)])
        elif system == "Windows":
            os.startfile(str(path))
    except Exception:
        renderer.info(f"  Could not open file automatically: {path}")


# ─── Script Library ────────────────────────────────────────

def save_script(script: str, name: str, cwd: str, lang: str = "py") -> str:
    """Save a script to .nex/scripts/ for reuse."""
    scripts_dir = Path(cwd) / SCRIPTS_DIR
    if lang == "sql":
        scripts_dir = scripts_dir / "sql"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize name
    safe_name = re.sub(r'[^\w\-]', '_', name.lower())
    if not safe_name.endswith(f".{lang}"):
        safe_name += f".{lang}"

    script_path = scripts_dir / safe_name
    script_path.write_text(script, encoding="utf-8")
    renderer.tool_result("save_script", f"Saved: {script_path.relative_to(cwd)}")
    return f"Saved: {script_path}"


def list_scripts(cwd: str) -> str:
    """List all saved scripts."""
    scripts_dir = Path(cwd) / SCRIPTS_DIR
    if not scripts_dir.exists():
        return "No saved scripts."

    scripts = []
    for ext in ("*.py", "*.sql", "*.js"):
        scripts.extend(scripts_dir.rglob(ext))

    if not scripts:
        return "No saved scripts."

    lines = [f"\nSaved scripts ({len(scripts)}):"]
    for i, s in enumerate(sorted(scripts), 1):
        rel = s.relative_to(scripts_dir)
        # Try to read first comment line as description
        desc = ""
        try:
            first_lines = s.read_text(encoding="utf-8").splitlines()[:5]
            for line in first_lines:
                if line.startswith("#") or line.startswith("--") or line.startswith("//"):
                    desc = line.lstrip("#-/ ").strip()
                    break
        except Exception:
            pass
        desc_str = f"  {renderer.DIM}{desc}{renderer.RESET}" if desc else ""
        lines.append(f"  [{i}] {renderer.CYAN}{rel}{renderer.RESET}{desc_str}")

    return "\n".join(lines)
