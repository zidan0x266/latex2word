"""Compare the records of a paper's EndNote library with their counterparts in a source library
(e.g. the author's main library), field by field. Read-only on both.
usage: python3 en_diff.py PAPER.Data/sdb/sdb.eni SOURCE.Data/sdb/sdb.eni OUT.json"""
import json, re, sqlite3, sys, unicodedata
from collections import Counter

paper_db, source_db, out = sys.argv[1:4]
COLS = ["reference_type", "author", "year", "title", "secondary_title", "volume", "number", "pages",
        "electronic_resource_number", "publisher", "place_published", "isbn", "edition", "url", "alternate_title",
        "date", "abstract", "keywords", "language"]
MINOR = {"abstract", "keywords", "url", "language", "alternate_title", "date", "isbn"}


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def ndoi(d):
    return re.sub(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", "", (d or "").strip(), flags=re.I).lower()


def load(p):
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(f"select id, trash_state, {', '.join(COLS)} from refs")]


paper = {r["id"]: r for r in load(paper_db)}
by_doi, by_title = {}, {}
for r in load(source_db):
    if r["trash_state"]:
        continue
    if ndoi(r["electronic_resource_number"]):
        by_doi.setdefault(ndoi(r["electronic_resource_number"]), []).append(r)
    by_title.setdefault(norm(r["title"]), []).append(r)

report = {}
for n, c in sorted(paper.items()):
    cands = by_doi.get(ndoi(c["electronic_resource_number"]), []) if ndoi(c["electronic_resource_number"]) else []
    cands = cands or by_title.get(norm(c["title"]), [])
    if not cands:
        report[n] = {"match": None}
        continue
    m = max(cands, key=lambda r: r["id"])  # newest copy in the source library
    diffs = {}
    for col in COLS:
        a = str(c[col] if c[col] is not None else "").strip()
        b = str(m[col] if m[col] is not None else "").strip()
        if col == "electronic_resource_number":
            a, b = ndoi(a), ndoi(b)
        if a != b:
            diffs[col] = {"paper": a[:200], "source": b[:200]}
    report[n] = {"match": m["id"], "copies": [r["id"] for r in cands], "diffs": diffs}

json.dump(report, open(out, "w"), indent=1, ensure_ascii=False)
unmatched = [n for n, v in report.items() if v["match"] is None]
print("paper library records:", len(paper), "| found in source library:", len(paper) - len(unmatched), "| not found:", unmatched)
print("fields that differ (number of records):", dict(Counter(col for v in report.values() if v["match"] for col in v["diffs"])))
for n, v in report.items():
    if v["match"] and set(v["diffs"]) - MINOR:
        print(f"  [{n}] source rec {v['match']}:",
              {k: (d["paper"][:45], d["source"][:45]) for k, d in v["diffs"].items() if k not in MINOR})
