"""Independent consistency check: Word manuscript (main.docx) vs the PDF LaTeX compiles from
main.tex. Compares prose word by word (body; captions/affiliations/footnotes), the sequence of
citation numbers, equation numbering, and the reference list entry by entry.
Math is compared separately because the PDF stores it as positioned glyphs.

usage: python compare_docx_pdf.py main.docx main.pdf      (needs PyMuPDF, lxml)
"""
import difflib, re, sys, unicodedata, zipfile
import pymupdf
from lxml import etree

docx_path, pdf_path = sys.argv[1:3]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
w = lambda t: f"{{{W}}}{t}"
FIG_FONTS = ("ArialMT", "DejaVuSans", "HelveticaNeue", "Arial", "Helvetica")


def norm(t):
    return unicodedata.normalize("NFKC", t).replace("−", "-").replace("–", "-").replace(" ", " ")


def tokens(t):
    return re.findall(r"\w+", norm(t).lower().replace("-", ""))


# ------------------------------------------------------------------ PDF
MATH_FONTS = ("CM", "MSBM", "rsfs", "MSAM")
pdf = pymupdf.open(pdf_path)
pdf_body, pdf_small, pdf_bib_lines, pdf_eqnums = [], [], [], []
in_refs = False
for page in pdf:
    H, Wd = page.rect.height, page.rect.width
    pno = str(page.number + 1)
    for b in page.get_text("dict")["blocks"]:
        block_lines = []
        for line in b.get("lines", []):
            spans = [s for s in line["spans"] if not s["font"].startswith(FIG_FONTS) and not s["font"].startswith("SFSS")
                     and not (re.fullmatch(r"\s*\d+\s*", s["text"]) and s["bbox"][2] < 72)]   # line numbers
            if "".join(s["text"] for s in spans).strip() == pno and line["bbox"][1] > H * 0.85:
                continue                                       # page number
            if not in_refs:
                keep = []
                for s in spans:
                    m = re.fullmatch(r"\s*\((\d+)\)\s*", s["text"])
                    if m and s["bbox"][0] > Wd * 0.8:
                        pdf_eqnums.append(int(m.group(1)))   # equation number
                    else:
                        keep.append(s)
                spans = keep
            block_lines.append(spans)
        if not any(not s["font"].startswith(MATH_FONTS) for spans in block_lines for s in spans):
            continue                                           # pure-math block = display equation
        for spans in block_lines:
            if not spans:
                continue
            text_spans = [s for s in spans if not s["font"].startswith(MATH_FONTS)] or spans
            txt = "".join(s["text"] for s in spans)            # inline math kept, in reading order
            size = max(text_spans, key=lambda s: len(s["text"].strip()))["size"]
            if txt.strip() == "References":
                in_refs = True
                continue
            if in_refs:
                pdf_bib_lines.append(txt)
            elif size < 11:
                pdf_small.append(txt)
            else:
                pdf_body.append(txt)


def join_lines(lines):
    out = ""
    for l in lines:
        l = l.rstrip()
        if out.endswith(("-", "\u2013", "\u2014", "/")) and l[:1].isalnum():
            out = out + l               # hyphen / en dash / slash at a line end: no space (hyphens dropped in tokens)
        else:
            out += " " + l
    return out


pdf_body_text, pdf_small_text = join_lines(pdf_body), join_lines(pdf_small)

# ------------------------------------------------------------------ DOCX
root = etree.fromstring(zipfile.ZipFile(docx_path).read("word/document.xml"))
docx_body, docx_small, docx_bib = [], [], []
eq_numbers, inline_math = [], []
in_refs = False
SMALL_STYLES = {"ImageCaption", "Affiliation", "Correspondence"}
for p in root.iter(w("p")):
    sty = p.find(f"{w('pPr')}/{w('pStyle')}")
    sty = sty.get(w("val")) if sty is not None else ""
    for om in p.iter(f"{{{M}}}oMathPara"):
        eq = "".join(t.text or "" for t in om.iter(f"{{{M}}}t"))
        m = re.search(r"#(\d+)$", eq)
        eq_numbers.append(int(m.group(1)) if m else None)
    parts = []
    for t in p.iter(w("t"), f"{{{M}}}t"):
        if any(a.tag == f"{{{M}}}oMathPara" for a in t.iterancestors()):
            continue                                       # display equations: compared separately
        parts.append(t.text or "")
    text = "".join(parts)                                  # field codes are instrText, never included
    if text.strip() == "References":
        in_refs = True
        continue
    if in_refs:
        if text.strip(): docx_bib.append(text)
    elif sty in SMALL_STYLES:
        docx_small.append(text)
    elif text.strip():
        docx_body.append(text)
