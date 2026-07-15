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
import json, re, sys, urllib.request, pathlib, html as _html

MANUAL_URL = "https://www.polestar.com/uk/manual/polestar-2/2027/software-updates/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"


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


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--local":
        page = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace")
    else:
        page = fetch(MANUAL_URL)
    rn = extract_release_notes_object(page)
    versions = parse_versions(rn)
    if not versions:
        raise SystemExit("parsed zero versions — aborting so we don't wipe good data")

    out_json = json.dumps(versions, ensure_ascii=False)
    # write a sidecar data file for transparency / debugging
    (ROOT / "data.json").write_text(json.dumps(versions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    index = INDEX.read_text(encoding="utf-8")
    new_index, n = re.subn(r"const DATA = .*?;\n", "const DATA = " + out_json + ";\n", index, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("could not locate 'const DATA = ...;' in index.html")
    # bump the captured date shown in the footer/script
    import datetime
    today = datetime.date.today().isoformat()
    new_index = re.sub(r'const SCRAPED = "[^"]*";', f'const SCRAPED = "{today}";', new_index)
    new_index = re.sub(r'Data captured [0-9]{4}-[0-9]{2}-[0-9]{2}', f'Data captured {today}', new_index)

    if new_index != index:
        INDEX.write_text(new_index, encoding="utf-8")
        print(f"updated index.html — {len(versions)} versions, latest {versions[0]['version']}")
    else:
        print(f"no change — {len(versions)} versions, latest {versions[0]['version']}")


if __name__ == "__main__":
    main()
