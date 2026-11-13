"""One file per figure for journal upload: Figure_N.pdf (vector, panels laid out as in the
manuscript). Text set in Type 3 fonts (matplotlib's default) is converted to outlines with
Ghostscript, since preflight checks often flag Type 3 fonts; PDF rather than EPS because
most figures use transparency, which EPS cannot hold. Embedded bitmaps with soft masks (alpha)
are flattened onto white, losslessly, keeping vector labels. Optional: --tiff also writes a 600 dpi
LZW TIFF for bitmap figures; --svg also writes Figure_N.svg.

Layout (rows, panel widths) is read from the prep.py output, so it matches the Word file.
usage: python make_submission_figs.py PANDOC_TEX FIGURE_DIR OUT_DIR [GRAPHICAL_ABSTRACT.pdf] [--svg] [--tiff]
needs PyMuPDF; uses Ghostscript (gs) and ImageMagick (magick)
"""
import os, re, subprocess, sys, tempfile
import pymupdf

args = [a for a in sys.argv[1:] if a not in ("--svg", "--tiff")]
want_svg = "--svg" in sys.argv
want_tiff = "--tiff" in sys.argv
tex, figdir, out = args[:3]
ga = args[3] if len(args) > 3 else None
os.makedirs(out, exist_ok=True)
src = open(tex, encoding="utf8").read()
TIFF_DPI = 600


def is_bitmap(page):
    area = page.rect.width * page.rect.height
    covered = sum(r.width * r.height for img in page.get_images(full=True) for r in page.get_image_rects(img[0]))
    return covered > 0.25 * area


def open_flat(path):
    """Open a panel PDF; images with a soft mask are composited onto white (lossless).

    The image data is overwritten in place (same object, same colour space), and the mask is
    dropped; PyMuPDF's replace_image would keep a second copy of every image."""
    doc = pymupdf.open(path)
    done = set()
    for page in doc:
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            if not smask or xref in done:
                continue
            rgba = pymupdf.Pixmap(pymupdf.Pixmap(doc, xref), pymupdf.Pixmap(doc, smask))
            with tempfile.TemporaryDirectory() as tmp:
                a, b = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
                rgba.save(a)
                subprocess.run(["magick", a, "-background", "white", "-alpha", "remove", "-alpha", "off",
                                "-type", "TrueColor", b], check=True)
                flat = pymupdf.Pixmap(b)
            assert (flat.width, flat.height, flat.n, flat.alpha) == (img[2], img[3], 3, 0), "unexpected pixmap"
            doc.update_stream(xref, flat.samples)  # deflated, /Filter /FlateDecode
            doc.xref_set_key(xref, "SMask", "null")
            doc.xref_set_key(xref, "DecodeParms", "null")
            done.add(xref)
    return pymupdf.open("pdf", doc.tobytes(garbage=4, deflate=True))


def write_outputs(doc, stem, bitmap):
    pdf = os.path.join(out, stem + ".pdf")
    page = doc[0]
    type3 = any(f[2] == "Type3" for f in page.get_fonts(full=True))
    if type3:
        tmp = os.path.join(out, stem + "_type3.pdf")
        doc.save(tmp, garbage=4, deflate=True)
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dNoOutputFonts",
                        "-dCompatibilityLevel=1.5", f"-sOutputFile={pdf}", tmp], check=True)
        os.remove(tmp)
    else:
        doc.save(pdf, garbage=4, deflate=True)
    made = [stem + ".pdf" + (" (text outlined)" if type3 else "")]
    if want_svg:
        with open(os.path.join(out, stem + ".svg"), "w", encoding="utf8") as f:
            f.write(page.get_svg_image(text_as_path=True))
        made.append(stem + ".svg")
    if bitmap and want_tiff:
        png = os.path.join(out, stem + "_tmp.png")
        page.get_pixmap(dpi=TIFF_DPI, alpha=False).save(png)  # composited on white: no transparency
        tif = os.path.join(out, stem + ".tif")
        subprocess.run(["magick", png, "-units", "PixelsPerInch", "-density", str(TIFF_DPI),
                        "-compress", "LZW", tif], check=True)
        os.remove(png)
        made.append(stem + ".tif")
    w, h = page.rect.width / 72, page.rect.height / 72
    print(f"{stem:20s} {w:.2f} x {h:.2f} in ({w * 25.4:.0f} mm wide)  {', '.join(made)}")


figures = re.findall(r"\\begin\{figure\}(.*?)\\end\{figure\}", src, re.S)
for n, body in enumerate(figures, 1):
    rows = []
    for line in body.split("\\\\"):
        row = [(nm, float(wd)) for wd, nm in re.findall(r"\\includegraphics\[width=([\d.]+)in\]\{png/([^}]+)\.png\}", line)]
        if row:
            rows.append(row)
    placed, width, y, bitmap = [], 0.0, 0.0, False
    for row in rows:
        x, row_h, items = 0.0, 0.0, []
        for name, w_in in row:
            p = open_flat(os.path.join(figdir, name + ".pdf"))[0]
            bitmap |= is_bitmap(p)
            w = w_in * 72
            h = w * p.rect.height / p.rect.width
            items.append((name, x, w, h)); x += w; row_h = max(row_h, h)
        placed.append((items, x, y)); width = max(width, x); y += row_h
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=y)
    for items, row_w, row_y in placed:
        off = (width - row_w) / 2  # rows are centred, as in the manuscript
        for name, x, w, h in items:
            with open_flat(os.path.join(figdir, name + ".pdf")) as panel:
                page.show_pdf_page(pymupdf.Rect(off + x, row_y, off + x + w, row_y + h), panel, 0)
    write_outputs(doc, f"Figure_{n}", bitmap)

if ga:
    with pymupdf.open(ga) as g:
        doc = pymupdf.open(); doc.insert_pdf(g, from_page=0, to_page=0)
        write_outputs(doc, "Graphical_abstract", is_bitmap(doc[0]))
