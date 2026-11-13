"""Re-sync the citation map (the cites JSON from build_enxml.py) with the paper's EndNote library: first-author surname and
year of every record. EndNote matches a temporary citation {Author, Year #Rec} on all three, so
a year corrected in the library must also be corrected here before a rebuild.
usage: python3 sync_cites.py cites.json PAPER.Data/sdb/sdb.eni   (library read-only)
"""
import json, sqlite3, sys

path, db = sys.argv[1:3]
cites = json.load(open(path, encoding="utf8"))
def surname(author_field):
    first = author_field.split("\r")[0].strip()
    return first.split(",")[0].strip() if "," in first else first.split()[-1]  # "Last, First" or "First Last"


lib = {i: (surname(a), y) for i, a, y in
       sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute("select id, author, year from refs")}
fixed = []
for key, v in cites.items():
    author, year = lib[v["rec"]]
    if (v["author"], v["year"]) != (author, year):
        fixed.append(f"{key}: {v['author']}, {v['year']} -> {author}, {year} (#{v['rec']})")
        v["author"], v["year"] = author, year
with open(path, "w", encoding="utf8") as f:
    json.dump(cites, f, indent=1, ensure_ascii=False)
print(f"{len(cites)} citations checked; fixed: {fixed or 'none'}")
