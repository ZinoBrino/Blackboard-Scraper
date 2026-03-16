#!/usr/bin/env python3
"""
Aston VLE Course Scraper
Download your own course content from vle.aston.ac.uk

Usage:
  python scraper.py               — interactive (opens browser login)
  python scraper.py <course_url>  — if you already have BLACKBOARD_COOKIES set

Output: ./output/<course_id>/
  api_content.json        — full raw data
  Monday Chats/
    notes.txt             — description + body text for this section
    week1_slides.pptx     — attachments sit right inside their section
    Week 1/
      notes.txt
      lecture.pdf
  Module Information/
    notes.txt
  ...                     — mirrors the VLE folder structure exactly

SECURITY NOTES:
  • Cookies are never saved to disk (only held in memory for this session)
  • No credentials are collected or transmitted anywhere
  • Only makes requests to vle.aston.ac.uk
  • All downloads go to ./output/ — nothing outside your working directory
  • Open source — read this file to verify what it does
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print()
    print("  Missing dependencies. Install them with:")
    print()
    print("    pip install requests beautifulsoup4")
    print()
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / ".scraper_config.json"
VLE_URL = "https://vle.aston.ac.uk"
VERSION = "1.2.0"

BANNER = f"""
╔══════════════════════════════════════════════════════════════╗
║  Aston VLE Course Scraper  v{VERSION}                          ║
║  Download your own course content                            ║
║                                                              ║
║  This tool ONLY downloads content you already have access   ║
║  to. It never stores passwords or sends data anywhere       ║
║  other than vle.aston.ac.uk.                                ║
╚══════════════════════════════════════════════════════════════╝
"""


# ─── Colours (degrade gracefully if terminal doesn't support them) ────────────

def _supports_colour() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


if _supports_colour():
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
else:
    GREEN = YELLOW = RED = CYAN = DIM = BOLD = RESET = ""

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET}  {msg}")
def err(msg: str)  -> None: print(f"  {RED}✗{RESET}  {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}!{RESET}  {msg}")
def info(msg: str) -> None: print(f"  {CYAN}→{RESET}  {msg}")
def dim(msg: str)  -> None: print(f"  {DIM}{msg}{RESET}")
def step(n: int, title: str) -> None:
    print()
    print(f"  {BOLD}Step {n}{RESET}  {title}")
    print(f"  {'─' * (len(title) + 8)}")


# ─── Config (only saves last course ID — never credentials) ──────────────────

def load_config() -> dict:
    """Load non-sensitive config (last course ID only)."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Extra safety: strip anything that looks like credentials
            return {k: v for k, v in data.items() if "cookie" not in k.lower()
                                                    and "password" not in k.lower()
                                                    and "token" not in k.lower()}
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    """Save only the course ID hint — never cookies."""
    safe = {"last_course_id": cfg.get("last_course_id", "")}
    try:
        CONFIG_FILE.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    except Exception:
        pass  # Config saving is optional convenience


# ─── Session / network ────────────────────────────────────────────────────────

def parse_cookies(s: str) -> dict:
    cookies = {}
    for part in s.replace(" ", "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def make_session(base_url: str, cookies_str: str) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"{base_url}/",
    })
    sess.cookies.update(parse_cookies(cookies_str))
    return sess


