"""Check DOIs in an EndNote library against Crossref/DataCite; search DOIs for records without one.
Read-only on the library. usage: python3 verify_doi.py SDB_ENI OUT.json
"""
import difflib, json, re, sqlite3, sys, time, unicodedata, urllib.parse, urllib.request

db, out = sys.argv[1:3]
UA = {"User-Agent": "doi-check/1.0 (manuscript reference verification)"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}


def norm(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def meta_crossref(m):
    year = None
    for k in ("published-print", "published-online", "issued", "published"):
        dp = (m.get(k) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            year = dp[0][0]; break
    au = (m.get("author") or [{}])[0]
    return {"title": " ".join(m.get("title") or [""]) + ((": " + " ".join(m["subtitle"])) if m.get("subtitle") else ""),
            "first": au.get("family") or au.get("name") or "", "year": year,
            "container": " ".join(m.get("container-title") or [""]), "type": m.get("type"),
            "volume": m.get("volume", ""), "page": m.get("page", "")}


con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
rows = con.execute("select id, author, year, title, secondary_title, electronic_resource_number from refs order by id").fetchall()
results = []
for rid, author, year, title, sec, doi in rows:
    first = author.split("\r")[0].split(",")[0].strip()
    rec = {"rec": rid, "first": first, "year": year, "title": title, "doi": doi}
    if doi:
        r = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))
        if "message" in r:
            m = meta_crossref(r["message"]); rec["source"] = "crossref"
        else:
            d = get("https://api.datacite.org/dois/" + urllib.parse.quote(doi))
            if "data" in d:
                a = d["data"]["attributes"]
                m = {"title": (a.get("titles") or [{}])[0].get("title", ""),
                     "first": ((a.get("creators") or [{}])[0].get("familyName") or (a.get("creators") or [{}])[0].get("name", "")),
                     "year": a.get("publicationYear"), "container": a.get("publisher", ""), "type": a.get("types", {}).get("resourceTypeGeneral")}
                rec["source"] = "datacite"
            else:
                m = None; rec["source"] = "not found"
        rec["registered"] = m
        if m:
            rec["title_sim"] = round(sim(title, m["title"]), 3)
            rec["first_ok"] = norm(first).split()[-1:] == norm(m["first"]).split()[-1:] if m["first"] else None
            rec["year_ok"] = str(m["year"]) == str(year)
    else:
        q = urllib.parse.urlencode({"query.bibliographic": f"{title} {first} {year}", "rows": 5})
        r = get("https://api.crossref.org/works?" + q)
        cands = []
        for it in (r.get("message") or {}).get("items", []):
            m = meta_crossref(it)
            cands.append({"doi": it.get("DOI"), **m, "title_sim": round(sim(title, m["title"]), 3),
                          "first_ok": norm(first).split()[-1:] == norm(m["first"]).split()[-1:] if m["first"] else None})
        rec["candidates"] = sorted(cands, key=lambda c: -c["title_sim"])[:3]
    results.append(rec)
    time.sleep(0.3)
json.dump(results, open(out, "w"), indent=1, ensure_ascii=False)
ok = [r for r in results if r.get("registered") and r["title_sim"] >= 0.9 and r["first_ok"] and r["year_ok"]]
print(f"with DOI: {sum(1 for r in results if r['doi'])}, clean match: {len(ok)}")
for r in results:
    if r["doi"] and r not in ok:
        m = r.get("registered") or {}
        print(f"CHECK #{r['rec']} {r['first']} {r['year']} doi={r['doi']} [{r['source']}] sim={r.get('title_sim')} first_ok={r.get('first_ok')} reg_year={m.get('year')}\n   lib: {r['title'][:90]}\n   reg: {m.get('title','')[:90]} | {m.get('first')} | {m.get('container','')[:50]}")
for r in results:
    if not r["doi"]:
        print(f"NO DOI #{r['rec']} {r['first']} {r['year']}: {r['title'][:70]}")
        for c in r["candidates"]:
            print(f"   {c['title_sim']:.2f} first_ok={c['first_ok']} {c['year']} {c['doi']} | {c['title'][:70]} | {c['container'][:40]} | {c['type']}")
