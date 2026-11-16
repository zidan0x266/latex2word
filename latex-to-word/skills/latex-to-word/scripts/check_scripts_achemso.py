"""Compare every sub-/superscript and every non-ASCII symbol between an achemso .docx and its
LaTeX PDF (the achemso counterpart of check_scripts.py): achemso's sans-serif front matter is kept,
TikZ panel labels (inside the Word pictures) are dropped, and the TOC entry's heading is skipped.
Display equations are excluded (checked separately); the reference list is excluded.
Ends with an order-independent comparison: script characters per kind.
usage: python check_scripts_achemso.py X.docx X.pdf
"""
import collections, difflib, re, sys, unicodedata, zipfile
import pymupdf
from lxml import etree

docx_path, pdf_path = sys.argv[1:3]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
w = lambda t: f"{{{W}}}{t}"
m = lambda t: f"{{{M}}}{t}"
FIG_FONTS = ("ArialMT", "DejaVuSans", "HelveticaNeue", "Arial", "Helvetica")
MATH_FONTS = ("CM", "MSBM", "rsfs", "MSAM")
SAME = {"·": "⋅", "−": "-", "–": "-", "φ": "ϕ"}  # same glyph, different code point


def toc_names(docx_path):
    """the TOC entry's heading (achemso \\tocentryname): the text before the TOC Graphic picture"""
    names, prev = {"TOC Graphic"}, ""
    for p in etree.fromstring(zipfile.ZipFile(docx_path).read("word/document.xml")).iter(w("p")):
        sty = p.find(f"{w('pPr')}/{w('pStyle')}")
        if sty is not None and sty.get(w("val")) == "TOCGraphic" and prev:
            names.add(prev)
        t = "".join(x.text or "" for x in p.iter(w("t"))).strip()
        prev = t or prev
    return names


TOC_NAMES = toc_names(docx_path)


def clean(t):
    t = unicodedata.normalize("NFC", t)
    return "".join(SAME.get(c, c) for c in t).replace(" ", "").replace("​", "")


# ------------------------------------------------------------------ PDF
pdf = pymupdf.open(pdf_path)
pdf_scripts, pdf_syms, in_refs = [], collections.Counter(), False
for page in pdf:
    for b in page.get_text("dict")["blocks"]:
        lines = []
        for line in b.get("lines", []):
            spans = [s for s in line["spans"] if not s["font"].startswith(FIG_FONTS)
                     and not (re.fullmatch(r"\s*\([a-z]\)\s*", s["text"]) and s["font"].startswith("SFBX"))  # TikZ panel labels
                     and not (re.fullmatch(r"\s*\d+\s*", s["text"]) and s["bbox"][2] < 72)]   # line numbers
            spans = [s for s in spans if not re.fullmatch(r"\s*\(\d+\)\s*", s["text"])]   # equation numbers
            if spans:
                lines.append(spans)
        if not lines or all(s["font"].startswith(MATH_FONTS) for sp in lines for s in sp):
            continue                                   # empty or display-equation block
        for spans in lines:
            txt = "".join(s["text"] for s in spans)
            if txt.strip() == "References":
                in_refs = True
            if in_refs or txt.strip() in TOC_NAMES:
                continue
            if re.fullmatch(r"\s*(S-)?\d+\s*", txt) and spans[0]["bbox"][1] > page.rect.height * 0.85:
                continue                               # page number
            for s in spans:
                for ch in s["text"]:
                    if ord(ch) > 127 and not ch.isspace():
                        pdf_syms[SAME.get(ch, ch)] += 1
            main = max(spans, key=lambda s: len(s["text"].strip()))
            base_y, base_size = main["origin"][1], main["size"]
            for s in spans:
                if not s["text"].strip() or s["size"] >= base_size * 0.9:
                    continue
                dy = s["origin"][1] - base_y
                kind = "sup" if dy < -0.5 else "sub" if dy > 0.5 else None
                if kind:
                    pdf_scripts.append((kind, clean(s["text"])))

# ------------------------------------------------------------------ DOCX
root = etree.fromstring(zipfile.ZipFile(docx_path).read("word/document.xml"))
docx_scripts, docx_syms, in_refs = [], collections.Counter(), False


def math_text(el):
    return "".join(t.text or "" for t in el.iter(m("t")))


for p in root.iter(w("p")):
    ptxt = "".join(t.text or "" for t in p.iter(w("t")))
    if ptxt.strip() == "References":
        in_refs = True
    if in_refs:
        break
    if ptxt.strip() in TOC_NAMES:
        continue
    for el in p.iter(w("r"), m("sSub"), m("sSup"), m("sSubSup"), m("t")):
        if any(a.tag == m("oMathPara") for a in el.iterancestors()):
            continue                                   # display equations
        if el.tag == w("r"):
            if any(a.tag in (m("sub"), m("sup")) for a in el.iterancestors()):
                continue
            t = "".join(x.text or "" for x in el.iter(w("t")))
            for ch in t:
                if ord(ch) > 127 and not ch.isspace():
                    docx_syms[SAME.get(ch, ch)] += 1
            va = el.find(f"{w('rPr')}/{w('vertAlign')}")
            if va is not None and va.get(w("val")) in ("superscript", "subscript") and t.strip():
                docx_scripts.append(("sup" if va.get(w("val")) == "superscript" else "sub", clean(t)))
        elif el.tag == m("t"):
            for ch in el.text or "":
                if ord(ch) > 127 and not ch.isspace():
                    docx_syms[SAME.get(ch, ch)] += 1
        else:
            sub, sup = el.find(m("sub")), el.find(m("sup"))
            # LaTeX typesets a sub+sup pair as sup first in the PDF glyph stream
            if sup is not None: docx_scripts.append(("sup", clean(math_text(sup))))
            if sub is not None: docx_scripts.append(("sub", clean(math_text(sub))))

a, b = docx_scripts, pdf_scripts
print(f"sub/superscripts outside display equations: Word {len(a)}, PDF {len(b)}")
print("  Word by kind:", collections.Counter(k for k, _ in a), "| PDF by kind:", collections.Counter(k for k, _ in b))
ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
print(f"  differing spans in order: {len(ops)}")
for tag, i1, i2, j1, j2 in ops[:25]:
    print(f"    {tag:7s} Word {a[i1:i2]} | PDF {b[j1:j2]}")
print("\nnon-ASCII symbols (text + inline math, no display equations, no references):")
keys = sorted(set(docx_syms) | set(pdf_syms), key=lambda c: (-(docx_syms[c] + pdf_syms[c]), c))
for c in keys:
    flag = "" if docx_syms[c] == pdf_syms[c] else "   <-- differs"
    print(f"  {c!r:8s} U+{ord(c):04X} {unicodedata.name(c, '?')[:34]:34s} Word {docx_syms[c]:4d}  PDF {pdf_syms[c]:4d}{flag}")

print("\norder-independent: script characters per kind (commas, spaces ignored)")
for kind in ("sub", "sup"):
    cw = collections.Counter(c for k, t in a if k == kind for c in t.replace(",", "").replace("−", "-"))
    cp = collections.Counter(c for k, t in b if k == kind for c in t.replace(",", "").replace("−", "-"))
    print(f"  {kind}: Word {sum(cw.values())}, PDF {sum(cp.values())}; only Word {dict(cw - cp)}; only PDF {dict(cp - cw)}")
