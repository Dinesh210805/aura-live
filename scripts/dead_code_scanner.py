#!/usr/bin/env python3
"""
dead_code_scanner.py — Pure static analysis. No AI. No external deps beyond stdlib + optional ruff/vulture.

Finds:
  1. Unused imports (per-file, AST)
  2. Defined but never called functions/classes (cross-file grep)
  3. Unreachable code (after return/raise/continue/break)
  4. Orphaned Python files (never imported anywhere)
  5. Large commented-out blocks (Python + Kotlin)
  6. Duplicate function bodies (exact hash match)
  7. Empty except blocks
  8. Kotlin: unused @Composable functions (cross-file)

Usage:
    python scripts/dead_code_scanner.py [--scope <folder>] [--output report.md] [--min-confidence 80]

Examples:
    python scripts/dead_code_scanner.py
    python scripts/dead_code_scanner.py --scope agents
    python scripts/dead_code_scanner.py --scope agents --output cleanup_report.md
"""

import ast
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {
    "__pycache__", ".git", ".github", "Google-Edge-AI-gallery-main",
    "node_modules", ".gradle", "build", ".idea", "dist", ".venv", "venv", "env",
    "implementation paper", "implementation_paper",
}
SAFE_FILES = {"main.py", "constants.py", "export_paper.py", "conftest.py"}
SAFE_DIRS = {"tests", "scripts"}
STALE_LOG_DIRS = ["logs", "data/failure_screenshots", "terminal_logs"]

# ─── helpers ──────────────────────────────────────────────────────────────────

def iter_python_files(scope: Path) -> list[Path]:
    results = []
    for dirpath, dirnames, filenames in os.walk(scope):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not any(
                str(Path(dirpath) / d).startswith(str(ROOT / s)) for s in SAFE_DIRS
            )
        ]
        for f in filenames:
            if f.endswith(".py"):
                results.append(Path(dirpath) / f)
    return results


