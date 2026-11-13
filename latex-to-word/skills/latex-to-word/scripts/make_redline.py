"""Turn a Word Compare result into a static redline for reviewers (no tracked changes).

Additions are highlighted yellow and deletions are shown in red strikethrough, as ordinary
formatting, so Word shows no revision balloons or change bars. Fields (EndNote) are
reduced to their displayed text. The reference list is rebuilt per reference from the two
EndNote-formatted documents: new entries are highlighted, and renumbered entries show
[old→new] as [~~old~~ new].

usage: python make_redline.py COMPARE.docx CURRENT.docx INITIAL.docx OUT.docx   (needs lxml)
"""
import copy, re, sys, zipfile
from lxml import etree

cmp_path, cur_path, init_path, out_path = sys.argv[1:5]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
w = lambda t: f"{{{W}}}{t}"
m_ = lambda t: f"{{{M}}}{t}"
RPR_ORDER = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
             "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
             "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText",
             "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath"]


def read_zip(path):
    z = zipfile.ZipFile(path)
    return z, {i.filename: z.read(i.filename) for i in z.infolist()}


def set_prop(rpr, name, **attrs):
    old = rpr.find(w(name))
    if old is not None:
        rpr.remove(old)
    el = etree.Element(w(name), {w(k): v for k, v in attrs.items()})
    rank = RPR_ORDER.index(name)
    for i, child in enumerate(rpr):
        tag = etree.QName(child).localname
        if tag in RPR_ORDER and RPR_ORDER.index(tag) > rank:
            rpr.insert(i, el)
            return
    rpr.append(el)


def run_rpr(run):
    """w:rPr of a w:r or m:r, created if missing."""
    rpr = run.find(w("rPr"))
    if rpr is None:
        rpr = etree.Element(w("rPr"))
        if run.tag == m_("r") and len(run) and run[0].tag == m_("rPr"):
            run.insert(1, rpr)
        else:
            run.insert(0, rpr)
    return rpr


def mark(run, kind):
    rpr = run_rpr(run)
    if kind == "del":
        set_prop(rpr, "strike")
        set_prop(rpr, "color", val="FF0000")
    else:
        set_prop(rpr, "highlight", val="yellow")


def paragraph_text(p):
    return "".join(t.text or "" for t in p.iter(w("t"), m_("t")))


# ----------------------------------------------------------------- load
zc, parts = read_zip(cmp_path)
_, cur_parts = read_zip(cur_path)
_, init_parts = read_zip(init_path)
doc = etree.fromstring(parts["word/document.xml"])
body = doc.find(w("body"))


def heading_index(bdy):
    kids = list(bdy)
    for i, el in enumerate(kids):
        if el.tag == w("p") and paragraph_text(el).strip() == "References":
            return i
    raise SystemExit("References heading not found")


def bibliography(part):
    root = etree.fromstring(part)
    bdy = root.find(w("body"))
    kids = list(bdy)
    return [el for el in kids[heading_index(bdy) + 1:] if el.tag == w("p")]


# ----------------------------------------------------------------- reference list
for el in list(body)[heading_index(body) + 1:]:
    if el.tag != w("sectPr"):
        body.remove(el)
label = re.compile(r"^\[(\d+)\]\s*")
initial_number = {}
for p in bibliography(init_parts["word/document.xml"]):
    t = paragraph_text(p)
    if label.match(t):
        initial_number[label.sub("", t)] = int(label.match(t).group(1))

rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
cur_rels = {r.get("Id"): r for r in etree.fromstring(cur_parts["word/_rels/document.xml.rels"])}
sect = body.find(w("sectPr"))
new_refs, renumbered, kept = [], 0, 0
for k, p in enumerate(bibliography(cur_parts["word/document.xml"])):
    p = copy.deepcopy(p)
    for h in p.iter(w("hyperlink")):  # DOI links: copy the relationship into this package
        rid = h.get(f"{{{R}}}id")
        if rid in cur_rels:
            nid = f"rIdRedline{k}_{rid}"
            r = copy.deepcopy(cur_rels[rid]); r.set("Id", nid); rels.append(r)
            h.set(f"{{{R}}}id", nid)
    text = paragraph_text(p)
    lm = label.match(text)
    if lm:
        cur_n, rest = int(lm.group(1)), label.sub("", text)
        old_n = initial_number.get(rest)
        if old_n is None:
            new_refs.append(cur_n)
            for r in p.iter(w("r")):
                mark(r, "ins")
        elif old_n != cur_n:
            renumbered += 1
            t0 = next(t for t in p.iter(w("t")) if t.text)
            r0 = t0.getparent()
            head, num, tail = "[", str(cur_n), t0.text[len(f"[{cur_n}"):]
            pieces = [(head, None), (str(old_n), "del"), (" ", None), (num, "ins"), (tail, None)]
            for txt, kind in pieces:
                nr = copy.deepcopy(r0)
                nt = nr.find(w("t")); nt.text = txt
                nt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if kind:
                    mark(nr, kind)
                r0.addprevious(nr)
            r0.getparent().remove(r0)
        else:
            kept += 1
    sect.addprevious(p)

# ----------------------------------------------------------------- fields -> displayed text
stack = []
for run in list(doc.iter(w("r"))):
    fc = run.find(w("fldChar"))
    if fc is not None:
        t = fc.get(w("fldCharType"))
        if t == "begin":
            stack.append("code")
        elif t == "separate" and stack:
            stack[-1] = "result"
        elif t == "end" and stack:
            stack.pop()
        run.getparent().remove(run)
    elif "code" in stack or run.find(w("instrText")) is not None or run.find(w("delInstrText")) is not None:
        run.getparent().remove(run)
for fs in list(doc.iter(w("fldSimple"))):
    for child in list(fs):
        fs.addprevious(child)
    fs.getparent().remove(fs)

# ----------------------------------------------------------------- deleted pictures
# A picture can't be shown "struck through": Word Compare records a re-exported figure as
# old picture deleted + new one inserted, so deleted pictures are dropped, and so is a
# paragraph that only held one.
PICS = (w("drawing"), w("pict"), w("object"))
for el in list(doc.iter(w("del"), w("moveFrom"))):
    for r in list(el.iter(w("r"))):
        if any(r.find(t) is not None for t in PICS):
            r.getparent().remove(r)
for p in list(doc.iter(w("p"))):
    pmark = p.find(f"{w('pPr')}/{w('rPr')}")
    deleted_mark = pmark is not None and (pmark.find(w("del")) is not None or pmark.find(w("moveFrom")) is not None)
    has_content = any(True for _ in p.iter(w("t"), w("delText"), m_("t"), *PICS))
    if deleted_mark and not has_content:
        p.getparent().remove(p)

# ----------------------------------------------------------------- revisions -> formatting
REV = {w("ins"): "ins", w("moveTo"): "ins", w("del"): "del", w("moveFrom"): "del"}
for el in reversed([e for e in doc.iter() if e.tag in REV]):
    kind, parent = REV[el.tag], el.getparent()
    if parent is None:
        continue
    if parent.tag == w("rPr"):  # paragraph-mark / run-property revision marker
        parent.remove(el)
        continue
    if parent.tag == m_("r"):  # math run: <m:r><w:del><w:rPr/><m:t/></w:del></m:r>
        idx = parent.index(el)
        for child in list(el):
            parent.insert(idx, child); idx += 1
        parent.remove(el)
        mark(parent, kind)
        continue
    if parent.tag == m_("ctrlPr"):
        for child in list(el):
            el.addprevious(child)
        parent.remove(el)
        continue
    for r in list(el.iter(w("r"), m_("r"))):
        if kind == "del":
            for dt in r.iter(w("delText")):
                dt.tag = w("t")
        mark(r, kind)
    for child in list(el):
        el.addprevious(child)
    parent.remove(el)
for tag in ("moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd"):
    for el in list(doc.iter(w(tag))):
        el.getparent().remove(el)
leftover = [etree.QName(e).localname for e in doc.iter() if e.tag in REV or e.tag in (w("delText"), w("fldChar"))]
if leftover:
    raise SystemExit(f"unconverted revision elements left: {set(leftover)}")

parts["word/document.xml"] = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
parts["word/_rels/document.xml.rels"] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
    for info in zc.infolist():
        z.writestr(info, parts[info.filename])
print(f"wrote {out_path}: reference list: {len(new_refs)} new {new_refs}, {renumbered} renumbered, {kept} unchanged")
