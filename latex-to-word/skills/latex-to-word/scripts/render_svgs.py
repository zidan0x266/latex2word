"""Convert vector figure PDFs to SVG for Word (text converted to outlines).

PDFs whose content is mainly an embedded bitmap are skipped; their PNG stays as is.
Needs PyMuPDF (pip install pymupdf). usage: python render_svgs.py BUILD_DIR STEM
"""
import json, os, re, sys
import pymupdf

build, stem = sys.argv[1:3]
src = open(os.path.join(build, stem + ".tex"), encoding="utf8").read()
src = "\n".join(re.sub(r"(?<!\\)%.*", "", l) for l in src.split("\n"))
gp = re.search(r"\\graphicspath\{\{([^}]*)\}", src)
gdir = os.path.join(build, gp.group(1) if gp else "")
names = list(dict.fromkeys(os.path.splitext(os.path.basename(n))[0]
                           for n in re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\{([^}]+)\}", src)))
os.makedirs(os.path.join(build, "svg"), exist_ok=True)
report = {}
for n in names:
    page = pymupdf.open(os.path.join(gdir, n + ".pdf"))[0]
    area = page.rect.width * page.rect.height
    img_area = sum(r.width * r.height for img in page.get_images(full=True) for r in page.get_image_rects(img[0]))
    if img_area > 0.25 * area:
        report[n] = f"skipped: bitmap covers {img_area / area:.0%} of the page"
        continue
    svg = page.get_svg_image(text_as_path=True)
    with open(os.path.join(build, "svg", n + ".svg"), "w", encoding="utf8") as f:
        f.write(svg)
    report[n] = f"svg {len(svg) // 1024} KB" + (f" (contains small bitmaps, {img_area / area:.0%})" if img_area else "")
json.dump(report, open(os.path.join(build, "svg", "report.json"), "w"), indent=1)
for k, v in report.items():
    print(f"{k:16s} {v}")
