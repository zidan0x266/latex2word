"""Independent consistency check: achemso Word manuscript vs the PDF LaTeX compiles from the same
.tex (the achemso counterpart of compare_docx_pdf.py).

Compares prose word by word (body; captions and table notes), table contents (as a bag of words,
since the PDF reads table cells in layout order), [REF: ...]-style placeholders, the sequence of
citation groups (superscript or round), equation numbering, and the reference list entry by entry.
PDF side: tables are found by their booktabs rules; caption blocks start with "Figure/Scheme/
Chart/Graph/Table N:"; TikZ panel labels and figure fonts are dropped (they are inside the Word
pictures); the TOC entry's heading is skipped and reading stops at it after the references (its
picture is compared by eye). Word side: citations are the runs linked to a
reference (pandoc's #_bibN bookmarks) or inside an EndNote field; \\citenum (plain number) is left out on both sides.
Math is compared separately because the PDF stores it as positioned glyphs.

usage: python compare_achemso.py X.docx X.pdf      (needs PyMuPDF, lxml)
"""
import collections, difflib, re, sys, unicodedata, zipfile
import pymupdf
from lxml import etree

docx_path, pdf_path = sys.argv[1:3]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
w = lambda t: f"{{{W}}}{t}"
FIG_FONTS = ("ArialMT", "DejaVuSans", "HelveticaNeue", "Arial", "Helvetica")
MATH_FONTS = ("CM", "MSBM", "rsfs", "MSAM")
CAPTION = re.compile(r"\s*(Figure|Scheme|Chart|Graph|Table) S?\d+:")
CITE_GROUP = re.compile(r"^\(?S?\d+(?:[,–-]S?\d+)*\)?$")


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


def norm(t):
    t = unicodedata.normalize("NFKC", t).replace("∆", "Δ")   # PDF increment sign = Word Delta
    return t.replace("−", "-").replace("–", "-").replace(" ", " ")


def tokens(t):
    t = norm(t).lower()
    t = re.sub(r"(?<=[^\W\d])-(?=[^\W\d])", "", t)   # hyphenated words / line-end hyphens: joined
    return re.findall(r"\w+", t.replace("-", " "))  # any other '-' (minus): a separator


def cite_norm(t):
    return re.sub(r"[\s()]", "", t).replace("-", "–")


def table_regions(page):
    """booktabs rules: horizontal strokes (or thin filled rectangles) < 1.2 pt; >= 3 of the same
    width = one table."""
    rules = collections.defaultdict(list)
    for d in page.get_drawings():
        for it in d["items"]:
            r = None
            if it[0] == "re" and d.get("fill") is not None and it[1].height < 1.2:
                r = it[1]
            elif it[0] == "l" and abs(it[1].y - it[2].y) < 0.1 and (d.get("width") or 0) < 1.2:
                r = pymupdf.Rect(min(it[1].x, it[2].x), it[1].y - 0.5, max(it[1].x, it[2].x), it[1].y + 0.5)
            if r is not None and r.width > 50:
                rules[(round(r.x0), round(r.x1))].append(r)
    return [pymupdf.Rect(x0, min(r.y0 for r in rs), x1, max(r.y1 for r in rs))
            for (x0, x1), rs in rules.items() if len(rs) >= 3]


def in_region(bbox, regions):
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(r.x0 - 2 <= cx <= r.x1 + 2 and r.y0 <= cy <= r.y1 for r in regions)


def raised_groups(spans):
    """superscript citation groups in one PDF line: consecutive small, raised text-font spans"""
    text_spans = [s for s in spans if s["text"].strip() and not s["font"].startswith(MATH_FONTS)]
    if not text_spans:
        return []
    main = max(text_spans, key=lambda s: len(s["text"].strip()))
    groups, cur = [], ""
    for s in spans:
        small = s["size"] < main["size"] * 0.9 and s["origin"][1] < main["origin"][1] - 0.5
        if small and not s["font"].startswith(MATH_FONTS):
            cur += s["text"]
        elif cur and not s["text"].strip() and small:
            continue
        else:
            if cur.strip():
                groups.append(cur)
            cur = ""
    if cur.strip():
        groups.append(cur)
    return [cite_norm(g) for g in groups if CITE_GROUP.match(cite_norm(g))]


