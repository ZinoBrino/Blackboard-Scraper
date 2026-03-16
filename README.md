# Aston VLE Course Scraper

Download all your course content from [vle.aston.ac.uk](https://vle.aston.ac.uk) in one command — slides, documents, ZIPs, everything.

---

## What it does

- Downloads the **complete content tree** of any course you're enrolled in
- Mirrors the VLE folder structure with **notes.txt** (plain text) per section
- Downloads all **file attachments** (PDFs, slides, Word docs, ZIPs, etc.) alongside their sections
- Saves full structured data as **api_content.json**

```
output/<course_id>/
├── api_content.json       ← full raw API data (JSON)
├── Module Information/
│   └── notes.txt
├── Monday Chats/
│   ├── notes.txt
│   └── week1_slides.pptx   ← attachments in their section
├── Ethics/
│   ├── notes.txt
│   └── CS3IP Survey_Questionnaire Documents/
│       ├── notes.txt
│       └── CS3IP Online Survey Documents.zip
└── ...
```

---

## Is it safe to use?

**Yes.** Here's exactly what it does and doesn't do:

| | What happens |
|---|---|
| **Your password** | Entered directly into Aston's own login page — this script never sees it |
| **Your cookies** | Held in memory for the duration of the script, then gone — never written to a file |
| **What it contacts** | Only `vle.aston.ac.uk` |
| **What it writes** | Only to `./output/` in your current directory |
| **What it sends** | Nothing. It only reads content you already have access to |

You can read the source — it's a single Python file with no obfuscation.

---

## Setup

**Requirements:** Python 3.10+

```bash
# Install dependencies
pip install -r requirements.txt

# For the browser login (recommended):
playwright install chromium
```

---

## Usage

### Interactive (recommended for first-time use)

```bash
python scraper.py
```

A browser will open. Log in as you normally would (including 2FA). Once you can see your courses, switch back to the terminal and press Enter. Then paste your course URL or ID.

### With course URL directly

```bash
python scraper.py "https://vle.aston.ac.uk/ultra/courses/_12345_1/outline"
```

(Needs `BLACKBOARD_COOKIES` env var — see manual cookie method below.)

### Flags

```
--dry-run     Show what would happen without downloading anything
--wizard     Force interactive mode even when BLACKBOARD_COOKIES is set
```

---

## Manual cookie method (if the browser approach doesn't work)

1. Log in to the VLE in Chrome/Firefox as normal
2. Open DevTools: **F12** → **Application** tab → **Cookies** → `https://vle.aston.ac.uk`
3. Copy all cookies in `name=value; name=value` format
4. Run:

```bash
BLACKBOARD_COOKIES='cookie1=abc; cookie2=xyz; ...' python scraper.py
```

---

## Common issues

**"No cookies captured"**
Press Enter *after* you've fully logged in and can see your course list, not during the login flow.

**"Login verification failed"**
Your session may have expired. Run the script again and log in fresh.

**"Couldn't find course ID"**
Paste the full URL from your browser, not just the course name. It should contain something like `_62382_1`.

**Files not downloading**
Some files may require an active session cookie that expired. Re-run the script — your course ID is remembered, so you only need to log in again.

---

## Limitations

- Only downloads content you have access to (obviously)
- Blackboard's API doesn't expose everything — some content types (tests, assignments) are read-only or unavailable
- Session cookies typically last a few hours; if a large course takes too long, you may need to re-run

---

## Project structure

```
.
├── scraper.py
├── requirements.txt
├── run                     # Convenience: ./run [args]
├── LICENSE
└── README.md
```

---

*Built for personal academic use. Respects Aston's ToS by only accessing content you're enrolled in.*