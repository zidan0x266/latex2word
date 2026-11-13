"""Collect every cited reference as EndNote XML, in citation order.

Records found in the source EndNote library (matched by DOI, then title) are exported
from it through EndNote; the rest are built from the .bib file.

The source library must be open in EndNote; it is only read (exported through EndNote,
matched read-only via its SQLite file).

usage: python3 build_enxml.py BIB AUX SOURCE_ENL OUT.xml OUT_cites.json [--prefer BIBKEY=RECNUM ...]
  --prefer: when the source library holds duplicates of a reference, the record to use
"""
import html, json, os, re, sqlite3, subprocess, sys, unicodedata

args = sys.argv[1:]
PREFER = {}
while "--prefer" in args:
    i = args.index("--prefer")
    k, v = args[i + 1].split("="); PREFER[k] = int(v)
    del args[i:i + 2]
bib, aux, enl, out_xml, out_json = args[:5]
here = os.path.dirname(os.path.abspath(__file__))


def library_db_id(enl_path):
    """EndNote's session database number for an open library (needed in RecordID specifiers)."""
    name = os.path.basename(enl_path)
    out = subprocess.run(["osascript", "-e", f'tell application "EndNote 21" to retrieve "all" records in document "{name}"'],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r'database="(\d+)"', out)
    if not m:
        sys.exit(f"library {name} is not open in EndNote")
    return m.group(1)

cited = {k: int(v) for k, v in re.findall(r"\\bibcite\{([^}]+)\}\{\{(\d+)\}", open(aux).read())}
order = sorted(cited, key=cited.get)

LATEX_ACCENTS = {"'": "\u0301", '"': "\u0308", "`": "\u0300", "^": "\u0302", "~": "\u0303", "c": "\u0327"}


