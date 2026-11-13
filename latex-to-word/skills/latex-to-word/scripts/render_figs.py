"""Render every figure PDF referenced by STEM.tex to PNG (300 dpi) for Word.

Natural widths (inches) are written to png/natural_widths.json before any downscaling,
so very large renders can be shrunk without changing their size on the page.
usage: python3 render_figs.py BUILD_DIR STEM
"""
import json, os, re, struct, subprocess, sys

build, stem = sys.argv[1:3]
DPI, MAXPX = 300, 2400
src = open(os.path.join(build, stem + ".tex"), encoding="utf8").read()
src = "\n".join(re.sub(r"(?<!\\)%.*", "", l) for l in src.split("\n"))
gp = re.search(r"\\graphicspath\{\{([^}]*)\}", src)
gdir = os.path.join(build, gp.group(1) if gp else "")
names = re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\{([^}]+)\}", src)
os.makedirs(os.path.join(build, "png"), exist_ok=True)
widths = {}
for n in dict.fromkeys(names):
    base = os.path.splitext(os.path.basename(n))[0]
    pdf = os.path.join(gdir, n if n.endswith(".pdf") else n + ".pdf")
    png = os.path.join(build, "png", base + ".png")
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m", f"-r{DPI}",
                    "-dUseCropBox", "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                    "-dFirstPage=1", "-dLastPage=1", f"-sOutputFile={png}", pdf], check=True)
    with open(png, "rb") as f:
        w, h = struct.unpack(">II", f.read(24)[16:24])
    widths[base] = w / DPI
    if w > MAXPX:
        subprocess.run(["magick", png, "-resize", f"{MAXPX}x", png], check=True)
    print(base, w, h)
json.dump(widths, open(os.path.join(build, "png", "natural_widths.json"), "w"), indent=1)
