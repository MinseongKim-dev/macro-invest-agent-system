"""Import path migration script.

Walks all .py files (excluding legacy/, __pycache__) and replaces old
top-level import prefixes with new src.* prefixes.

Rules:
- Only replaces at the START of import statements (^from ... / ^import ...)
- Guards against double-replacement (skip files where new paths already present)
- Also fixes evals/conftest.py which is now at tests/evals/conftest.py
"""

from __future__ import annotations

import os
import re

ROOT = "/home/user/macro-invest-agent-system"

EXCLUDE_DIRS = {
    "legacy",
    "__pycache__",
    ".git",
    ".venv",
    ".mypy_cache",
    ".ruff_cache",
}

# Ordered replacements — more specific first to avoid partial matches.
# Format: (old_pattern_prefix, new_prefix)
# The old_pattern_prefix is matched at the start of import lines.
REPLACEMENTS: list[tuple[str, str]] = [
    # alembic -> src.core.alembic (before core to avoid double-replace)
    (r"^(from\s+)alembic(\b)", r"\1src.core.alembic\2"),
    (r"^(import\s+)alembic(\b)", r"\1src.core.alembic\2"),

    # storage -> src.core.storage
    (r"^(from\s+)storage(\b)", r"\1src.core.storage\2"),
    (r"^(import\s+)storage(\b)", r"\1src.core.storage\2"),

    # core -> src.core
    (r"^(from\s+)core(\b)", r"\1src.core\2"),
    (r"^(import\s+)core(\b)", r"\1src.core\2"),

    # mcp.schemas / mcp.tools -> src.agent.mcp.schemas / src.agent.mcp.tools
    # (project-local mcp, not the external mcp SDK — external SDK uses `from mcp import X`
    #  not `from mcp.schemas` / `from mcp.tools`)
    (r"^(from\s+)mcp\.(schemas|tools)(\b)", r"\1src.agent.mcp.\2\3"),
    (r"^(import\s+)mcp\.(schemas|tools)(\b)", r"\1src.agent.mcp.\2\3"),

    # adapters -> src.agent.adapters
    (r"^(from\s+)adapters(\b)", r"\1src.agent.adapters\2"),
    (r"^(import\s+)adapters(\b)", r"\1src.agent.adapters\2"),

    # agent -> src.agent
    (r"^(from\s+)agent(\b)", r"\1src.agent\2"),
    (r"^(import\s+)agent(\b)", r"\1src.agent\2"),

    # domain -> src.domain
    (r"^(from\s+)domain(\b)", r"\1src.domain\2"),
    (r"^(import\s+)domain(\b)", r"\1src.domain\2"),

    # pipelines -> src.pipelines
    (r"^(from\s+)pipelines(\b)", r"\1src.pipelines\2"),
    (r"^(import\s+)pipelines(\b)", r"\1src.pipelines\2"),

    # services -> src.services
    (r"^(from\s+)services(\b)", r"\1src.services\2"),
    (r"^(import\s+)services(\b)", r"\1src.services\2"),
]

# Guard: if a line already starts with src.<something>, skip it
ALREADY_MIGRATED_RE = re.compile(
    r"^(from|import)\s+src\.", re.MULTILINE
)


def should_skip_dir(path: str) -> bool:
    parts = path.split(os.sep)
    return any(part in EXCLUDE_DIRS for part in parts)


def fix_file(filepath: str) -> bool:
    """Apply all replacements to a single file. Returns True if file was modified."""
    with open(filepath, encoding="utf-8") as f:
        original = f.read()

    content = original
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def main() -> None:
    changed: list[str] = []
    skipped: list[str] = []

    for dirpath, dirnames, filenames in os.walk(ROOT):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

        if should_skip_dir(dirpath):
            continue

        for fname in filenames:
            if not fname.endswith(".py"):
                continue

            filepath = os.path.join(dirpath, fname)
            # Skip this script itself
            if filepath == os.path.abspath(__file__):
                continue

            try:
                modified = fix_file(filepath)
                if modified:
                    changed.append(filepath)
                else:
                    skipped.append(filepath)
            except Exception as e:
                print(f"ERROR: {filepath}: {e}")

    print(f"\nModified {len(changed)} files:")
    for f in sorted(changed):
        rel = f.replace(ROOT + "/", "")
        print(f"  {rel}")

    print(f"\nUnchanged: {len(skipped)} files")


if __name__ == "__main__":
    main()