def delatex(t):
    t = re.sub(r"\{?\\([\'\"`^~c])\s*\{?([A-Za-z])\}?\}?",
               lambda m: unicodedata.normalize("NFC", m.group(2) + LATEX_ACCENTS[m.group(1)]), t)
    t = t.replace("\\&", "&").replace("--", "-").replace("~", " ")
    t = re.sub(r"[{}]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_bib(src):
    entries = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", src):
        start, depth, i = m.end(), 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        body, fields = src[start:i - 1], {}
        for f in re.finditer(r"(\w+)\s*=\s*", body):
            j = f.end()
            if body[j] == "{":
                d, k = 0, j
                while True:
                    d += {"{": 1, "}": -1}.get(body[k], 0)
                    k += 1
                    if d == 0:
                        break
                val = body[j + 1:k - 1]
            else:
                val = re.match(r"[^,\n]*", body[j:]).group(0)
            fields.setdefault(f.group(1).lower(), val.strip().strip('"'))
        entries[m.group(2)] = {"type": m.group(1).lower(), **fields}
    return entries


entries = parse_bib(open(bib, encoding="utf8").read())


def norm(t):
    t = unicodedata.normalize("NFKD", delatex(t).lower())
    return re.sub(r"[^a-z0-9]", "", t.encode("ascii", "ignore").decode())


# While a library is open in EndNote, the .enl file is a stale snapshot; the live database is
# <name>.Data/sdb/sdb.eni. Read that one (read-only).
live = os.path.splitext(enl)[0] + ".Data/sdb/sdb.eni"
con = sqlite3.connect(f"file:{live if os.path.exists(live) else enl}?mode=ro", uri=True)
by_doi, by_title = {}, {}
for rid, doi, title in con.execute("select id, electronic_resource_number, title from refs where trash_state = 0"):
    d = (doi or "").lower().strip().replace("https://doi.org/", "")
    if d:
        by_doi.setdefault(d, []).append(rid)
    if title:
        by_title.setdefault(norm(title), []).append(rid)

source_id, missing = {}, []
for key in order:
    e = entries[key]
    doi = e.get("doi", "").lower().replace("https://doi.org/", "")
    ids = by_doi.get(doi) or by_title.get(norm(e.get("title", ""))) or []
    if key in PREFER and PREFER[key] in ids:
        source_id[key] = PREFER[key]
    elif ids:
        source_id[key] = min(ids)
    else:
        missing.append(key)

# --- export found records through EndNote (source library must be open as database 1)
tmp = out_xml + ".export"
subprocess.run([sys.executable, os.path.join(here, "en_export.py"), library_db_id(enl), tmp] +
               [str(source_id[k]) for k in order if k in source_id], check=True)
exported = {}
for rec in re.findall(r"<record>.*?</record>", open(tmp, encoding="utf8").read(), re.S):
    n = int(re.search(r"<rec-number>(\d+)</rec-number>", rec).group(1))
    for tag in ("database", "source-app", "rec-number", "foreign-keys", "pdf-urls"):
        rec = re.sub(r"<%s[^>]*>.*?</%s>" % (tag, tag), "", rec, flags=re.S)
    exported[n] = rec
lost = sorted({source_id[k] for k in source_id} - set(exported))
if lost:
    sys.exit(f"EndNote did not export records {lost}: are they in the open library (not the Trash)?")
os.remove(tmp)


def sty(t):
    return '<style face="normal" font="default" size="100%">' + html.escape(t, quote=False) + "</style>"


def el(tag, t):
    return f"<{tag}>{sty(t)}</{tag}>" if t else ""


def name(a):
    a = delatex(a)
    if "," in a:
        return a
    parts = a.split()
    return parts[-1] + ", " + " ".join(parts[:-1])


def from_bib(key):
    e = entries[key]
    kind = e["type"]
    if kind == "book":
        rtype = ("Book", 6)
    elif kind == "inproceedings":
        rtype = ("Conference Proceedings", 10)
    elif kind == "misc":
        rtype = ("Computer Program", 9)
    else:
        rtype = ("Journal Article", 17)
    authors = "".join(f"<author>{sty(name(a))}</author>" for a in re.split(r"\s+and\s+", e.get("author", "")) if a.strip())
    sec = delatex(e.get("journal") or e.get("booktitle") or "")
    doi = e.get("doi", "")
    url = e.get("url") or (f"https://doi.org/{doi}" if doi else "")
    return ("<record>" + f'<ref-type name="{rtype[0]}">{rtype[1]}</ref-type>'
            + f"<contributors><authors>{authors}</authors></contributors>"
            + "<titles>" + el("title", delatex(e.get("title", ""))) + el("secondary-title", sec) + "</titles>"
            + (f"<periodical>{el('full-title', sec)}</periodical>" if rtype[1] == 17 and sec else "")
            + el("pages", delatex(e.get("pages", "")).replace("\u2013", "-"))
            + el("volume", e.get("volume", "")) + el("number", e.get("number", ""))
            + el("edition", e.get("edition", ""))
            + f"<dates>{el('year', e.get('year', ''))}</dates>"
            + el("pub-location", delatex(e.get("address", ""))) + el("publisher", delatex(e.get("publisher", "")))
            + el("isbn", e.get("isbn", ""))
            + (f"<urls><related-urls><url>{sty(url)}</url></related-urls></urls>" if url else "")
            + el("electronic-resource-num", doi)
            + "</record>")


records, cites = [], {}
for key in order:
    rec = exported[source_id[key]] if key in source_id else from_bib(key)
    records.append(rec)
    first = re.search(r"<author><style[^>]*>(.*?)</style></author>", rec)
    year = re.search(r"<year><style[^>]*>(.*?)</style></year>", rec)
    fa = html.unescape(first.group(1)).strip() if first else ""
    surname = (fa.split(",")[0].strip() if "," in fa else fa.split()[-1]) if fa else "Anonymous"  # "Last, First" or "First Last"
    cites[key] = {"num": cited[key], "author": surname, "year": html.unescape(year.group(1)) if year else "",
                  "source": "library %d" % source_id[key] if key in source_id else "bib"}

with open(out_xml, "w", encoding="utf8") as f:
    f.write('<?xml version="1.0" encoding="UTF-8" ?><xml><records>' + "".join(records) + "</records></xml>")
json.dump(cites, open(out_json, "w"), indent=1, ensure_ascii=False)
print(f"records={len(records)} from_library={len(source_id)} from_bib={len(missing)}: {', '.join(missing)}")