# ------------------------------------------------------------------ PDF
pdf = pymupdf.open(pdf_path)
pdf_body, pdf_small, pdf_table, pdf_bib_lines, pdf_eqnums = [], [], [], [], []
pdf_cites = {"body": [], "small": []}
in_refs, done = False, False
for page in pdf:
    if done:
        break
    H, Wd = page.rect.height, page.rect.width
    pno_re = r"\s*(S-)?%d\s*" % (page.number + 1)
    tables = table_regions(page)
    for b in page.get_text("dict")["blocks"]:
        if done:
            break
        block_lines, has_eqnum = [], False
        for line in b.get("lines", []):
            spans = [s for s in line["spans"] if not s["font"].startswith(FIG_FONTS)
                     and not (re.fullmatch(r"\s*\([a-z]\)\s*", s["text"]) and s["font"].startswith("SFBX"))  # TikZ panel labels
                     and not (re.fullmatch(r"\s*\d+\s*", s["text"]) and s["bbox"][2] < 72)]   # line numbers
            if re.fullmatch(pno_re, "".join(s["text"] for s in spans)) and line["bbox"][1] > H * 0.85:
                continue                                       # page number
            if not in_refs:
                prose = [s for s in spans if not s["font"].startswith(MATH_FONTS) and s["text"].strip()]
                keep = []
                for s in spans:
                    m = re.fullmatch(r"\s*\(([A-Z]?\d+)\)\s*", s["text"])   # (1), or (S1) in an SI
                    if m and s["bbox"][0] > Wd * 0.8 and all(p is s for p in prose):
                        pdf_eqnums.append(m.group(1))   # equation number: alone at the right margin
                        has_eqnum = True
                    else:
                        keep.append(s)
                spans = keep
            block_lines.append((line["bbox"], spans))
        if has_eqnum or not any(not s["font"].startswith(MATH_FONTS) for _, sp in block_lines for s in sp):
            continue                                           # display equation
        first = next(("".join(s["text"] for s in sp) for _, sp in block_lines if sp), "")
        caption_block = CAPTION.match(first) is not None
        for bbox, spans in block_lines:
            if not spans:
                continue
            text_spans = [s for s in spans if not s["font"].startswith(MATH_FONTS)] or spans
            txt = "".join(s["text"] for s in spans)            # inline math kept, in reading order
            size = max(text_spans, key=lambda s: len(s["text"].strip()))["size"]
            if txt.strip() in TOC_NAMES:                       # achemso TOC entry: one picture in Word
                if in_refs:
                    done = True
                    break
                continue
            if txt.strip() == "References":
                in_refs = True
                continue
            if in_refs:
                pdf_bib_lines.append(txt)
                continue
            where = "small" if caption_block or size < 10.5 or in_region(bbox, tables) else "body"
            pdf_cites[where] += raised_groups(spans)
            if in_region(bbox, tables):
                pdf_table.append(txt)
            elif where == "small":                             # captions; table notes (\footnotesize)
                pdf_small.append(txt)
            else:
                pdf_body.append(txt)                           # incl. the \small abstract


def join_lines(lines):
    out = ""
    for l in lines:
        l = l.rstrip()
        if out.endswith(("-", "–", "—", "/")) and l[:1].isalnum():
            out = out + l
        else:
            out += " " + l
    return out


pdf_body_text, pdf_small_text, pdf_table_text = join_lines(pdf_body), join_lines(pdf_small), " ".join(pdf_table)

# ------------------------------------------------------------------ DOCX
root = etree.fromstring(zipfile.ZipFile(docx_path).read("word/document.xml"))
docx_body, docx_small, docx_table, docx_bib = [], [], [], []
docx_cites = {"body": [], "small": []}
eq_numbers = []
in_refs = False
SMALL_STYLES = {"ImageCaption", "TableCaption", "TableNote"}