def iter_kotlin_files(scope: Path) -> list[Path]:
    results = []
    for dirpath, dirnames, filenames in os.walk(scope):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f.endswith(".kt"):
                results.append(Path(dirpath) / f)
    return results


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def read_source(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def parse_ast(src: str, filepath: Path):
    try:
        return ast.parse(src, filename=str(filepath))
    except SyntaxError:
        return None


# ─── check 1: unused imports ──────────────────────────────────────────────────

def find_unused_imports(filepath: Path, src: str) -> list[dict]:
    tree = parse_ast(src, filepath)
    if not tree:
        return []

    issues = []
    # Collect all names used in the file (identifiers, attributes)
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # collect root name: e.g. os.path → "os"
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                used_names.add(root.id)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                used_names.add(node.func.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname if alias.asname else alias.name.split(".")[0]
                if local_name not in used_names and local_name != "_":
                    issues.append({
                        "file": rel(filepath),
                        "line": node.lineno,
                        "code": f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                        "kind": "unused_import",
                    })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname if alias.asname else alias.name
                if local_name not in used_names and local_name != "_":
                    issues.append({
                        "file": rel(filepath),
                        "line": node.lineno,
                        "code": f"from {module} import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                        "kind": "unused_import",
                    })
    return issues


# ─── check 2: unreachable code ────────────────────────────────────────────────

TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)

def find_unreachable_code(filepath: Path, src: str) -> list[dict]:
    tree = parse_ast(src, filepath)
    if not tree:
        return []
    issues = []

    class Visitor(ast.NodeVisitor):
        def _check_body(self, stmts):
            for i, stmt in enumerate(stmts):
                if isinstance(stmt, TERMINATORS) and i < len(stmts) - 1:
                    next_stmt = stmts[i + 1]
                    # skip trailing pass / docstring
                    if isinstance(next_stmt, ast.Pass):
                        continue
                    if isinstance(next_stmt, ast.Expr) and isinstance(next_stmt.value, ast.Constant):
                        continue
                    issues.append({
                        "file": rel(filepath),
                        "line": next_stmt.lineno,
                        "code": f"unreachable after {type(stmt).__name__} at line {stmt.lineno}",
                        "kind": "unreachable_code",
                    })
                    break  # only report first unreachable per block
                self.visit(stmt)

        def visit_FunctionDef(self, node):
            self._check_body(node.body)
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_If(self, node):
            # detect `if False:` blocks
            if isinstance(node.test, ast.Constant) and node.test.value is False:
                issues.append({
                    "file": rel(filepath),
                    "line": node.lineno,
                    "code": "if False: block — always dead",
                    "kind": "unreachable_code",
                })
            self._check_body(node.body)
            self._check_body(node.orelse)

    Visitor().visit(tree)
    return issues


# ─── check 3: empty except blocks ─────────────────────────────────────────────

def find_empty_except(filepath: Path, src: str) -> list[dict]:
    tree = parse_ast(src, filepath)
    if not tree:
        return []
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            body = node.body
            if all(isinstance(s, (ast.Pass, ast.Ellipsis)) or
                   (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                   for s in body):
                issues.append({
                    "file": rel(filepath),
                    "line": node.lineno,
                    "code": f"except {ast.unparse(node.type) if node.type else 'bare'}: pass/ellipsis",
                    "kind": "empty_except",
                })
    return issues


# ─── check 4: duplicate function bodies ───────────────────────────────────────

def collect_function_hashes(filepath: Path, src: str) -> list[tuple[str, int, str, str]]:
    """Returns list of (hash, lineno, funcname, filepath_rel)"""
    tree = parse_ast(src, filepath)
    if not tree:
        return []
    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node.body) <= 2:  # too short to be interesting
                continue
            try:
                body_src = ast.unparse(node)
                # strip name so rename doesn't break dedup
                body_src = re.sub(r'^(async )?def \w+', 'def __fn__', body_src)
                h = hashlib.md5(body_src.encode()).hexdigest()
                results.append((h, node.lineno, node.name, rel(filepath)))
            except Exception:
                pass
    return results


# ─── check 5: orphaned Python files ───────────────────────────────────────────

def find_orphaned_files(all_py_files: list[Path]) -> list[dict]:
    """Files whose module name is never imported anywhere."""
    # Build set of all imported module names (first component)
    imported: set[str] = set()
    for fp in all_py_files:
        src = read_source(fp)
        if not src:
            continue
        tree = parse_ast(src, fp)
        if not tree:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    imported.update(parts)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    parts = node.module.split(".")
                    imported.update(parts)
                for alias in node.names:
                    imported.add(alias.name)

    orphans = []
    for fp in all_py_files:
        stem = fp.stem
        if stem in SAFE_FILES or fp.name in SAFE_FILES:
            continue
        if stem == "__init__":
            continue
        if stem not in imported:
            orphans.append({
                "file": rel(fp),
                "kind": "orphaned_file",
                "code": "module never imported anywhere in scanned files",
            })
    return orphans


# ─── check 6: large commented-out blocks (Python) ─────────────────────────────

def find_large_comment_blocks(filepath: Path, src: str, min_lines: int = 8) -> list[dict]:
    issues = []
    lines = src.splitlines()
    run_start = None
    run_len = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        is_comment = stripped.startswith("#") and len(stripped) > 1
        if is_comment:
            if run_start is None:
                run_start = i
            run_len += 1
        else:
            if run_len >= min_lines:
                issues.append({
                    "file": rel(filepath),
                    "line": run_start,
                    "code": f"commented block lines {run_start}–{run_start + run_len - 1} ({run_len} lines)",
                    "kind": "large_comment_block",
                })
            run_start = None
            run_len = 0
    if run_len >= min_lines:
        issues.append({
            "file": rel(filepath),
            "line": run_start,
            "code": f"commented block lines {run_start}–{run_start + run_len - 1} ({run_len} lines)",
            "kind": "large_comment_block",
        })
    return issues


# ─── check 7: Kotlin unused @Composable ───────────────────────────────────────

def find_unused_composables(kt_files: list[Path]) -> list[dict]:
    # Collect all @Composable function names
    composables: dict[str, Path] = {}
    composable_re = re.compile(r'@Composable\s+(?:fun\s+)(\w+)\s*\(', re.MULTILINE)
    fun_re = re.compile(r'(?:^|\s)fun\s+(\w+)\s*[(<]', re.MULTILINE)

    for fp in kt_files:
        src = read_source(fp)
        if not src:
            continue
        # Check for @Composable annotation followed by fun
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "@Composable" in line:
                # look ahead for `fun FuncName(`
                for j in range(i, min(i + 3, len(lines))):
                    m = re.search(r'\bfun\s+(\w+)\s*[(<@]', lines[j])
                    if m:
                        composables[m.group(1)] = fp
                        break

    if not composables:
        return []

    # Build a full-text index of all Kotlin source
    all_kt_src = ""
    for fp in kt_files:
        src = read_source(fp)
        if src:
            all_kt_src += src + "\n"

    issues = []
    for name, defined_in in composables.items():
        # A composable is "used" if its name appears as a call (followed by `(` or `{`)
        # anywhere in the entire kt corpus (outside its own definition)
        pattern = re.compile(rf'\b{re.escape(name)}\s*' + r'[({]')
        all_except_self = all_kt_src.replace(read_source(defined_in) or "", "", 1)
        if not pattern.search(all_except_self):
            issues.append({
                "file": rel(defined_in),
                "line": None,
                "code": f"@Composable fun {name}() — no call sites found",
                "kind": "unused_composable",
            })
    return issues


# ─── check 8: Kotlin large commented blocks ───────────────────────────────────

def find_kt_comment_blocks(filepath: Path, src: str, min_lines: int = 8) -> list[dict]:
    issues = []
    lines = src.splitlines()
    # single-line // comments
    run_start = None
    run_len = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        is_comment = stripped.startswith("//") and len(stripped) > 2
        if is_comment:
            if run_start is None:
                run_start = i
            run_len += 1
        else:
            if run_len >= min_lines:
                issues.append({
                    "file": rel(filepath),
                    "line": run_start,
                    "code": f"// commented block lines {run_start}–{run_start + run_len - 1} ({run_len} lines)",
                    "kind": "kt_comment_block",
                })
            run_start = None
            run_len = 0
    return issues


# ─── check 9: stale log / data files ──────────────────────────────────────────

def find_stale_files() -> list[dict]:
    import time
    now = time.time()
    TWO_WEEKS = 14 * 86400
    results = []
    for d in STALE_LOG_DIRS:
        full = ROOT / d
        if not full.exists():
            continue
        for f in full.iterdir():
            if f.is_file():
                age_days = (now - f.stat().st_mtime) / 86400
                size_kb = f.stat().st_size / 1024
                results.append({
                    "file": rel(f),
                    "kind": "stale_file",
                    "code": f"{age_days:.0f}d old, {size_kb:.1f} KB",
                })
    return results


# ─── check 10: defined but never cross-referenced functions ───────────────────

def find_uncalled_functions(all_py_files: list[Path]) -> list[dict]:
    """Functions defined in one file but never referenced in ANY other file."""
    # Step 1: collect all defined function names (skip private/dunder)
    defined: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for fp in all_py_files:
        src = read_source(fp)
        if not src:
            continue
        tree = parse_ast(src, fp)
        if not tree:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if name.startswith("__") and name.endswith("__"):
                    continue  # skip dunders
                defined[name].append((fp, node.lineno))

    # Step 2: build corpus of all identifiers used across all files
    all_used: set[str] = set()
    for fp in all_py_files:
        src = read_source(fp)
        if not src:
            continue
        # Use regex on raw text for speed (catches string-based calls too)
        all_used.update(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', src))

    # Step 3: a function is "uncalled" if its name only appears in its defining file
    issues = []
    for name, locations in defined.items():
        if name in ("main", "setup", "teardown", "create_app", "app"):
            continue  # common entry points
        # Check if name appears in any OTHER file's text
        defining_files = {fp for fp, _ in locations}
        referenced_elsewhere = False
        for fp in all_py_files:
            if fp in defining_files:
                continue
            src = read_source(fp)
            if src and re.search(rf'\b{re.escape(name)}\b', src):
                referenced_elsewhere = True
                break
        if not referenced_elsewhere:
            for fp, lineno in locations:
                issues.append({
                    "file": rel(fp),
                    "line": lineno,
                    "code": f"def {name}() — no references in other files",
                    "kind": "uncalled_function",
                })
    return issues


# ─── ruff integration (optional, more accurate) ───────────────────────────────

def run_ruff(scope: Path) -> list[dict]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select", "F401,F811,F841",
             "--output-format", "json", str(scope),
             "--exclude", "Google-Edge-AI-gallery-main"],
            capture_output=True, text=True, cwd=ROOT
        )
        data = json.loads(result.stdout or "[]")
        return [{
            "file": item["filename"].replace(str(ROOT) + os.sep, "").replace("\\", "/"),
            "line": item["location"]["row"],
            "code": item["message"],
            "kind": f"ruff_{item['code']}",
        } for item in data]
    except Exception:
        return []


