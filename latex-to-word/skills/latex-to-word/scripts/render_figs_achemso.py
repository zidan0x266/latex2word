"""Render every picture float (figure, scheme, chart, graph) of an achemso STEM.tex for Word:
one picture per float, in document order.

- A float with a single \\includegraphics (no TikZ, no subfigure) uses that file: a PDF is rendered
  at 300 dpi (plus an SVG with text as outlines), a raster file is copied unchanged.
- Any other float (subfigure panels, TikZ overlay labels, chemfig, ...) is typeset on its own page
  at the paper's text width with the manuscript's preamble, exactly as in the manuscript, cropped
  to its ink and rendered from that PDF, so labels drawn by LaTeX end up inside the picture.

Writes png/<STEM>_figN.png, svg/<STEM>_figN.svg (vector, needs PyMuPDF), <STEM>_figN.pdf (one PDF
per float for make_submission_figs.py: the cropped page, the source PDF, or a raster file wrapped
losslessly) and png/<STEM>_figs.json [{"name", "width_in", "kind"}]; width_in is the size the
float has in the PDF, capped at the text width. usage: python render_figs_achemso.py BUILD_DIR STEM   (gs, pdflatex, pdfcrop; macOS sips)
"""
import json, os, re, shutil, struct, subprocess, sys

try:
    import pymupdf
except ImportError:
    pymupdf = None

build, stem = sys.argv[1:3]
DPI, MAXPX = 300, 2400
FLOATS = r"\\begin\{(figure|scheme|chart|graph)\*?\}(?:\[[^\]]*\])?(.*?)\\end\{\1\*?\}"
# achemso-only preamble commands: undefined in the standalone article class
ACS_ONLY = ("author", "affiliation", "alsoaffiliation", "altaffiliation", "email", "phone", "fax", "title",
            "keywords", "abbreviations", "date")


def strip_comments(src):
    """as prep.py: a comment-only line produces nothing, not even a blank line (= paragraph break)"""
    out = []
    for line in src.split("\n"):
        m = re.search(r"(?<!\\)%", line)
        if m is None:
            out.append(line + "\n")
        elif line[:m.start()].strip():
            out.append(line[:m.start()])
    return "".join(out)


def group(s, i):
    """s[i] == '{' -> (content, index after the matching '}'), as in prep.py"""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError("unbalanced braces near: " + s[i:i + 60])


def drop_command(t, name):
    """remove \\name[opt]{arg} (one argument) everywhere"""
    out, pos = [], 0
    for m in re.finditer(r"\\%s(?![A-Za-z])\s*(\[[^\]]*\])?\s*" % name, t):
        if m.start() < pos or m.end() >= len(t) or t[m.end()] != "{":
            continue
        _, end = group(t, m.end())
        out.append(t[pos:m.start()])
        pos = end
    out.append(t[pos:])
    return "".join(out)


src = strip_comments(open(os.path.join(build, stem + ".tex"), encoding="utf8").read())
pre = src.split("\\begin{document}", 1)[0]
gp = re.search(r"\\graphicspath\{\{([^}]*)\}", pre)
gdir = gp.group(1) if gp else ""
log = open(os.path.join(build, "pdflatex_figs.log"), "a")
tw = re.search(r"\\textwidth=([\d.]+)pt", open(os.path.join(build, stem + ".log"), errors="replace").read())
TEXTWIDTH_PT = float(tw.group(1)) if tw else 469.75539
TEXTWIDTH_IN = TEXTWIDTH_PT / 72.27
os.makedirs(os.path.join(build, "png"), exist_ok=True)
os.makedirs(os.path.join(build, "svg"), exist_ok=True)

# the manuscript preamble for the standalone pages, plus the packages achemso itself loads
sa_pre = re.sub(r"\\documentclass\s*(\[[^\]]*\])?\s*\{[^}]*\}", "", pre)
for name in ACS_ONLY:
    sa_pre = drop_command(sa_pre, name)
sa_pre = re.sub(r"\\Section(s|Numbers)(On|Off)(?![A-Za-z])", "", sa_pre)
m = re.search(r"\\setkeys\{acs\}\s*\{", sa_pre)
while m:
    _, end = group(sa_pre, m.end() - 1)
    sa_pre = sa_pre[:m.start()] + sa_pre[end:]
    m = re.search(r"\\setkeys\{acs\}\s*\{", sa_pre)
