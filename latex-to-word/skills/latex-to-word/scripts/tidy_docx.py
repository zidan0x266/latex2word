"""Repair a saved manuscript .docx in place-safe fashion (writes a new file).

1. Built-in styles that Word renamed on save ("Heading 11", "Normal1", ... caused by an
   earlier reference.docx that flagged them as custom) are merged back into Word's own
   Normal / Heading 1-3 / Body Text / Title / Caption / Bibliography, and every reference
   to them is updated.
2. The empty heading-styled paragraph EndNote leaves between the "References" heading and
   the bibliography is removed.
Everything else, including EndNote fields, is copied unchanged.

usage: python3 tidy_docx.py IN.docx OUT.docx
"""
import re, sys, zipfile

src, dst = sys.argv[1:3]
CANONICAL = {"Normal": "Normal", "BodyText": "Body Text", "Title": "Title", "Heading1": "heading 1",
             "Heading2": "heading 2", "Heading3": "heading 3", "Caption": "caption",
             "Bibliography": "Bibliography"}
STYLE_RE = r'<w:style\b[^>]*w:styleId="%s"[^>]*>.*?</w:style>'

zin = zipfile.ZipFile(src)
parts = {i.filename: zin.read(i.filename) for i in zin.infolist()}
styles = parts["word/styles.xml"].decode("utf8")

renamed = {}
for sid, canon in CANONICAL.items():
    dup = re.search(STYLE_RE % (sid + "1"), styles, re.S)
    if not dup or 'w:customStyle="1"' not in dup.group(0)[:200]:
        continue
    block = dup.group(0)
    own = re.search(STYLE_RE % sid, styles, re.S)
    if own:  # Word created its own built-in: give it our formatting, drop the duplicate
        inner = re.sub(r'^.*?<w:name [^>]*/>', "", block[block.index(">") + 1:-len("</w:style>")], flags=re.S)
        new = re.sub(r'(<w:name [^>]*/>).*(</w:style>)', lambda m: m.group(1) + inner + m.group(2), own.group(0), flags=re.S)
        styles = styles.replace(own.group(0), new).replace(block, "")
    else:  # only the renamed copy exists: rename it back
        new = block.replace(' w:customStyle="1"', "")
        new = new.replace(f'w:styleId="{sid}1"', f'w:styleId="{sid}"', 1)
        new = re.sub(r'<w:name w:val="[^"]*"', f'<w:name w:val="{canon}"', new, count=1)
        styles = styles.replace(block, new)
    renamed[sid + "1"] = sid

def repoint(xml):
    for old, new in renamed.items():
        xml = xml.replace(f'w:val="{old}"', f'w:val="{new}"')
    return xml

parts["word/styles.xml"] = repoint(styles).encode("utf8")
for name in parts:
    if re.match(r"word/(document|footnotes|endnotes|header\d*|footer\d*|comments)\.xml$", name):
        parts[name] = repoint(parts[name].decode("utf8")).encode("utf8")

doc = parts["word/document.xml"].decode("utf8")
heading = re.search(r'<w:p\b(?:(?!<w:p\b).)*?<w:t[^>]*>References</w:t>.*?</w:p>', doc, re.S)
removed = 0
if heading:
    after = re.match(r'<w:p\b[^>]*>\s*<w:pPr>\s*<w:pStyle w:val="Heading\d"/>\s*</w:pPr>\s*</w:p>', doc[heading.end():])
    if after:
        doc = doc[:heading.end()] + doc[heading.end() + after.end():]
        removed = 1
parts["word/document.xml"] = doc.encode("utf8")

with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        zout.writestr(info, parts[info.filename])
print("styles restored:", ", ".join(f"{o}->{n}" for o, n in renamed.items()) or "none",
      "| empty paragraph under References removed:", bool(removed))