def run_vulture(scope: Path, min_confidence: int = 80) -> list[dict]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "vulture", str(scope),
             f"--min-confidence={min_confidence}",
             "--exclude", "Google-Edge-AI-gallery-main,tests,scripts"],
            capture_output=True, text=True, cwd=ROOT
        )
        issues = []
        for line in result.stdout.splitlines():
            # format: path/file.py:lineno: message (confidence%)
            m = re.match(r"^(.+?):(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)", line)
            if m:
                issues.append({
                    "file": m.group(1).replace(str(ROOT) + os.sep, "").replace("\\", "/"),
                    "line": int(m.group(2)),
                    "code": m.group(3),
                    "kind": f"vulture_{int(m.group(4))}pct",
                })
        return issues
    except Exception:
        return []


# ─── report formatting ────────────────────────────────────────────────────────

TIER_ORDER = {
    "ruff_F401": ("🔴", "Unused Imports (ruff)"),
    "ruff_F811": ("🔴", "Redefined Unused Names (ruff)"),
    "ruff_F841": ("🔴", "Unused Local Variables (ruff)"),
    "unused_import": ("🔴", "Unused Imports (AST)"),
    "unreachable_code": ("🔴", "Unreachable Code"),
    "empty_except": ("🟡", "Empty Except Blocks"),
    "uncalled_function": ("🟡", "Functions Never Called From Other Files"),
    "orphaned_file": ("🟡", "Orphaned Files (Never Imported)"),
    "large_comment_block": ("🟢", "Large Commented Blocks (Python)"),
    "kt_comment_block": ("🟢", "Large Commented Blocks (Kotlin)"),
    "unused_composable": ("🟡", "Unused @Composable Functions"),
    "duplicate_body": ("🟡", "Duplicate Function Bodies"),
    "stale_file": ("🟢", "Stale Log / Data Files"),
    "vulture_80pct": ("🔴", "Dead Code — vulture ≥80%"),
    "vulture_60pct": ("🟡", "Dead Code — vulture 60–79%"),
}

