"""Build a pandoc reference.docx with manuscript styles (Times New Roman 12 pt, Elsevier-like headings).

usage: python3 mkref.py default-ref.docx out-ref.docx [--achemso]
  --achemso: ACS front matter (affiliations and E-mail line at body size, centred) and styles for
             booktabs tables (cells, caption above, threeparttable notes below)
"""
import re
import sys
import zipfile

src, dst = sys.argv[1], sys.argv[2]

FONT = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman" />'
BLACK = '<w:color w:val="000000" />'


def sz(halfpts):
    return f'<w:sz w:val="{halfpts}" /><w:szCs w:val="{halfpts}" />'


# Word's own styles must not be flagged customStyle: Word would rename them on save
# ("Heading 11", "Normal1") and they would stop being the built-in Heading 1, Normal, ...
BUILTIN = {"Normal", "BodyText", "Title", "Heading1", "Heading2", "Heading3", "Caption", "Bibliography"}


def pstyle(sid, name, based="Normal", nxt=None, ppr="", rpr="", extra=""):
    nxt = f'<w:next w:val="{nxt}" />' if nxt else ""
    based = f'<w:basedOn w:val="{based}" />' if based else ""
    custom = "" if sid in BUILTIN else ' w:customStyle="1"'
    return (f'<w:style w:type="paragraph"{custom} w:styleId="{sid}">'
            f'<w:name w:val="{name}" />{based}{nxt}{extra}<w:qFormat />'
            f'<w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


BODY_SPACING = '<w:spacing w:before="0" w:after="120" w:line="360" w:lineRule="auto" />'

styles = {
    "Normal": pstyle("Normal", "Normal", based=None,
                     ppr='<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto" />',
                     rpr=FONT + sz(24)),
    "BodyText": pstyle("BodyText", "Body Text", ppr=BODY_SPACING + '<w:jc w:val="both" />',
                       extra='<w:link w:val="BodyTextChar" />'),
    "FirstParagraph": pstyle("FirstParagraph", "First Paragraph", based="BodyText", nxt="BodyText"),
    "Title": pstyle("Title", "Title", nxt="Author",
                    ppr='<w:spacing w:before="240" w:after="240" w:line="276" w:lineRule="auto" /><w:jc w:val="center" />',
                    rpr=sz(34)),
    "Author": pstyle("Author", "Author", nxt="Affiliation",
                     ppr='<w:keepNext /><w:spacing w:before="0" w:after="160" w:line="276" w:lineRule="auto" /><w:jc w:val="center" />'),
    "Affiliation": pstyle("Affiliation", "Affiliation",
                          ppr='<w:spacing w:before="0" w:after="40" /><w:jc w:val="center" />',
                          rpr='<w:i /><w:iCs />' + sz(20)),
    "Correspondence": pstyle("Correspondence", "Correspondence",
                             ppr='<w:spacing w:before="0" w:after="40" />', rpr=sz(20)),
    "Keywords": pstyle("Keywords", "Keywords",
                       ppr='<w:spacing w:before="120" w:after="240" w:line="360" w:lineRule="auto" /><w:jc w:val="left" />'),
    "Heading1": pstyle("Heading1", "heading 1", nxt="FirstParagraph",
                       ppr='<w:keepNext /><w:keepLines /><w:spacing w:before="360" w:after="120" /><w:outlineLvl w:val="0" />',
                       rpr='<w:b /><w:bCs />' + BLACK + sz(24)),
    "Heading2": pstyle("Heading2", "heading 2", nxt="FirstParagraph",
                       ppr='<w:keepNext /><w:keepLines /><w:spacing w:before="240" w:after="120" /><w:outlineLvl w:val="1" />',
                       rpr='<w:i /><w:iCs />' + BLACK + sz(24)),
    "Heading3": pstyle("Heading3", "heading 3", nxt="FirstParagraph",
                       ppr='<w:keepNext /><w:keepLines /><w:spacing w:before="240" w:after="120" /><w:outlineLvl w:val="2" />',
                       rpr='<w:i /><w:iCs />' + BLACK + sz(24)),
    "Caption": pstyle("Caption", "Caption",
                      ppr='<w:suppressLineNumbers /><w:spacing w:before="60" w:after="240" w:line="240" w:lineRule="auto" /><w:jc w:val="both" />',
                      rpr=sz(20)),
    "ImageCaption": pstyle("ImageCaption", "Image Caption", based="Caption"),
    "Figure": pstyle("Figure", "Figure", ppr='<w:suppressLineNumbers /><w:spacing w:before="240" w:after="0" /><w:jc w:val="center" />'),
    "CaptionedFigure": pstyle("CaptionedFigure", "Captioned Figure", based="Figure",
                              ppr='<w:keepNext /><w:suppressLineNumbers /><w:jc w:val="center" />'),
    "Equation": pstyle("Equation", "Equation", based="BodyText", ppr='<w:spacing w:before="120" w:after="120" />'),
    "Bibliography": pstyle("Bibliography", "Bibliography", nxt="Bibliography",
                           ppr='<w:tabs><w:tab w:val="left" w:pos="567" /></w:tabs>'
                               '<w:spacing w:before="0" w:after="80" w:line="240" w:lineRule="auto" />'
                               '<w:ind w:left="567" w:hanging="567" /><w:jc w:val="left" />'),
}
if "--achemso" in sys.argv[3:]:
    styles.update({
        "Affiliation": pstyle("Affiliation", "Affiliation",
                              ppr='<w:spacing w:before="0" w:after="60" w:line="276" w:lineRule="auto" /><w:jc w:val="center" />',
                              rpr='<w:i /><w:iCs />'),
        "Correspondence": pstyle("Correspondence", "Correspondence",
                                 ppr='<w:spacing w:before="120" w:after="240" /><w:jc w:val="center" />'),
        # table cells (pandoc's "Compact"), table captions above the table, threeparttable notes below
        "Compact": pstyle("Compact", "Compact",
                          ppr='<w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto" />', rpr=sz(20)),
        "TableCaption": pstyle("TableCaption", "Table Caption", based="Caption",
                               ppr='<w:keepNext /><w:keepLines /><w:spacing w:before="240" w:after="60" w:line="240" w:lineRule="auto" /><w:jc w:val="both" />'),
        "TableNote": pstyle("TableNote", "Table Note",
                            ppr='<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto" /><w:jc w:val="left" />',
                            rpr=sz(18)),
        "TableFootnote": pstyle("TableFootnote", "Table Footnote", based="TableNote",
                                ppr='<w:spacing w:before="60" w:after="0" w:line="240" w:lineRule="auto" /><w:jc w:val="center" />'),
        "TOCGraphic": pstyle("TOCGraphic", "TOC Graphic", based="Figure",
                             ppr='<w:suppressLineNumbers /><w:spacing w:before="120" w:after="0" w:line="240" w:lineRule="auto" /><w:jc w:val="center" />'),
    })

with zipfile.ZipFile(src) as zin:
    items = {n: zin.read(n) for n in zin.namelist()}

xml = items["word/styles.xml"].decode("utf8")

# Default run font: Times New Roman everywhere (incl. East Asian / complex script).
xml = re.sub(r'<w:rFonts w:asciiTheme="minorHAnsi"[^>]*/>', FONT, xml, count=1)
xml = re.sub(r'(<w:pPrDefault>\s*<w:pPr>\s*)<w:spacing w:after="200" />', r'\1<w:spacing w:after="0" />', xml)

for sid, new in styles.items():
    pat = re.compile(r'<w:style [^>]*w:styleId="%s"[^>]*>.*?</w:style>' % sid, re.S)
    if pat.search(xml):
        xml = pat.sub(lambda m: new, xml, count=1)
    else:
        xml = xml.replace("</w:styles>", new + "</w:styles>")

# Heading character styles: drop theme colours/fonts so linked chars match the paragraph styles.
for n in (1, 2, 3):
    pat = re.compile(r'(<w:style [^>]*w:styleId="Heading%dChar"[^>]*>.*?<w:rPr>).*?(</w:rPr>)' % n, re.S)
    xml = pat.sub(lambda m: m.group(1) + BLACK + m.group(2), xml, count=1)

items["word/styles.xml"] = xml.encode("utf8")

with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
    for n, data in items.items():
        zout.writestr(n, data)
print("wrote", dst)
