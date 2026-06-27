#!/usr/bin/env python3
"""Compile all VoiderOS / proto-voider source code into a single text file.

Walks the repo, gathers every code file (by extension), and writes one big
plain-text compilation to PROTOVOIDER_COMPILED_CODE.txt at the repo root —
so the code can be sent to / read on a phone like any other /void text.

Run it yourself whenever you want a fresh dump:

    nix-shell -p python3 --run "python3 scripts/compile_code.py"

Generated/data files (lockfiles, runtime JSON, build artifacts) are excluded.
"""
import os

# Repo root = parent of this script's directory (scripts/..).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, 'PROTOVOIDER_COMPILED_CODE.txt')

# Code extensions to include.
EXTS = {'.py', '.rs', '.nix', '.json', '.toml', '.cpp'}

# Directory names to skip entirely, anywhere in the tree.
SKIP_DIRS = {'.git', '.claude', '.vscode', 'target', '__pycache__',
             'node_modules', '.direnv', '.pytest_cache', '.mypy_cache',
             'result'}

# Specific filenames to exclude (generated / runtime data).
SKIP_FILES = {'flake.lock', 'Cargo.lock', '_book_order.json',
              'combined_code.py'}

TITLE_BAR = '=' * 70
FILE_BAR = '=' * 40


def collect():
    """Return sorted list of (relpath, line_count, text) for all code files."""
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        # Prune skip dirs in place so we don't descend into them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            ext = os.path.splitext(fn)[1]
            if ext not in EXTS:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, REPO)
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            n = text.count('\n') + (1 if text and not text.endswith('\n') else 0)
            found.append((rel, n, text))
    found.sort(key=lambda t: t[0])
    return found


def build(files):
    total_files = len(files)
    total_lines = sum(n for _, n, _ in files)

    # Per-extension breakdown: (files desc, lines desc).
    by_ext = {}
    for rel, n, _ in files:
        ext = os.path.splitext(rel)[1]
        c, l = by_ext.get(ext, (0, 0))
        by_ext[ext] = (c + 1, l + n)
    breakdown = sorted(by_ext.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))

    out = []
    out.append(TITLE_BAR)
    out.append('PROTOVOIDER / VOIDEROS — COMPLETE SOURCE CODE COMPILATION')
    out.append(TITLE_BAR)
    out.append('')
    out.append(f'Total files: {total_files}')
    out.append(f'Total lines of code: {total_lines}')
    out.append('')
    out.append('FILE TYPE BREAKDOWN:')
    out.append(f'  {"ext":<10} {"files":>6} {"lines":>8}')
    out.append(f'  {"-"*10} {"-"*6} {"-"*8}')
    for ext, (c, l) in breakdown:
        out.append(f'  {ext:<10} {c:>6} {l:>8}')
    out.append('')
    out.append('FILE LIST (path — lines):')
    for rel, n, _ in files:
        out.append(f'{n:>7}  {rel}')
    out.append('')
    out.append('NOTE: Generated/data files excluded — flake.lock, Cargo.lock,')
    out.append('      _book_order.json (runtime data), combined_code.py (old dump),')
    out.append('      and Rust target/ build artifacts.')
    out.append('')
    out.append(TITLE_BAR)
    out.append('')

    for rel, _, text in files:
        out.append(FILE_BAR)
        out.append(f'FILE: {rel}')
        out.append(FILE_BAR)
        out.append(text.rstrip('\n'))
        out.append('')
        out.append('')

    return '\n'.join(out).rstrip('\n') + '\n'


def main():
    files = collect()
    content = build(files)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(content)
    total_lines = sum(n for _, n, _ in files)
    print(f'✓ wrote {OUT}')
    print(f'  {len(files)} files, {total_lines} lines of code')


if __name__ == '__main__':
    main()
