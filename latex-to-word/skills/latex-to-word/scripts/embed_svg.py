"""Give the pictures in an existing .docx an SVG version, as Word does when an SVG is inserted.

Each picture keeps its PNG (the fallback older Word versions show) and gains an svgBlip that
current Word renders. Pictures are matched to figures by document order. Everything else in
the package (EndNote fields, edits) is copied unchanged.

usage: python3 embed_svg.py IN.docx OUT.docx SVG_DIR NAME [NAME ...]
  NAME: figure base name for each picture, in document order ("-" = leave as PNG)
"""
import os, re, sys, zipfile

src, dst, svgdir, names = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
SVG_EXT = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"

zin = zipfile.ZipFile(src)
parts = {i.filename: zin.read(i.filename) for i in zin.infolist()}
doc = parts["word/document.xml"].decode("utf8")
rels = parts["word/_rels/document.xml.rels"].decode("utf8")
if "svgBlip" in doc:
    sys.exit("document already contains SVG pictures")

blips = list(re.finditer(r"<a:blip\b[^>]*?(/>|>.*?</a:blip>)", doc, re.S))
if len(blips) != len(names):
    sys.exit(f"{len(blips)} pictures in document but {len(names)} names given")

new_rels, out, pos, n_svg = [], [], 0, 0
for i, (m, name) in enumerate(zip(blips, names)):
    blip = m.group(0)
    svg_path = os.path.join(svgdir, name + ".svg")
    if name != "-" and os.path.exists(svg_path):
        n_svg += 1
        rid, target = f"rIdSvg{i + 1}", f"media/{name}.svg"
        parts["word/" + target] = open(svg_path, "rb").read()
        new_rels.append(f'<Relationship Id="{rid}" Type="{REL_IMAGE}" Target="{target}"/>')
        ext = (f'<a:ext uri="{SVG_EXT}"><asvg:svgBlip '
               f'xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main" r:embed="{rid}"/></a:ext>')
        if blip.endswith("/>"):
            blip = blip[:-2] + "><a:extLst>" + ext + "</a:extLst></a:blip>"
        elif "<a:extLst>" in blip:
            blip = blip.replace("</a:extLst>", ext + "</a:extLst>", 1)
        else:
            blip = blip.replace("</a:blip>", "<a:extLst>" + ext + "</a:extLst></a:blip>", 1)
    out.append(doc[pos:m.start()] + blip)
    pos = m.end()
out.append(doc[pos:])
parts["word/document.xml"] = "".join(out).encode("utf8")
parts["word/_rels/document.xml.rels"] = rels.replace("</Relationships>", "".join(new_rels) + "</Relationships>").encode("utf8")
ct = parts["[Content_Types].xml"].decode("utf8")
if 'Extension="svg"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="svg" ContentType="image/svg+xml"/><Default ', 1)
parts["[Content_Types].xml"] = ct.encode("utf8")

with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        zout.writestr(info, parts.pop(info.filename))
    for name, data in parts.items():  # the new SVG parts
        zout.writestr(name, data)
print(f"wrote {dst}: {n_svg} of {len(names)} pictures now SVG")