docx_body_text, docx_small_text = " ".join(docx_body), " ".join(docx_small)


def compare(name, a_text, b_text, show=12):
    a, b = tokens(a_text), tokens(b_text)
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    print(f"\n== {name}: Word {len(a)} words, PDF {len(b)} words, {len(ops)} differing spans")
    for tag, i1, i2, j1, j2 in ops[:show]:
        print(f"   {tag:7s} Word: {' '.join(a[max(0, i1 - 4):i2 + 3])[:110]!r}\n           PDF : {' '.join(b[max(0, j1 - 4):j2 + 3])[:110]!r}")
    return ops


compare("Body text (title, front matter, abstract, sections, back matter)", docx_body_text, pdf_body_text)
compare("Small text (affiliations, footnotes, figure captions)", docx_small_text, pdf_small_text)

# ------------------------------------------------------------------ citations
cite = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")
def cite_seq(text):
    return [re.sub(r"\s+", "", norm(c)) for c in cite.findall(norm(text))]
cw, cp = cite_seq(docx_body_text + " " + docx_small_text), cite_seq(pdf_body_text + " " + pdf_small_text)
print(f"\n== Citation groups in reading order: Word {len(cw)}, PDF {len(cp)}")
cw_body, cp_body = cite_seq(docx_body_text), cite_seq(pdf_body_text)
print(f"   in body text: identical sequence = {cw_body == cp_body} ({len(cw_body)} groups)")
cw_cap, cp_cap = cite_seq(docx_small_text), cite_seq(pdf_small_text)
print(f"   in captions:  identical sequence = {cw_cap == cp_cap} ({len(cw_cap)} groups)")
for tag, i1, i2, j1, j2 in [o for o in difflib.SequenceMatcher(None, cw_body, cp_body, autojunk=False).get_opcodes() if o[0] != "equal"][:10]:
    print(f"   {tag}: Word {cw_body[i1:i2]} | PDF {cp_body[j1:j2]}")

# ------------------------------------------------------------------ equations
print(f"\n== Display equations: Word numbers {eq_numbers}\n                       PDF  numbers {pdf_eqnums}")

# ------------------------------------------------------------------ references
entries, cur = [], None
for l in pdf_bib_lines:
    m = re.match(r"\s*\[(\d+)\]\s*(.*)", l)
    if m:
        cur = [int(m.group(1)), m.group(2)]; entries.append(cur)
    elif cur and l.strip():
        cur[1] = (cur[1][:-1] + l.strip()) if cur[1].endswith("-") and l.strip()[:1].isalpha() else cur[1] + " " + l.strip()
pdf_refs = {n: t for n, t in entries}
word_refs = {}
for t in docx_bib:
    m = re.match(r"\s*\[(\d+)\]\s*(.*)", t)
    if m: word_refs[int(m.group(1))] = m.group(2)
print(f"\n== Reference list: Word {len(word_refs)} entries, PDF {len(pdf_refs)} entries")
def ref_tokens(t):
    t = norm(t).lower()
    t = re.sub(r"https?://\S+", " ", t)                     # DOI links (EndNote style only)
    t = re.sub(r"(\d+)\s*\(\s*[\w\-–]+\s*\)(?=\s*\()", r"\1", t)  # volume(issue) -> volume
    t = re.sub(r"\b(\w)\.\s*(?=\w\.)", r"\1.", t)            # initials "y. a." -> "y.a."
    return re.findall(r"\w+", t.replace("-", ""))
bad = []
for n in sorted(set(word_refs) | set(pdf_refs)):
    a, b = ref_tokens(word_refs.get(n, "")), ref_tokens(pdf_refs.get(n, ""))
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    if ops:
        bad.append((n, [(" ".join(a[i1:i2]), " ".join(b[j1:j2])) for _, i1, i2, j1, j2 in ops]))
print(f"   entries that differ in content (authors/title/journal/volume/year/pages): {len(bad)}")
for n, diffs in bad:
    print(f"     [{n}] " + "; ".join(f"Word {x!r} vs PDF {y!r}" for x, y in diffs)[:300])