loaded = " ".join(re.findall(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", pre))
achemso_pkgs = ",".join(p for p in ("graphicx", "caption", "float", "url") if not re.search(r"\b%s\b" % p, loaded))
STANDALONE = r"""\documentclass[12pt]{article}
%s
%s
\usepackage[paperwidth=8.5in,paperheight=22in,textwidth=%.5fpt,textheight=20in]{geometry}
\pagestyle{empty}
\begin{document}
\begin{figure}[p]%s\end{figure}
\end{document}
"""


def resolve(name):
    """The file LaTeX finds: the path as given first, then under \\graphicspath."""
    for base in (build, os.path.join(build, gdir)):
        for ext in ("", ".pdf", ".png", ".jpg", ".jpeg"):
            p = os.path.join(base, name + ext)
            if os.path.isfile(p):
                return p
    sys.exit(f"figure file not found: {name}")


def width_in(opts, natural):
    sc = re.search(r"scale\s*=\s*([\d.]+)", opts)
    wd = re.search(r"width\s*=\s*([\d.]*)\\(textwidth|linewidth|columnwidth)", opts)
    wabs = re.search(r"width\s*=\s*([\d.]+)\s*(cm|mm|in|pt)", opts)
    if sc:
        return natural * float(sc.group(1))
    if wd:
        return TEXTWIDTH_IN * float(wd.group(1) or 1)
    if wabs:
        return float(wabs.group(1)) / {"cm": 2.54, "mm": 25.4, "in": 1, "pt": 72.27}[wabs.group(2)]
    return min(natural, TEXTWIDTH_IN)


def png_px(path):
    with open(path, "rb") as f:
        return struct.unpack(">II", f.read(24)[16:24])


def gs_png(pdf, png):
    """300 dpi render; returns the page width in inches"""
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m", f"-r{DPI}",
                    "-dUseCropBox", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                    "-dFirstPage=1", "-dLastPage=1", f"-sOutputFile={png}", pdf], check=True)
    return png_px(png)[0] / DPI


def svg_from(pdf, out):
    if pymupdf is None:
        return "no PyMuPDF: PNG only"
    page = pymupdf.open(pdf)[0]
    area = page.rect.width * page.rect.height
    img_area = sum(r.width * r.height for img in page.get_images(full=True) for r in page.get_image_rects(img[0]))
    if img_area > 0.25 * area:
        return f"bitmap covers {img_area / area:.0%}: PNG only"
    open(out, "w", encoding="utf8").write(page.get_svg_image(text_as_path=True))
    return "svg"


figs = []
for n, m in enumerate(re.finditer(FLOATS, src, re.S), 1):
    env = m.group(2)
    c = re.search(r"\\caption(?![A-Za-z])\s*(\[[^\]]*\])?\s*", env)
    body = env
    if c:
        _, cend = group(env, c.end())
        body = env[:c.start()] + env[cend:]
    body = re.sub(r"\\label\{[^}]+\}", "", body)
    incs = re.findall(r"\\includegraphics\s*(?:\[([^\]]*)\])?\{([^}]+)\}", body)
    name = f"{stem}_fig{n}"
    png, svg = os.path.join(build, "png", name + ".png"), os.path.join(build, "svg", name + ".svg")
    if len(incs) == 1 and not re.search(r"tikzpicture|subfigure|subfloat|minipage", body):
        opts, f = incs[0]
        path = resolve(f)
        if path.lower().endswith(".pdf"):
            w = width_in(opts, gs_png(path, png))
            kind = "pdf, " + svg_from(path, svg)
            shutil.copyfile(path, os.path.join(build, name + ".pdf"))
        else:
            if path.lower().endswith(".png"):
                shutil.copyfile(path, png)
            else:   # JPEG: Word takes PNG here like every other picture
                subprocess.run(["sips", "-s", "format", "png", path, "--out", png], stdout=subprocess.DEVNULL, check=True)
            w = width_in(opts, png_px(png)[0] / DPI)
            kind = "raster file"
            if pymupdf is not None:   # PDF wrapper (Flate, lossless) at the size the float has
                px, py = png_px(png)
                doc = pymupdf.open()
                doc.new_page(width=w * 72, height=w * 72 * py / px).insert_image(
                    pymupdf.Rect(0, 0, w * 72, w * 72 * py / px), filename=png)
                doc.save(os.path.join(build, name + ".pdf"), deflate=True)
    else:
        tex = os.path.join(build, name + "_standalone.tex")
        open(tex, "w", encoding="utf8").write(STANDALONE % (
            "\\usepackage{%s}" % achemso_pkgs if achemso_pkgs else "", sa_pre, TEXTWIDTH_PT, body))
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", os.path.basename(tex)],
                           cwd=build, stdout=log, stderr=log)
        if r.returncode:
            sys.exit(f"standalone page for {m.group(1)} {n} failed: see {tex[:-4]}.log")
        crop = os.path.join(build, name + ".pdf")
        subprocess.run(["pdfcrop", "--margins", "0", tex[:-4] + ".pdf", crop], stdout=log, stderr=log, check=True)
        typeset = gs_png(crop, png)
        w = min(typeset, TEXTWIDTH_IN)
        kind = f"composite ({len(incs)} files, {typeset:.2f} in wide as typeset), " + svg_from(crop, svg)
    px, _ = png_px(png)
    if px > MAXPX:  # keep the .docx small: no picture needs more than ~2400 px across
        if shutil.which("magick"):
            subprocess.run(["magick", png, "-resize", f"{MAXPX}x", png], check=True)
        else:
            subprocess.run(["sips", "--resampleWidth", str(MAXPX), png], stdout=subprocess.DEVNULL, check=True)
        kind += f", downsampled {px} -> {MAXPX} px"
    figs.append({"name": name, "width_in": round(w, 4), "kind": kind})
    print(f"{name:12s} {m.group(1):7s} {w:5.2f} in  {kind}")
json.dump(figs, open(os.path.join(build, "png", stem + "_figs.json"), "w"), indent=1)