def paragraph_cites(p):
    """citation groups: runs linked to #bibN or inside an EndNote field result, merged across
    separators; superscript groups, or round groups standing in parentheses"""
    fields, marked = [], []
    for el in p.iter(w("r")):
        for fc in el.iter(w("fldChar"), w("instrText")):
            if fc.tag == w("instrText"):
                if fields: fields[-1][0] += fc.text or ""
            elif fc.get(w("fldCharType")) == "begin":
                fields.append(["", False])
            elif fc.get(w("fldCharType")) == "separate" and fields:
                fields[-1][1] = True
            elif fc.get(w("fldCharType")) == "end" and fields:
                fields.pop()
        if any(a.tag == f"{{{M}}}oMath" for a in el.iterancestors()):
            continue
        t = "".join(x.text or "" for x in el.iter(w("t")))
        link = any(a.tag == w("hyperlink") and (a.get(w("anchor")) or "").lstrip("_").startswith("bib") for a in el.iterancestors())
        endnote = any("EN.CITE" in instr and res for instr, res in fields)
        va = el.find(f"{w('rPr')}/{w('vertAlign')}")
        sup = va is not None and va.get(w("val")) == "superscript"
        marked.append((t, link or endnote, sup))
    sup_mode = any(c and sp for _, c, sp in marked)
    # superscript mode: linked superscript runs only (\citenum is a plain, linked number);
    # round mode: linked runs, kept below only when the group stands in parentheses
    s = "".join(("\x01" + t + "\x02") if c and (sp or not sup_mode) else t for t, c, sp in marked)
    groups = []
    for m in re.finditer(r"\x01[^\x02]*\x02(?:[,;\s\u2013\-]*\x01[^\x02]*\x02)*", s):
        g = cite_norm(m.group(0).replace("\x01", "").replace("\x02", ""))
        if not sup_mode and not (s[:m.start()].rstrip().endswith("(") and s[m.end():].lstrip().startswith(")")):
            continue
        if CITE_GROUP.match(g):
            groups.append(g)
    return groups


for p in root.iter(w("p")):
    sty = p.find(f"{w('pPr')}/{w('pStyle')}")
    sty = sty.get(w("val")) if sty is not None else ""
    for om in p.iter(f"{{{M}}}oMathPara"):
        eq = "".join(t.text or "" for t in om.iter(f"{{{M}}}t"))
        m = re.search(r"#([A-Z]?\d+)$", eq)
        eq_numbers.append(m.group(1) if m else None)
    parts = []
    for t in p.iter(w("t"), w("tab"), f"{{{M}}}t"):
        if any(a.tag == f"{{{M}}}oMathPara" for a in t.iterancestors()):
            continue
        parts.append("\t" if t.tag == w("tab") else t.text or "")
    text = "".join(parts)
    if text.strip() in TOC_NAMES:
        if in_refs:
            break
        continue
    if text.strip() == "References":
        in_refs = True
        continue
    if in_refs:
        if text.strip(): docx_bib.append(text)
        continue
    in_table = any(a.tag == w("tbl") for a in p.iterancestors())
    where = "small" if in_table or sty in SMALL_STYLES else "body"
    docx_cites[where] += paragraph_cites(p)
    if in_table:
        docx_table.append(text)
    elif where == "small":
        docx_small.append(text)
    elif text.strip():
        docx_body.append(text)
docx_body_text, docx_small_text, docx_table_text = " ".join(docx_body), " ".join(docx_small), " ".join(docx_table)
# round citations, (1), (2, 3), (1–4): read from the PDF text only when Word has citations but the
# PDF has no superscript ones, so that a "(0)" in an inline formula is not taken for a citation
if not any(pdf_cites.values()) and any(docx_cites.values()):
    for where, text in (("body", pdf_body_text), ("small", pdf_small_text)):
        pdf_cites[where] = [cite_norm(g) for g in re.findall(r"\((S?\d+(?:\s*[,–-]\s*S?\d+)*)\)", norm(text))]


def compare(name, a_text, b_text, show=25):
    a, b = tokens(a_text), tokens(b_text)
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    print(f"\n== {name}: Word {len(a)} words, PDF {len(b)} words, {len(ops)} differing spans")
    for tag, i1, i2, j1, j2 in ops[:show]:
        print(f"   {tag:7s} Word: {' '.join(a[max(0, i1 - 4):i2 + 3])[:110]!r}\n           PDF : {' '.join(b[max(0, j1 - 4):j2 + 3])[:110]!r}")
    return ops


