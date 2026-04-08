# wiki-lint

Run a health check on the AURA wiki brain and report any stale, orphaned, or unlisted pages.

## What this skill does

1. Runs `python scripts/wiki_lint.py` from the repo root
2. Parses the output and presents a structured report
3. For STALE pages, reads the source file and offers to update the wiki page
4. For ORPHAN pages, offers to remove or re-target the wiki page
5. For UNLISTED pages, offers to add the page to index.md

## When to use

- At the start of a session when you suspect the wiki is stale
- After a major refactor that touched many files
- When `git log` shows many files changed since the last wiki update
- When a wiki page's `last_verified` date is more than 2 weeks old

## Steps

```
1. cd to repo root
2. Run: python scripts/wiki_lint.py
3. Parse output — categorize issues into STALE / ORPHAN / UNLISTED / MISSING_FRONTMATTER
4. For each STALE page:
   a. Read the source file(s) listed in source_files frontmatter
   b. Compare to wiki page content
   c. Update wiki page where content has changed
   d. Bump last_verified to today, set status: current
5. For each ORPHAN page:
   a. Check git log to see if the source file was renamed (git log --follow)
   b. If renamed: update source_files to new path
   c. If deleted: update status: orphan and add a note to the wiki page
6. For each UNLISTED page:
   a. Add a line to index.md under the appropriate section
7. For MISSING_FRONTMATTER:
   a. Add the required frontmatter block at the top of the file
8. Append a summary entry to wiki/log.md
9. Run wiki_lint.py again to confirm PASS
```

## Output format

Present results as:

```
Wiki Lint Report — YYYY-MM-DD
==============================
PASS / FAIL

STALE (N pages):
  - agents/coordinator.md  →  agents/coordinator.py  (last verified: YYYY-MM-DD)

ORPHAN (N pages):
  - agents/visual_locator.md  →  agents/visual_locator.py  (file not found)

UNLISTED (N pages):
  - services/web_search.md  (not in index.md)

MISSING_FRONTMATTER (N pages):
  - overview.md
```
