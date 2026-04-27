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

# Sentence-case: capitalize only the first letter of the title part (after "XX. " prefix).
# Prepositions/conjunctions stay lowercase even if they are the first content word.
LOWER_WORDS = {"и", "в", "на", "с", "о", "у", "к", "по", "из", "за", "от", "до", "для", "под", "при", "без", "или"}


def to_sentence_case(name: str) -> str:
    """Convert 'XX. Каждое Слово' to 'XX. Каждое слово'.

    Preserves numeric prefixes and file extensions.
    The first content word keeps its capital letter; all subsequent words
    are lowercased. Words that are entirely Latin letters (English terms,
    brand names like "Draw Steel!") are left unchanged.
    """
    # Separate numeric prefix like "01. " or "0801. "
    m = re.match(r'^(\d+\.\s*)', name)
    prefix = m.group(1) if m else ""

    # Separate .md extension
    ext = ""
    base = name
    if name.endswith(".md"):
        ext = ".md"
        base = name[:-3]

    title = base[len(prefix):]
    if not title:
        return name

    # If title starts with Latin characters, leave it entirely unchanged
    if title[0].isascii() and title[0].isalpha():
        return name

    words = title.split()
    result = []
    for i, w in enumerate(words):
        if i == 0:
            # First word keeps its case as-is
            result.append(w)
        elif w.isascii() and any(c.isalpha() for c in w):
            # English words keep their case
            result.append(w)
        else:
            # Lowercase everything after the first word
            result.append(w.lower())

    return prefix + " ".join(result) + ext


def build_file_index(source: Path) -> dict[str, Path]:
    """Map filenames (with and without numeric prefixes) to their relative paths.

    Indexes both original and sentence-cased names so wikilinks resolve
    regardless of casing in the source.
    """
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
        # Index sentence-cased version too
        sc = to_sentence_case(stem)
        if sc != stem:
            index[sc] = rel
        sc_stripped = to_sentence_case(stripped)
        if sc_stripped != stripped and sc_stripped != sc:
            index[sc_stripped] = rel
    return index


def resolve_wikilink(target: str, heading: str | None, display: str | None,
                     current_rel: Path, index: dict[str, Path]) -> str:
    """Convert a wikilink target to a relative Markdown link."""
    if target.endswith('.md'):
        target = target[:-3]

    # Try exact match, then sentence-cased, then without numeric prefix
    rel_path = index.get(target)
    if rel_path is None:
        sc_target = to_sentence_case(target)
        rel_path = index.get(sc_target)
    if rel_path is None:
        stripped = re.sub(r'^\d+\.\s*', '', target)
        rel_path = index.get(stripped)
    if rel_path is None:
        sc_stripped = to_sentence_case(stripped)
        rel_path = index.get(sc_stripped)

    if rel_path is None:
        return display or target

    # Compute relative path from current file to target,
    # but use sentence-cased path segments in the link
    sc_rel_path = to_sentence_case_path(rel_path)
    current_dir = current_rel.parent
    try:
        rel_from_current = sc_rel_path.relative_to(current_dir)
    except ValueError:
        parts_up = len(current_dir.parts)
        prefix = "../" * parts_up
        rel_from_current = Path(prefix + str(sc_rel_path))

    # Keep .md, force forward slashes
    link = str(rel_from_current).replace("\\", "/")
    if heading:
        anchor = heading.lower().replace(" ", "-")
        link += f"#{anchor}"

    text = display or target
    return f"[{text}]({link})"


def process_content(content: str, current_rel: Path, index: dict[str, Path]) -> str:
    """Convert wikilinks in a file's content and add title frontmatter if missing."""
    def replace_match(m: re.Match) -> str:
        target = m.group(1).strip()
        heading = m.group(2).strip() if m.group(2) else None
        display = m.group(3).strip() if m.group(3) else None
        return resolve_wikilink(target, heading, display, current_rel, index)

    content = WIKILINK_RE.sub(replace_match, content)

    # Add title frontmatter if the file doesn't have one.
    # MkDocs replaces dashes with spaces when generating titles from filenames,
    # so we must provide an explicit title to preserve "1-й" etc.
    if not content.startswith('---'):
        # Extract title from filename (without .md and numeric prefix)
        stem = current_rel.stem
        title = re.sub(r'^\d+\.\s*', '', stem)
        frontmatter = f'---\ntitle: {to_sentence_case(title)}\n---\n\n'
        content = frontmatter + content

    return content


def process_pages(content: str) -> str:
    """Apply sentence-case to title values in .pages files."""
    def replace_title(m: re.Match) -> str:
        title = m.group(1)
        return f"title: {to_sentence_case(title)}"
    return re.sub(r'^title:\s*(.+)$', replace_title, content, flags=re.MULTILINE)


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


def to_sentence_case_path(rel: Path) -> Path:
    """Apply sentence-case to each part of a relative path (dirs and filename)."""
    parts = list(rel.parts)
    new_parts = []
    for i, part in enumerate(parts):
        if i == len(parts) - 1 and part.endswith(".md"):
            new_parts.append(to_sentence_case(part))
        elif i == len(parts) - 1:
            new_parts.append(part)
        else:
            new_parts.append(to_sentence_case(part))
    return Path(*new_parts)


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

        # Apply sentence-case to path segments
        sc_rel = to_sentence_case_path(rel)
        dest = output / sc_rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if file_path.is_dir():
            continue

        if file_path.suffix == ".md":
            content = file_path.read_text(encoding="utf-8")
            content = process_content(content, rel, index)
            dest.write_text(content, encoding="utf-8")
            processed += 1
        elif file_path.name == ".pages":
            content = file_path.read_text(encoding="utf-8")
            content = process_pages(content)
            dest.write_text(content, encoding="utf-8")
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

    # Copy root .pages file if it exists
    root_pages = source.parent / ".pages"
    if root_pages.exists():
        content = root_pages.read_text(encoding="utf-8")
        content = process_pages(content)
        (output / ".pages").write_text(content, encoding="utf-8")

    print(f"Processed {processed} markdown files -> {output}")


if __name__ == "__main__":
    main()
