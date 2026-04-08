"""
wiki_lint.py — AURA Wiki Health Check

Implements the Lint operation from the Wiki Brain protocol (CLAUDE.md).

Checks:
  1. ORPHAN  — source_files listed in frontmatter no longer exist on disk
  2. STALE   — source file was modified after the page's last_verified date
  3. UNLISTED — wiki .md files not referenced in index.md
  4. MISSING_FRONTMATTER — wiki pages missing required frontmatter fields

Usage:
    python scripts/wiki_lint.py
    python scripts/wiki_lint.py --fix-dates   # bump last_verified to today for STALE pages (after you've reviewed)

Exit codes:
    0 — PASS (no issues)
    1 — issues found (STALE / ORPHAN / UNLISTED / MISSING_FRONTMATTER)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # graceful degradation — we parse frontmatter manually

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
WIKI_ROOT = REPO_ROOT / "aura brain vault" / "Aura brain" / "wiki"
INDEX_PATH = WIKI_ROOT / "index.md"

# Pages that legitimately have no source_files (meta pages)
META_PAGES = {"index.md", "log.md", "decisions.md", "backlog.md"}

# ---------------------------------------------------------------------------
# Frontmatter parsing (no external deps required)
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> dict | None:
    """
    Parse YAML frontmatter from a markdown file.
    Returns None if no frontmatter block found.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    end = text.find("\n---", 3)
    if end == -1:
        return None

    fm_text = text[3:end].strip()

    if yaml is not None:
        try:
            return yaml.safe_load(fm_text)
        except Exception:
            return {}

    # Manual parse for basic key: value and key: [list] forms
    result: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Handle inline YAML list: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
            result[key] = items
        else:
            result[key] = val.strip("'\"")
    return result


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_modified_after(repo: Path, since: str, rel_path: str) -> bool:
    """
    Returns True if rel_path was modified in git after the given date (YYYY-MM-DD).
    Falls back to filesystem mtime if git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--name-only", "--format=", "--", rel_path],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        # If there's any output, the file was modified after the date
        return bool(result.stdout.strip())
    except Exception:
        # Fallback: compare filesystem mtime to last_verified date
        full_path = repo / rel_path
        if not full_path.exists():
            return False
        mtime = datetime.fromtimestamp(full_path.stat().st_mtime).date()
        try:
            verified_date = date.fromisoformat(since)
            return mtime > verified_date
        except ValueError:
            return False


# ---------------------------------------------------------------------------
# Main lint logic
# ---------------------------------------------------------------------------

def lint_wiki(fix_dates: bool = False) -> int:
    """
    Run the full wiki lint. Returns exit code (0 = pass, 1 = issues found).
    """
    issues: list[str] = []
    stale_paths: list[Path] = []

    all_wiki_pages = list(WIKI_ROOT.rglob("*.md"))

    # -----------------------------------------------------------------------
    # Check 1: MISSING_FRONTMATTER + ORPHAN + STALE
    # -----------------------------------------------------------------------
    for page in sorted(all_wiki_pages):
        rel_page = page.relative_to(WIKI_ROOT)
        page_name = page.name

        # Skip log.md — append-only, never needs source verification
        if page_name == "log.md":
            continue

        fm = _parse_frontmatter(page)

        if fm is None:
            issues.append(f"  MISSING_FRONTMATTER  {rel_page}")
            continue

        missing_fields = [f for f in ("last_verified", "source_files", "status") if f not in fm]
        if missing_fields:
            issues.append(f"  MISSING_FRONTMATTER  {rel_page}  (missing: {', '.join(missing_fields)})")
            continue

        source_files: list[str] = fm.get("source_files") or []
        last_verified: str = str(fm.get("last_verified", ""))

        # Skip staleness checks for meta pages with no source_files
        if not source_files:
            if page_name not in META_PAGES:
                issues.append(f"  WARN  {rel_page}  (source_files is empty but page is not a meta page)")
            continue

        for src in source_files:
            src_path = REPO_ROOT / src
            # ORPHAN check
            if not src_path.exists() and not src_path.is_dir():
                issues.append(f"  ORPHAN  {rel_page}  →  {src}  (file not found on disk)")
                continue

            # STALE check
            if last_verified:
                if _git_modified_after(REPO_ROOT, last_verified, src):
                    issues.append(f"  STALE   {rel_page}  →  {src}  (modified after {last_verified})")
                    stale_paths.append(page)

    # -----------------------------------------------------------------------
    # Check 2: UNLISTED — pages not referenced in index.md
    # -----------------------------------------------------------------------
    if INDEX_PATH.exists():
        index_text = INDEX_PATH.read_text(encoding="utf-8")
        for page in sorted(all_wiki_pages):
            if page == INDEX_PATH:
                continue
            rel_page = page.relative_to(WIKI_ROOT)
            # Check if any part of the path appears in index
            page_ref = str(rel_page).replace("\\", "/")
            if page_ref not in index_text and page.stem not in index_text:
                issues.append(f"  UNLISTED  {rel_page}  (not referenced in index.md)")
    else:
        issues.append("  ERROR  index.md not found")

    # -----------------------------------------------------------------------
    # Optional: bump last_verified for stale pages
    # -----------------------------------------------------------------------
    if fix_dates and stale_paths:
        today = date.today().isoformat()
        fixed: list[str] = []
        for page in set(stale_paths):
            text = page.read_text(encoding="utf-8")
            if "last_verified:" in text:
                import re
                new_text = re.sub(
                    r"last_verified:\s*\S+",
                    f"last_verified: {today}",
                    text,
                    count=1,
                )
                page.write_text(new_text, encoding="utf-8")
                fixed.append(str(page.relative_to(WIKI_ROOT)))
        if fixed:
            print(f"[wiki-lint] --fix-dates: bumped last_verified to {today} for:")
            for f in fixed:
                print(f"    {f}")
            print()

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    if issues:
        print(f"[wiki-lint] FAIL — {len(issues)} issue(s) found:\n")
        for issue in issues:
            print(issue)
        print()
        print("Run `python scripts/wiki_lint.py --fix-dates` after reviewing STALE pages.")
        return 1
    else:
        total = len(all_wiki_pages)
        print(f"[wiki-lint] PASS — {total} pages checked, no issues found.")
        return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AURA wiki health check")
    parser.add_argument(
        "--fix-dates",
        action="store_true",
        help="Bump last_verified to today for STALE pages (use after manual review)",
    )
    args = parser.parse_args()
    sys.exit(lint_wiki(fix_dates=args.fix_dates))