def build_report(all_issues: list[dict], duplicate_groups: list, args) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# AURA Dead Code Scanner Report",
        f"Generated: {now}  ",
        f"Scope: `{args.scope or '(entire project)'}`  ",
        f"Min vulture confidence: {args.min_confidence}%  ",
        "",
    ]

    # summary counts
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for issue in all_issues:
        by_kind[issue["kind"]].append(issue)

    lines += [
        "## Summary",
        f"| Category | Count |",
        f"|----------|-------|",
    ]
    total = 0
    for kind, (tier, label) in TIER_ORDER.items():
        count = len(by_kind.get(kind, []))
        if count:
            lines.append(f"| {tier} {label} | {count} |")
            total += count
    if duplicate_groups:
        lines.append(f"| 🟡 Duplicate Function Bodies | {len(duplicate_groups)} groups |")
    lines += [f"| **Total** | **{total}** |", ""]

    # group by tier
    for tier_label, tier_symbol in [("🔴 Safe to Remove", "🔴"), ("🟡 Needs Review", "🟡"), ("🟢 Informational", "🟢")]:
        tier_issues = [
            (kind, label, issues)
            for kind, (sym, label) in TIER_ORDER.items()
            if sym == tier_symbol
            for issues in [by_kind.get(kind, [])]
            if issues
        ]
        if not tier_issues:
            continue
        lines += [f"## {tier_label}", ""]
        for kind, label, issues in tier_issues:
            lines += [f"### {label}", ""]
            if kind in ("orphaned_file", "stale_file"):
                lines.append("| File | Details |")
                lines.append("|------|---------|")
                for i in issues:
                    lines.append(f"| `{i['file']}` | {i['code']} |")
            else:
                lines.append("| File | Line | Code |")
                lines.append("|------|------|------|")
                for i in sorted(issues, key=lambda x: (x["file"], x.get("line") or 0)):
                    line_ref = str(i.get("line") or "—")
                    lines.append(f"| `{i['file']}` | {line_ref} | {i['code']} |")
            lines.append("")

    # duplicates
    if duplicate_groups:
        lines += ["## 🟡 Duplicate Function Bodies", ""]
        lines.append("Functions with identical bodies (after name-stripping). Consider consolidating.")
        lines.append("")
        for group in duplicate_groups:
            lines.append(f"**Duplicate group** ({len(group)} occurrences):")
            for h, lineno, name, filepath in group:
                lines.append(f"  - `{filepath}:{lineno}` — `def {name}()`")
            lines.append("")

    return "\n".join(lines)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dead code scanner — no AI, pure static analysis")
    parser.add_argument("--scope", default=None,
                        help="Subdirectory to scan (relative to project root). Default: entire project.")
    parser.add_argument("--output", default=None,
                        help="Write Markdown report to this file. Default: print to stdout.")
    parser.add_argument("--min-confidence", type=int, default=80,
                        help="Minimum vulture confidence %% (default: 80)")
    parser.add_argument("--no-ruff", action="store_true", help="Skip ruff (use built-in AST only)")
    parser.add_argument("--no-vulture", action="store_true", help="Skip vulture")
    parser.add_argument("--no-kotlin", action="store_true", help="Skip Kotlin analysis")
    args = parser.parse_args()

    scope = ROOT / args.scope if args.scope else ROOT
    if not scope.exists():
        print(f"ERROR: scope path does not exist: {scope}", file=sys.stderr)
        sys.exit(1)

    print(f"[scanner] Root: {ROOT}", file=sys.stderr)
    print(f"[scanner] Scope: {scope}", file=sys.stderr)

    py_files = iter_python_files(scope)
    safe_py = [f for f in py_files if f.name not in SAFE_FILES and not any(
        str(f).startswith(str(ROOT / s)) for s in SAFE_DIRS)]
    print(f"[scanner] Found {len(py_files)} Python files ({len(safe_py)} scannable)", file=sys.stderr)

    all_issues: list[dict] = []

    # ── ruff (preferred) ──
    if not args.no_ruff:
        print("[scanner] Running ruff ...", file=sys.stderr)
        ruff_issues = run_ruff(scope)
        if ruff_issues:
            print(f"[scanner]   ruff: {len(ruff_issues)} issues", file=sys.stderr)
            all_issues.extend(ruff_issues)
        else:
            print("[scanner]   ruff not available or no issues — falling back to AST unused import check", file=sys.stderr)
            for fp in safe_py:
                src = read_source(fp)
                if src:
                    all_issues.extend(find_unused_imports(fp, src))

    # ── vulture (preferred for dead functions) ──
    if not args.no_vulture:
        print("[scanner] Running vulture ...", file=sys.stderr)
        vult_issues = run_vulture(scope, args.min_confidence)
        if vult_issues:
            print(f"[scanner]   vulture: {len(vult_issues)} issues", file=sys.stderr)
            all_issues.extend(vult_issues)
        else:
            print("[scanner]   vulture not available — falling back to cross-file reference check", file=sys.stderr)
            print("[scanner]   Cross-referencing functions (slow on large codebases) ...", file=sys.stderr)
            all_issues.extend(find_uncalled_functions(safe_py))

    # ── AST checks (always run) ──
    print("[scanner] Running AST checks ...", file=sys.stderr)
    func_hashes: list[tuple[str, int, str, str]] = []
    for fp in safe_py:
        src = read_source(fp)
        if not src:
            continue
        all_issues.extend(find_unreachable_code(fp, src))
        all_issues.extend(find_empty_except(fp, src))
        all_issues.extend(find_large_comment_blocks(fp, src))
        func_hashes.extend(collect_function_hashes(fp, src))

    # ── duplicate bodies ──
    hash_groups: dict[str, list] = defaultdict(list)
    for entry in func_hashes:
        hash_groups[entry[0]].append(entry)
    duplicate_groups = [g for g in hash_groups.values() if len(g) > 1]
    print(f"[scanner]   duplicate function groups: {len(duplicate_groups)}", file=sys.stderr)

    # ── orphaned files ──
    print("[scanner] Checking for orphaned files ...", file=sys.stderr)
    all_issues.extend(find_orphaned_files(safe_py))

    # ── stale log files ──
    print("[scanner] Checking stale log/data files ...", file=sys.stderr)
    all_issues.extend(find_stale_files())

    # ── Kotlin ──
    if not args.no_kotlin:
        kt_scope = ROOT / "UI"
        if kt_scope.exists():
            kt_files = iter_kotlin_files(kt_scope)
            print(f"[scanner] Found {len(kt_files)} Kotlin files", file=sys.stderr)
            print("[scanner] Checking Kotlin @Composable usage ...", file=sys.stderr)
            all_issues.extend(find_unused_composables(kt_files))
            for fp in kt_files:
                src = read_source(fp)
                if src:
                    all_issues.extend(find_kt_comment_blocks(fp, src))

    # ── report ──
    report = build_report(all_issues, duplicate_groups, args)

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.write_text(report, encoding="utf-8")
        print(f"[scanner] Report written to {out_path}", file=sys.stderr)
    else:
        print(report)

    # exit code: number of 🔴 issues
    red_count = sum(1 for i in all_issues if TIER_ORDER.get(i["kind"], ("",))[0] == "🔴")
    sys.exit(min(red_count, 127))


if __name__ == "__main__":
    main()
