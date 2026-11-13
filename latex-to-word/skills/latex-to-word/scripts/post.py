"""Finish the pandoc docx: numbered equations, page-number footer, page setup, line numbers.

usage: python3 post.py IN.docx EQNUMS.json OUT.docx [--tables] [--page-prefix TEXT]
  --tables:          booktabs-style tables (achemso; prep_achemso.py writes STEM_post.opts)
  --page-prefix S-:  page numbers S-1, S-2, ... (achemso Supporting Information)
"""
import json
import re
import sys
import zipfile

src, eq_json, dst = sys.argv[1:4]
flags = sys.argv[4:]
TABLES = "--tables" in flags
PAGE_PREFIX = flags[flags.index("--page-prefix") + 1] if "--page-prefix" in flags else ""
eqnums = json.load(open(eq_json))

with zipfile.ZipFile(src) as z:
    parts = {n: z.read(n) for n in z.namelist()}
doc = parts["word/document.xml"].decode("utf8")

# --- equations: Word's native numbered-equation form, i.e. eqArr containing "#(n)",
# which Word renders centred with the number flush right.
MATH_CTRL = '<m:ctrlPr><w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/><w:i/></w:rPr></m:ctrlPr>'
paras = list(re.finditer(r"<m:oMathPara>.*?</m:oMathPara>", doc, re.S))
if len(paras) != len(eqnums):
    sys.exit(f"display equations in docx ({len(paras)}) != numbered equations in LaTeX ({len(eqnums)})")
out, pos = [], 0
for m, n in zip(paras, eqnums):
    block = m.group(0)
    inner = re.search(r"<m:oMath>(.*)</m:oMath>", block, re.S).group(1)
    numbered = ("<m:oMath><m:eqArr><m:eqArrPr><m:maxDist m:val=\"1\"/>" + MATH_CTRL + "</m:eqArrPr><m:e>"
                + inner
                + "<m:r><m:t>#</m:t></m:r><m:d><m:dPr>" + MATH_CTRL + "</m:dPr><m:e><m:r><m:t>"
                + n + "</m:t></m:r></m:e></m:d></m:e></m:eqArr></m:oMath>")
    block = re.sub(r"<m:oMath>.*</m:oMath>", lambda _: numbered, block, flags=re.S)
    out.append(doc[pos:m.start()] + block)
    pos = m.end()
out.append(doc[pos:])
doc = "".join(out)
doc = re.sub(r'<w:pStyle w:val="BodyText" /></w:pPr><m:oMathPara>',
             '<w:pStyle w:val="Equation" /></w:pPr><m:oMathPara>', doc)

# --- tables (--tables): booktabs look (top/bottom rule 1 pt, rule under the header 0.5 pt, no other
# lines), centred, columns sized to their content; the caption above and the threeparttable
# notes below take the width of the table, as in the PDF.
TEXT_TW, CHAR_TW, PAD_TW = 9360, 100, 300     # 6.5 in; ~10 pt Times average glyph; cell padding


def cell_text(tc):
    return "".join(re.findall(r"<(?:w|m):t(?: [^>]*)?>([^<]*)</(?:w|m):t>", tc))


def format_table(tbl, keep_last):
    rows = re.findall(r"<w:tr>.*?</w:tr>", tbl, re.S)
    ncol = len(re.findall(r"<w:gridCol ", tbl))
    need = [0] * ncol
    for r in rows:
        col = 0
        for tc in re.findall(r"<w:tc>.*?</w:tc>", r, re.S):
            span = int((re.search(r'<w:gridSpan w:val="(\d+)"', tc) or [0, 1])[1])
            if span == 1:
                need[col] = max(need[col], len(cell_text(tc).strip()) * CHAR_TW + PAD_TW)
            col += span
    total = sum(need)
    if total > TEXT_TW:
        need = [int(w * TEXT_TW / total) for w in need]
        total = sum(need)
    grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}" />' for w in need) + "</w:tblGrid>"
    tbl = re.sub(r"<w:tblGrid>.*?</w:tblGrid>", grid, tbl, flags=re.S)
    tbl = re.sub(r'<w:tblW w:type="auto" w:w="0" />',
                 f'<w:tblW w:type="dxa" w:w="{total}" /><w:jc w:val="center" />'
                 '<w:tblBorders><w:top w:val="single" w:sz="8" w:space="0" w:color="000000" />'
                 '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000" />'
                 '<w:insideH w:val="nil" /><w:insideV w:val="nil" /></w:tblBorders>'
                 '<w:tblLayout w:type="fixed" />', tbl, count=1)
    new_rows = []
    for k, r in enumerate(rows):
        col, cells = 0, []
        for tc in re.findall(r"<w:tc>.*?</w:tc>", r, re.S):
            span = int((re.search(r'<w:gridSpan w:val="(\d+)"', tc) or [0, 1])[1])
            w = sum(need[col:col + span])
            border = ('<w:tcBorders><w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000" /></w:tcBorders>'
                      if k == 0 else "")
            span_xml = f'<w:gridSpan w:val="{span}" />' if span > 1 else ""
            tc = re.sub(r"<w:tcPr ?/>|<w:tcPr>.*?</w:tcPr>",
                        lambda _: f'<w:tcPr><w:tcW w:w="{w}" w:type="dxa" />{span_xml}{border}</w:tcPr>', tc, count=1, flags=re.S)
            cells.append(tc)
            col += span
        head = re.match(r"<w:tr>(<w:trPr>.*?</w:trPr>)?", r, re.S).group(0)
        row = head + "".join(cells) + "</w:tr>"
        if k < len(rows) - 1 or keep_last:   # Word's way to keep a table (and its notes) on one page
            row = row.replace('<w:pStyle w:val="Compact" />', '<w:pStyle w:val="Compact" /><w:keepNext />')
        new_rows.append(row)
    out, pos = [], 0
    for r, nr in zip(re.finditer(r"<w:tr>.*?</w:tr>", tbl, re.S), new_rows):
        out.append(tbl[pos:r.start()] + nr)
        pos = r.end()
    out.append(tbl[pos:])
    return "".join(out), total


