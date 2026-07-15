#!/usr/bin/env python3
"""
Scrape Polestar 2 software-update release notes from the official owner's manual
and regenerate index.html.

Data source: the manual page server-renders a Remix context blob that contains a
`releaseNotes.content.body` structure. We fetch the HTML, isolate that object by
balanced-brace scanning, walk it into a flat list of {version, notes[]}, and
splice the result into index.html's embedded DATA array.

No browser / heavy deps required — just urllib from the stdlib.
"""
import json, re, sys, urllib.request, pathlib, html as _html, datetime

MANUAL_URL = "https://www.polestar.com/uk/manual/polestar-2/2027/software-updates/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

SITE_URL = "https://alexmicky19.github.io/polestar2-updates/"
FEED_URL = SITE_URL + "feed.xml"

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
DATA = ROOT / "data.json"
FEED = ROOT / "feed.xml"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def extract_release_notes_object(page: str) -> dict:
    """Find `"releaseNotes":{...}` and return it as a parsed dict via balanced braces."""
    key = '"releaseNotes":'
    i = page.find(key)
    if i == -1:
        raise SystemExit("could not find releaseNotes in page")
    j = page.find("{", i)
    # The blob lives inside the Remix context which is itself a JSON string, so the
    # HTML we downloaded has it JSON-escaped once (\" and \\n). Scan on the raw text
    # counting braces while respecting escaped quotes.
    depth, k, in_str, esc = 0, j, False, False
    while k < len(page):
        c = page[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    raw = page[j:k + 1]
                    return decode_escaped_json(raw)
        k += 1
    raise SystemExit("unbalanced braces scanning releaseNotes")


def decode_escaped_json(raw: str) -> dict:
    """The object text is escaped as it appeared inside a JSON string. Unescape then parse."""
    # First try parsing directly (in case it's already clean).
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Otherwise it's escaped: wrap in quotes and let json decode the escapes, then parse.
    unescaped = json.loads('"' + raw + '"')
    return json.loads(unescaped)


def walk_notes(children) -> list:
    """Flatten a segment's children into a list of note strings.
    Sub-segment titles are prefixed with '### ' (the UI renders them as sub-headings)."""
    notes = []

    def rec(node, sub=False):
        if isinstance(node, list):
            for n in node:
                rec(n, sub)
            return
        if not isinstance(node, dict):
            if isinstance(node, str) and node.strip():
                notes.append(node.strip())
            return
        t = node.get("type")
        ch = node.get("children")
        if t == "title":
            # sub-segment / note title -> heading; top segment title handled by caller
            if sub and isinstance(ch, str):
                notes.append("### " + ch.strip())
        elif t == "paragraph":
            if isinstance(ch, str) and ch.strip():
                notes.append(ch.strip())
            else:
                rec(ch, sub)
        elif t == "subSegment":
            rec(ch, True)
        elif t in ("unorderedList", "orderedList"):
            rec(ch, sub)
        elif t == "listItem":
            if isinstance(ch, str) and ch.strip():
                notes.append(ch.strip())
            else:
                rec(ch, sub)
        elif t == "note":
            rec(ch, True)
        else:
            if ch is not None:
                rec(ch, sub)

    rec(children)
    return notes


def parse_versions(rn: dict) -> list:
    body = rn.get("content", {}).get("body", [])
    versions = []
    for seg in body:
        children = seg.get("children")
        # A version segment starts with a title "Updates in software version PX.Y.Z"
        title = None
        if isinstance(children, list):
            for n in children:
                if isinstance(n, dict) and n.get("type") == "title" and isinstance(n.get("children"), str):
                    title = n["children"]
                    break
        if not title or "software version" not in title.lower():
            continue
        ver = re.sub(r"^Updates in software version\s*", "", title).strip()
        # notes = everything except the top-level title
        rest = [n for n in children if not (isinstance(n, dict) and n.get("type") == "title" and n.get("children") == title)]
        notes = walk_notes(rest)
        versions.append({"version": ver, "notes": notes})
    return versions


def version_key(v: str):
    """Sort key: strip leading P, compare numerically (newest first when reversed)."""
    parts = re.sub(r"^P", "", v, flags=re.I).split(".")
    return [int(p) if p.isdigit() else 0 for p in parts]


def load_first_seen() -> dict:
    """Read the previously persisted first-seen dates so pubDates stay stable."""
    if not DATA.exists():
        return {}
    try:
        prev = json.loads(DATA.read_text(encoding="utf-8"))
        return {v["version"]: v["first_seen"] for v in prev if v.get("first_seen")}
    except Exception:
        return {}


def rss_date(iso: str) -> str:
    """YYYY-MM-DD -> RFC 822 date (RSS pubDate), at 00:00:00 GMT."""
    d = datetime.date.fromisoformat(iso)
    dt = datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_feed(versions: list) -> str:
    """One <item> per version, newest first, pubDate = first_seen date."""
    def esc(s):
        return _html.escape(s, quote=True)

    items = []
    for v in versions:
        bullets = [n for n in v["notes"] if not n.startswith("### ")]
        # readable plain-text description
        desc = "\n".join(("• " + n) if not n.startswith("### ") else ("\n" + n[4:] + ":")
                         for n in v["notes"]).strip()
        link = SITE_URL + "#" + esc(v["version"].replace(".", "-"))
        items.append(
            "    <item>\n"
            f"      <title>Polestar 2 software {esc(v['version'])}</title>\n"
            f"      <link>{link}</link>\n"
            f"      <guid isPermaLink=\"false\">polestar2-{esc(v['version'])}</guid>\n"
            f"      <pubDate>{rss_date(v['first_seen'])}</pubDate>\n"
            f"      <description>{esc(desc)}</description>\n"
            "    </item>"
        )
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>Polestar 2 Software Updates (Unofficial)</title>\n"
        f"    <link>{SITE_URL}</link>\n"
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>\n'
        "    <description>New Polestar 2 software versions and their release notes, "
        "sourced from Polestar's owner's manual. Unofficial.</description>\n"
        "    <language>en-GB</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n"
        "</rss>\n"
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--local":
        page = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace")
    else:
        page = fetch(MANUAL_URL)
    rn = extract_release_notes_object(page)
    versions = parse_versions(rn)
    if not versions:
        raise SystemExit("parsed zero versions — aborting so we don't wipe good data")

    # Sort newest-first and attach a stable first-seen date per version.
    versions.sort(key=lambda v: version_key(v["version"]), reverse=True)
    seen = load_first_seen()
    today = datetime.date.today().isoformat()
    for v in versions:
        v["first_seen"] = seen.get(v["version"], today)

    out_json = json.dumps(versions, ensure_ascii=False)
    DATA.write_text(json.dumps(versions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    FEED.write_text(build_feed(versions), encoding="utf-8")

    index = INDEX.read_text(encoding="utf-8")
    new_index, n = re.subn(r"const DATA = .*?;\n", "const DATA = " + out_json + ";\n", index, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("could not locate 'const DATA = ...;' in index.html")
    # bump the captured date shown in the footer/script
    new_index = re.sub(r'const SCRAPED = "[^"]*";', f'const SCRAPED = "{today}";', new_index)
    new_index = re.sub(r'Data captured [0-9]{4}-[0-9]{2}-[0-9]{2}', f'Data captured {today}', new_index)

    changed = new_index != index
    if changed:
        INDEX.write_text(new_index, encoding="utf-8")
    verb = "updated" if changed else "no index change"
    print(f"{verb} — {len(versions)} versions, latest {versions[0]['version']}; wrote data.json + feed.xml")


if __name__ == "__main__":
    main()