compare("Body text (title, front matter, abstract, sections)", docx_body_text, pdf_body_text)
compare("Captions and table notes", docx_small_text, pdf_small_text)
tw, tp = collections.Counter(tokens(docx_table_text)), collections.Counter(tokens(pdf_table_text))
print(f"\n== Table contents (bag of words): Word {sum(tw.values())}, PDF {sum(tp.values())}; "
      f"only in Word {sum((tw - tp).values())}, only in PDF {sum((tp - tw).values())}")
if tw - tp: print("   only Word:", dict((tw - tp).most_common(20)))
if tp - tw: print("   only PDF :", dict((tp - tw).most_common(20)))

# ------------------------------------------------------------------ [REF: ...]-style placeholders
refp = re.compile(r"\[REF:\s*([^\]]+)\]")
def refs_of(t):
    return [re.sub(r"\s+", " ", x).strip() for x in refp.findall(re.sub(r"-\s+", "-", norm(t)))]
rw, rp = refs_of(docx_body_text + " " + docx_small_text), refs_of(pdf_body_text + " " + pdf_small_text)
if rw or rp:
    print(f"\n== [REF: ...] placeholders: Word {len(rw)}, PDF {len(rp)}, identical sequence = {rw == rp}")
    for tag, i1, i2, j1, j2 in [o for o in difflib.SequenceMatcher(None, rw, rp, autojunk=False).get_opcodes() if o[0] != "equal"]:
        print(f"   {tag}: Word {rw[i1:i2]} | PDF {rp[j1:j2]}")

# ------------------------------------------------------------------ citations
for where in ("body", "small"):
    a, b = docx_cites[where], pdf_cites[where]
    print(f"\n== Citation groups in {'body text' if where == 'body' else 'captions/tables'}: Word {len(a)}, PDF {len(b)}, "
          f"identical sequence = {a == b}")
    for tag, i1, i2, j1, j2 in [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"][:10]:
        print(f"   {tag}: Word {a[i1:i2]} | PDF {b[j1:j2]}")

# ------------------------------------------------------------------ equations
print(f"\n== Display equations: Word numbers {eq_numbers}\n                       PDF  numbers {pdf_eqnums}"
      f"\n   identical = {eq_numbers == pdf_eqnums}")

# ------------------------------------------------------------------ references
LABEL = re.compile(r"\s*[\[(]?(S?\d+)[\]).]?\s+(.*)")
entries, cur = [], None
for l in pdf_bib_lines:
    m = LABEL.match(l)
    if m and (not entries or m.group(1).lstrip("S") == str(int(entries[-1][0].lstrip("S")) + 1)):
        cur = [m.group(1), m.group(2)]; entries.append(cur)
    elif cur and l.strip():
        cur[1] = (cur[1][:-1] + l.strip()) if cur[1].endswith("-") and l.strip()[:1].isalpha() else cur[1] + " " + l.strip()
pdf_refs = {n: t for n, t in entries}
word_refs = {m.group(1): m.group(2) for t in docx_bib for m in [LABEL.match(t)] if m}
print(f"\n== Reference list: Word {len(word_refs)} entries, PDF {len(pdf_refs)} entries")


def ref_tokens(t):
    t = norm(t).lower()
    t = re.sub(r"https?://\S+|\b10\.\d{4,}/\S+", " ", t)              # DOI links (EndNote style only)
    t = re.sub(r"\b(\w)\.\s*(?=\w\.)", r"\1.", t)                      # initials "y. a." -> "y.a."
    return re.findall(r"\w+", t.replace("-", ""))


bad = []
for n in sorted(set(word_refs) | set(pdf_refs), key=lambda k: int(k.lstrip("S"))):
    a, b = ref_tokens(word_refs.get(n, "")), ref_tokens(pdf_refs.get(n, ""))
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    if ops:
        bad.append((n, [(" ".join(a[i1:i2]), " ".join(b[j1:j2])) for _, i1, i2, j1, j2 in ops]))
print(f"   entries that differ in content: {len(bad)}")
for n, diffs in bad:
    print(f"     ({n}) " + "; ".join(f"Word {x!r} vs PDF {y!r}" for x, y in diffs)[:300])