if TABLES:
    out, pos = [], 0
    NOTE_RE = r'(\s*<w:p><w:pPr><w:pStyle w:val="TableNote" />.*?</w:p>)+'
    for m in re.finditer(r"<w:tbl>.*?</w:tbl>", doc, re.S):
        tbl, width = format_table(m.group(0), keep_last=re.match(NOTE_RE, doc[m.end():], re.S) is not None)
        ind = (TEXT_TW - width) // 2
        before = doc[pos:m.start()]
        # the Table Caption paragraph pandoc puts right before the table
        k = before.rfind('<w:pStyle w:val="TableCaption" />')
        if k != -1:
            before = before[:k] + f'<w:pStyle w:val="TableCaption" /><w:ind w:left="{ind}" w:right="{ind}" />' + \
                     before[k + len('<w:pStyle w:val="TableCaption" />'):]
        out.append(before + tbl)
        pos = m.end()
        # the Table Note paragraphs right after it
        after = re.match(NOTE_RE, doc[pos:], re.S)
        if after:
            notes = after.group(0).replace('<w:pStyle w:val="TableNote" />',
                                           f'<w:pStyle w:val="TableNote" /><w:keepNext /><w:ind w:left="{ind}" w:right="{ind}" />')
            k = notes.rfind("<w:keepNext />")
            notes = notes[:k] + notes[k + len("<w:keepNext />"):]   # the last note does not bind to the text after it
            out.append(notes)
            pos += after.end()
    out.append(doc[pos:])
    doc = "".join(out)

# --- page setup: Letter, 1" margins, page-number footer. No line numbers: the
# submission system adds its own.
SECT = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdZZFooter1"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
        '<w:cols w:space="720"/></w:sectPr>')
last = doc.rfind("<w:sectPr>")
end = doc.find("</w:sectPr>", last) + len("</w:sectPr>")
assert doc.find("</w:body>", end) != -1, "final sectPr not at end of body"
doc = doc[:last] + SECT + doc[end:]
if 'xmlns:r="' not in doc[:2000]:
    sys.exit("document.xml lacks the r: namespace")
parts["word/document.xml"] = doc.encode("utf8")

# --- open in Word's current mode rather than Compatibility Mode
settings = parts["word/settings.xml"].decode("utf8")
if "<w:compat>" not in settings and "<w:compat " not in settings:
    compat = ('<w:compat><w:compatSetting w:name="compatibilityMode" '
              'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>')
    settings = settings.replace("<w:rsids>", compat + "<w:rsids>", 1) if "<w:rsids>" in settings \
        else settings.replace("<w:themeFontLang", compat + "<w:themeFontLang", 1)
    parts["word/settings.xml"] = settings.encode("utf8")

# --- footer with centred page number
parts["word/footer1.xml"] = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
    + (f'<w:r><w:t xml:space="preserve">{PAGE_PREFIX}</w:t></w:r>' if PAGE_PREFIX else '') +
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>').encode("utf8")
rels = parts["word/_rels/document.xml.rels"].decode("utf8")
rels = rels.replace("</Relationships>",
                    '<Relationship Id="rIdZZFooter1" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
                    'Target="footer1.xml"/></Relationships>')
parts["word/_rels/document.xml.rels"] = rels.encode("utf8")
ct = parts["[Content_Types].xml"].decode("utf8")
if 'Extension="png"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
ct = ct.replace("</Types>",
                '<Override PartName="/word/footer1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>')
parts["[Content_Types].xml"] = ct.encode("utf8")

with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    if "[Content_Types].xml" in parts:  # keep it first, as Word expects
        z.writestr("[Content_Types].xml", parts.pop("[Content_Types].xml"))
    for n, data in parts.items():
        z.writestr(n, data)
print("wrote", dst, "equations numbered:", len(eqnums))