def verify_login(base_url: str, cookies_str: str) -> bool:
    """Check cookies give valid API access (calls /users/me — read-only)."""
    sess = make_session(base_url, cookies_str)
    try:
        r = sess.get(
            f"{base_url}/learn/api/public/v1/users/me",
            headers={"Accept": "application/json"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception:
        return False


def extract_course_id(s: str) -> str | None:
    """Extract course ID from URL or raw ID. E.g. _62382_1"""
    m = re.search(r"/courses/(_[^/?#]+)", s)
    if m:
        return m.group(1)
    if re.match(r"_\d+_\d+", s.strip()):
        return s.strip()
    return None


# ─── Interactive wizard ───────────────────────────────────────────────────────

def run_wizard() -> tuple[str, str, str]:
    """Interactive setup. Returns (base_url, cookies_str, course_id).
    Cookies are NEVER written to disk.

    The browser stays open through both steps so the user can copy the
    course URL from the same window they logged in with — no second login.
    """
    cfg = load_config()
    last_course = cfg.get("last_course_id", "")
    cookies_str = os.environ.get("BLACKBOARD_COOKIES", "")

    print(BANNER)

    # ── Steps 1 + 2 via browser (keep it open across both) ─────────────────
    if not cookies_str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print()
            err("Playwright not installed. Run:")
            print()
            print("    pip install playwright")
            print("    playwright install chromium")
            print()
            sys.exit(1)

        step(1, "Log in to Aston VLE")
        print()
        print("  A browser window will open. Log in as you normally would.")
        print()
        dim("  Your password goes directly into Aston's own login page")
        dim("  — this script never sees it.")
        print()
        input("  Press Enter to open the browser... ")
        print()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(VLE_URL)

            # ── Step 1: wait for login ────────────────────────────────────
            while True:
                input("  When you can see your course list, press Enter here... ")
                cookies = context.cookies() or context.cookies(VLE_URL)
                if not cookies:
                    print()
                    warn("No cookies captured — did you finish logging in?")
                    retry = input("  Try again? [Y/n]: ").strip().lower()
                    if retry == "n":
                        browser.close()
                        print()
                        print("  Manual alternative: DevTools (F12) → Application → Cookies")
                        print(f"  Copy as  name=value; name=value  then run:")
                        print()
                        print(f"    {DIM}BLACKBOARD_COOKIES='...' python scraper.py{RESET}")
                        print()
                        sys.exit(1)
                    continue

                candidate = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                info("Verifying login...")
                if verify_login(VLE_URL, candidate):
                    cookies_str = candidate
                    ok("Logged in")
                    break
                else:
                    print()
                    err("Login check failed — not fully logged in yet.")
                    warn("Complete any 2FA prompts before pressing Enter.")
                    retry = input("  Try again? [Y/n]: ").strip().lower()
                    if retry == "n":
                        browser.close()
                        sys.exit(1)

            # ── Step 2: get course URL while browser is still open ────────
            step(2, "Which course?")
            print()
            print("  Navigate to your course in the browser that's still open.")
            print("  Then copy the URL from the address bar and paste it here.")
            print()
            hint = f" {DIM}[last: {last_course}]{RESET}" if last_course else ""
            print(f"  Course URL or ID{hint}: ", end="", flush=True)
            course_in = input().strip() or last_course

            # Try to grab the current page URL as a fallback hint
            if not course_in:
                try:
                    current_url = page.url
                    if extract_course_id(current_url):
                        print()
                        print(f"  {DIM}(using current browser URL){RESET}")
                        course_in = current_url
                except Exception:
                    pass

            browser.close()

    else:
        # ── Non-browser path (BLACKBOARD_COOKIES in env) ──────────────────
        step(1, "Log in to Aston VLE")
        print()
        info("Using BLACKBOARD_COOKIES from environment variable")

        if not verify_login(VLE_URL, cookies_str):
            print()
            err("Login check failed — cookies appear invalid or expired.")
            sys.exit(1)

        ok("Session verified")

        step(2, "Which course?")
        print()
        print("  Paste a course URL or ID (_12345_1).")
        print()
        hint = f" {DIM}[last: {last_course}]{RESET}" if last_course else ""
        print(f"  Course URL or ID{hint}: ", end="", flush=True)
        course_in = input().strip() or last_course

    # ── Validate course ID ────────────────────────────────────────────────
    if not course_in:
        err("No course provided.")
        sys.exit(1)

    course_id = extract_course_id(course_in)
    if not course_id:
        err("Couldn't find a course ID in that input.")
        warn("Paste the full course URL or just the _XXXXX_1 part.")
        sys.exit(1)

    ok(f"Course ID: {BOLD}{course_id}{RESET}")

    cfg["last_course_id"] = course_id
    save_config(cfg)

    print()
    return VLE_URL, cookies_str, course_id


# ─── API helpers ──────────────────────────────────────────────────────────────

def api_get(sess: requests.Session, base_url: str, path: str) -> dict | list | None:
    api_base = f"{base_url}/learn/api/public/v1"
    url = path if path.startswith("http") else f"{api_base}{path}"
    try:
        r = sess.get(url, headers={"Accept": "application/json"}, timeout=30)
    except requests.exceptions.ConnectionError:
        warn("Network error — check your connection")
        return None
    if r.status_code == 204:
        return None
    r.raise_for_status()
    return r.json()


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:120].strip()
    return cleaned or "unnamed"


def extract_file_refs_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    refs = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "bbcswebdav" in href or "xid-" in href:
            name = a.get_text(strip=True) or a.get("data-bbfile") or "attachment"
            refs.append({"name": name, "url": href})
    return refs


# ─── Content tree ─────────────────────────────────────────────────────────────

def fetch_content_tree(
    sess: requests.Session,
    base_url: str,
    course_id: str,
    parent_id: str | None = None,
    path: list | None = None,
    depth: int = 0,
) -> list:
    path = path or []
    endpoint = (
        f"/courses/{course_id}/contents/{parent_id}/children"
        if parent_id
        else f"/courses/{course_id}/contents"
    )
    try:
        data = api_get(sess, base_url, endpoint)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code == 401:
            print()
            err("Session expired mid-download. Run again and log in.")
            sys.exit(1)
        if code == 403:
            warn(f"Access denied to {endpoint} — skipping")
            return []
        warn(f"HTTP {code} on {endpoint}")
        return []

    if not data:
        return []
    items = data.get("results", []) if isinstance(data, dict) else []
    result = []

    for item in items:
        item_path = path + [item.get("title") or item.get("id", "")]
        handler = item.get("contentHandler") or {}
        handler_id = handler.get("id", "unknown")
        links = item.get("links") or []
        ui_href = next((l.get("href") for l in links if l.get("rel") == "alternate"), None)

        entry = {
            "id": item.get("id"),
            "title": item.get("title"),
            "type": handler_id,
            "path": " > ".join(item_path),
            "description": item.get("description") or "",
            "body": item.get("body"),
            "file_refs": extract_file_refs_from_html(item.get("body") or ""),
            "external_url": handler.get("url") if handler_id == "resource/x-bb-externallink" else None,
            "links": links,
            "ui_url": urljoin(base_url, ui_href) if ui_href else None,
            "children": [],
        }

        if item.get("body"):
            div = BeautifulSoup(item["body"], "html.parser")
            entry["body_text"] = (div.get_text(separator="\n", strip=True) or "").strip()

        if handler_id == "resource/x-bb-file":
            fname = handler.get("file", {}).get("fileName") or item.get("title")
            entry["file_refs"] = [{"name": fname, "url": None}]
            try:
                detail = api_get(sess, base_url, f"/courses/{course_id}/contents/{item['id']}")
                if detail and detail.get("body"):
                    entry["file_refs"] = extract_file_refs_from_html(detail["body"])
                # Fallback: resource/x-bb-file items (e.g. .zip) often have no body;
                # use Ultra redirect URL - it redirects to the actual file download
                if not entry["file_refs"][0].get("url") and entry.get("ui_url"):
                    entry["file_refs"] = [{"name": fname, "url": entry["ui_url"]}]
            except Exception:
                if entry.get("ui_url"):
                    entry["file_refs"] = [{"name": fname, "url": entry["ui_url"]}]

        if (handler_id == "resource/x-bb-document" or "document" in (handler_id or "")) \
                and not entry.get("body"):
            try:
                detail = api_get(sess, base_url, f"/courses/{course_id}/contents/{item['id']}")
                if detail:
                    entry["body"] = detail.get("body")
                    entry["file_refs"] = extract_file_refs_from_html(detail.get("body") or "")
                    div = BeautifulSoup(entry["body"] or "", "html.parser")
                    entry["body_text"] = (div.get_text(separator="\n", strip=True) or "").strip()
            except Exception:
                pass

        if item.get("hasChildren") or handler_id == "resource/x-bb-folder":
            # Guard against runaway recursion (VLE shouldn't nest > 10 deep)
            if depth < 10:
                entry["children"] = fetch_content_tree(
                    sess, base_url, course_id, item.get("id"), item_path, depth + 1
                )

        result.append(entry)

    return result


# ─── Hierarchical output ─────────────────────────────────────────────────────
#
# Output mirrors the VLE folder structure:
#
#   output/<course_id>/
#     Monday Chats/
#       notes.txt          ← description + body text for this section
#       lecture1.pdf       ← attachments sit right here
#       Week 1/
#         notes.txt
#         slides.pptx
#     Module Information/
#       notes.txt
#     api_content.json     ← full raw data at root
#

def _download_file(sess: requests.Session, url: str, name: str, dest_dir: Path, counts: dict) -> None:
    """Download a single file into dest_dir."""
    if not url.startswith(VLE_URL) and "bbcswebdav" not in url:
        warn(f"  Skipping off-domain URL: {url[:80]}")
        return

    try:
        r = sess.get(url, stream=True, timeout=60)
        r.raise_for_status()

        # Prefer server-suggested filename
        cd = r.headers.get("Content-Disposition", "")
        if cd:
            m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd, re.I)
            if m:
                name = sanitize_filename(m.group(1).strip())

        out_path = dest_dir / name
        if out_path.exists():
            stem = Path(name).stem
            suffix = Path(name).suffix or ".bin"
            out_path = dest_dir / f"{stem}_{abs(hash(url)) % 10000:04d}{suffix}"

        with open(out_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

        size = out_path.stat().st_size
        size_str = f"{size // 1024} KB" if size > 1024 else f"{size} B"
        dim(f"        ↳ {out_path.relative_to(out_path.parents[2])}  ({size_str})")
        counts["files"] += 1

    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code != 404:
            warn(f"  HTTP {code} for {name}")
        counts["file_err"] += 1
    except Exception as e:
        warn(f"  Error downloading {name}: {e}")
        counts["file_err"] += 1


def _write_notes(item: dict, folder: Path) -> None:
    """Write a notes.txt for this item if it has any text content."""
    parts = []

    title = item.get("title", "").strip()
    if title:
        parts.append(f"# {title}")
        parts.append("")

    desc = item.get("description", "").strip()
    if desc:
        parts.append(desc)
        parts.append("")

    body = item.get("body_text", "").strip()
    if not body and item.get("body"):
        soup = BeautifulSoup(item["body"], "html.parser")
        body = soup.get_text(separator="\n", strip=True).strip()
    if body:
        parts.append(body)
        parts.append("")

    ext_url = item.get("external_url")
    if ext_url:
        parts.append(f"Link: {ext_url}")
        parts.append("")

    if len(parts) > 2:  # more than just the title
        (folder / "notes.txt").write_text("\n".join(parts), encoding="utf-8")


def save_tree(
    sess: requests.Session,
    items: list,
    parent_dir: Path,
    counts: dict,
    depth: int = 0,
) -> None:
    """Recursively write the content tree into a matching folder hierarchy."""
    for item in items:
        title = item.get("title") or item.get("id") or "untitled"
        safe_title = sanitize_filename(title)
        handler_id = item.get("type", "")
        children = item.get("children", [])
        file_refs = item.get("file_refs", [])

        is_folder = bool(children) or handler_id in (
            "resource/x-bb-folder",
            "resource/x-bb-coursetoc",
        )

        if is_folder:
            # Sections become subfolders
            folder = parent_dir / safe_title
            folder.mkdir(parents=True, exist_ok=True)
            _write_notes(item, folder)
            if file_refs:
                for ref in file_refs:
                    if ref.get("url"):
                        _download_file(sess, ref["url"], sanitize_filename(ref.get("name", "file")), folder, counts)
            save_tree(sess, children, folder, counts, depth + 1)
        else:
            # Leaf items: write notes + download any attachments into parent
            _write_notes(item, parent_dir)
            for ref in file_refs:
                if ref.get("url"):
                    _download_file(sess, ref["url"], sanitize_filename(ref.get("name", "file")), parent_dir, counts)


# ─── Progress display ─────────────────────────────────────────────────────────

class Progress:
    """Simple inline progress counter that doesn't leave junk in the terminal."""

    def __init__(self, label: str):
        self.label = label
        self.n = 0
        self._last_len = 0

    def tick(self, detail: str = "") -> None:
        self.n += 1
        msg = f"  {CYAN}→{RESET}  {self.label}  {DIM}{self.n}{RESET}"
        if detail:
            msg += f"  {DIM}{detail[:50]}{RESET}"
        # Overwrite previous line
        spaces = " " * max(0, self._last_len - len(msg))
        print(f"\r{msg}{spaces}", end="", flush=True)
        self._last_len = len(msg)

    def done(self, summary: str = "") -> None:
        print(f"\r{' ' * (self._last_len + 4)}\r", end="")
        ok(f"{self.label}  {summary}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    raw = sys.argv[1:]
    flags = {a for a in raw if a.startswith("--")}
    args  = [a for a in raw if not a.startswith("--")]

    dry_run = "--dry-run" in flags

    # Non-interactive mode: course ID as arg, cookies from env
    if args and "--wizard" not in flags:
        course_in = args[0]
        course_id = extract_course_id(course_in)
        if not course_id:
            err("Invalid course. Use a full URL or the _XXXXX_1 ID.")
            sys.exit(1)
        cookies_str = os.environ.get("BLACKBOARD_COOKIES", "")
        if not cookies_str:
            err("Set the BLACKBOARD_COOKIES environment variable, or run without arguments.")
            sys.exit(1)
        base_url = VLE_URL
    else:
        base_url, cookies_str, course_id = run_wizard()

    if not verify_login(base_url, cookies_str):
        print()
        err("Login verification failed. Run again and log in properly.")
        sys.exit(1)

    out_dir = Path("output") / course_id
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = make_session(base_url, cookies_str)

    if dry_run:
        print()
        ok(f"Dry run — would download to: {out_dir.absolute()}")
        return

    print()
    print(f"  {BOLD}Downloading course {course_id}{RESET}")
    print(f"  {'─' * 40}")
    t_start = time.time()

    counts = {"files": 0, "file_err": 0}

    # ── Content tree ─────────────────────────────────────────────────────────
    info("Building content tree from API...")
    tree = fetch_content_tree(sess, base_url, course_id)

    with open(out_dir / "api_content.json", "w", encoding="utf-8") as f:
        json.dump({"courseId": course_id, "content": tree}, f, indent=2, ensure_ascii=False)
    ok("Saved api_content.json")

    # ── Hierarchical output ───────────────────────────────────────────────────
    info("Saving content into folders...")
    save_tree(sess, tree, out_dir, counts)
    ok(f"Files: {counts['files']} downloaded" +
       (f", {counts['file_err']} skipped" if counts["file_err"] else ""))

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print()
    print(f"  {'─' * 40}")
    ok(f"Done in {elapsed:.1f}s")
    print()
    print(f"  Saved to: {BOLD}{out_dir.absolute()}{RESET}")
    print()


if __name__ == "__main__":
    main()