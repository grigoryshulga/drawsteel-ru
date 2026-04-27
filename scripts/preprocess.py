#!/usr/bin/env python3
"""Preprocess Obsidian MD files for MkDocs: convert [[wikilinks]] to relative MD links.

Creates .mkdocs_docs/ with processed files. Originals are never modified.
"""

import re
import shutil
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent.parent / "vault"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / ".mkdocs_docs"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "docs-assets"

SKIP_DIRS = {".git", ".github", ".mkdocs_docs", ".obsidian", "scripts", "docs-assets", "overrides", "site"}
SKIP_FILES = {"mkdocs.yml", "requirements.txt"}
SKIP_DIR_PREFIXES = ("00.",)

WIKILINK_RE = re.compile(r'\[\[([^\]|]+?)(?:#([^\]|]+?))?(?:\|([^\]]+?))?\]\]')


def build_file_index(source: Path) -> dict[str, Path]:
    """Map filenames (with and without numeric prefixes) to their relative paths."""
    index: dict[str, Path] = {}
    for md_file in source.rglob("*.md"):
        rel = md_file.relative_to(source)
        if any(p in SKIP_DIRS for p in rel.parts):
            continue
        if any(p.startswith(".") for p in rel.parts):
            continue
        if any(p.startswith(SKIP_DIR_PREFIXES) for p in rel.parts):
            continue

        stem = md_file.stem
        index[stem] = rel
        # Also index by name without numeric prefix for flexible lookup
        stripped = re.sub(r'^\d+\.\s*', '', stem)
        if stripped != stem:
            index[stripped] = rel
    return index


def resolve_wikilink(target: str, heading: str | None, display: str | None,
                     current_rel: Path, index: dict[str, Path]) -> str:
    """Convert a wikilink target to a relative Markdown link."""
    if target.endswith('.md'):
        target = target[:-3]

    # Try exact match, then without numeric prefix
    rel_path = index.get(target)
    if rel_path is None:
        stripped = re.sub(r'^\d+\.\s*', '', target)
        rel_path = index.get(stripped)

    if rel_path is None:
        return display or target

    # Compute relative path from current file to target
    current_dir = current_rel.parent
    try:
        rel_from_current = rel_path.relative_to(current_dir)
    except ValueError:
        parts_up = len(current_dir.parts)
        prefix = "../" * parts_up
        rel_from_current = Path(prefix + str(rel_path))

    # Keep .md, force forward slashes
    link = str(rel_from_current).replace("\\", "/")
    if heading:
        anchor = heading.lower().replace(" ", "-")
        link += f"#{anchor}"

    text = display or target
    return f"[{text}]({link})"


def process_content(content: str, current_rel: Path, index: dict[str, Path]) -> str:
    """Convert wikilinks in a file's content."""
    def replace_match(m: re.Match) -> str:
        target = m.group(1).strip()
        heading = m.group(2).strip() if m.group(2) else None
        display = m.group(3).strip() if m.group(3) else None
        return resolve_wikilink(target, heading, display, current_rel, index)

    return WIKILINK_RE.sub(replace_match, content)


def should_skip(rel: Path) -> bool:
    if any(p in SKIP_DIRS for p in rel.parts):
        return True
    if any(p.startswith(".") and p != ".pages" for p in rel.parts):
        return True
    if any(p.startswith(SKIP_DIR_PREFIXES) for p in rel.parts):
        return True
    if rel.name in SKIP_FILES:
        return True
    return False


def main() -> None:
    source = SOURCE_DIR
    output = OUTPUT_DIR

    if output.exists():
        shutil.rmtree(output)
    output.mkdir()

    index = build_file_index(source)
    print(f"Indexed {len(index)} file aliases")

    processed = 0
    for file_path in source.rglob("*"):
        rel = file_path.relative_to(source)
        if should_skip(rel):
            continue

        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if file_path.is_dir():
            continue

        if file_path.suffix == ".md":
            content = file_path.read_text(encoding="utf-8")
            content = process_content(content, rel, index)
            dest.write_text(content, encoding="utf-8")
            processed += 1
        else:
            shutil.copy2(file_path, dest)

    # Copy docs-assets (CSS, JS) into output
    if ASSETS_DIR.exists():
        for asset in ASSETS_DIR.rglob("*"):
            if asset.is_file():
                rel = asset.relative_to(ASSETS_DIR)
                dest = output / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, dest)

    print(f"Processed {processed} markdown files -> {output}")


if __name__ == "__main__":
    main()
