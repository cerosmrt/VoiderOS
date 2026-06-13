"""
Gutenberg downloader — uses Gutendex API.
Downloads plain-text books into ~/void/O/Author/Title.txt
Strips Gutenberg header/footer boilerplate automatically.
Safe to interrupt and resume: skips already-downloaded files.

Run:
  nix-shell -p python3 python3Packages.requests --run "python3 scripts/gutenberg_download.py"
"""

import os
import re
import sys
import time
import json
import requests

OUT_DIR   = os.path.expanduser("~/void/O")
LOG_FILE  = os.path.expanduser("~/void/O/.gutenberg_log.json")
API_START = "https://gutendex.com/books/?mime_type=text%2Fplain"

os.makedirs(OUT_DIR, exist_ok=True)

# ── resume log ──────────────────────────────────────────────────────────────
if os.path.exists(LOG_FILE):
    with open(LOG_FILE) as f:
        log = json.load(f)
else:
    log = {"downloaded": [], "failed": [], "next_url": API_START}

downloaded = set(log["downloaded"])
failed     = set(log["failed"])


def save_log():
    log["downloaded"] = list(downloaded)
    log["failed"]     = list(failed)
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


# ── helpers ─────────────────────────────────────────────────────────────────
def sanitize(name):
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name[:120].strip()


def pick_txt_url(formats):
    for mime in (
        "text/plain; charset=utf-8",
        "text/plain; charset=us-ascii",
        "text/plain",
    ):
        if mime in formats:
            return formats[mime]
    for mime, url in formats.items():
        if "text/plain" in mime:
            return url
    return None


def strip_gutenberg(text):
    """Remove Project Gutenberg header and footer boilerplate."""
    start_re = re.compile(
        r"\*{3}\s*START\s+OF\s+(THE\s+)?PROJECT\s+GUTENBERG[^\n]*\*{3}",
        re.IGNORECASE,
    )
    end_re = re.compile(
        r"\*{3}\s*END\s+OF\s+(THE\s+)?PROJECT\s+GUTENBERG[^\n]*\*{3}",
        re.IGNORECASE,
    )

    m_start = start_re.search(text)
    m_end   = end_re.search(text)

    if m_start:
        text = text[m_start.end():]
    if m_end:
        # search again in the (already trimmed) text
        m_end2 = end_re.search(text)
        if m_end2:
            text = text[: m_end2.start()]

    return text.strip()


# ── progress display ─────────────────────────────────────────────────────────
def status(msg, end="\n"):
    sys.stdout.write("\r" + msg.ljust(78) + end)
    sys.stdout.flush()


# ── download ─────────────────────────────────────────────────────────────────
def download_book(book, total_ok):
    book_id = str(book["id"])
    if book_id in downloaded:
        return "skip"

    url = pick_txt_url(book.get("formats", {}))
    if not url:
        failed.add(book_id)
        return "no_txt"

    authors = book.get("authors", [])
    author  = sanitize(authors[0]["name"]) if authors else "Unknown"
    title   = sanitize(book.get("title", f"book_{book_id}"))
    fname   = f"{author} - {title}.txt" if authors else f"{title}.txt"
    out_path = os.path.join(OUT_DIR, fname)

    if os.path.exists(out_path):
        downloaded.add(book_id)
        return "skip"

    status(f"  ↓ [{total_ok+1}] {fname[:60]}", end="")

    try:
        r = requests.get(url, timeout=(15, 90))
        r.raise_for_status()
        cleaned = strip_gutenberg(r.text)
        with open(out_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(cleaned)
        downloaded.add(book_id)
        return "ok"
    except Exception as e:
        failed.add(book_id)
        return f"err:{e}"


# ── main loop ────────────────────────────────────────────────────────────────
def run():
    url      = log.get("next_url", API_START)
    page     = 0
    total_ok = 0

    print(f"Gutenberg downloader")
    print(f"  Output : {OUT_DIR}")
    print(f"  Already: {len(downloaded)} downloaded, {len(failed)} failed")
    print(f"  Resume : {url[:72]}")
    print()

    while url:
        page += 1
        status(f"Fetching page {page}…", end="")

        try:
            r = requests.get(url, timeout=(15, 90))
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            status(f"API error: {e} — retrying in 15s")
            time.sleep(15)
            continue

        books    = data.get("results", [])
        next_url = data.get("next")
        catalog  = data.get("count", "?")

        for book in books:
            result = download_book(book, total_ok)
            if result == "ok":
                total_ok += 1
                authors = book.get("authors", [])
                author  = authors[0]["name"] if authors else "Unknown"
                title   = book.get("title", "?")
                status(f"  ✓ [{total_ok}] {title[:50]} — {author[:25]}")
            elif result.startswith("err:"):
                title = book.get("title", book["id"])
                status(f"  ✗ {title[:55]}: {result[4:60]}")
            # skip: silent

        log["next_url"] = next_url
        save_log()

        print(
            f"  Page {page} done | {len(downloaded)} downloaded"
            f" | {len(failed)} failed | {catalog} in catalog"
        )

        url = next_url
        time.sleep(1)

    print(f"\nFinished. {total_ok} new books saved to {OUT_DIR}")
    save_log()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nInterrupted — progress saved. Run again to resume.")
        save_log()
