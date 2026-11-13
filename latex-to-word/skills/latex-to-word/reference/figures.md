# Figures

## In the Word file
- `build.sh` renders each figure PDF to a 300 dpi PNG at its LaTeX size (`scale=` × natural
  width). The sizes are checked against the 6.5 in text width.
- With PyMuPDF it also adds an **SVG** (text converted to outlines) the way Word stores an
  inserted SVG: `<a:blip>` keeps the PNG as fallback, plus an `asvg:svgBlip`. Word 2016+ draws the
  SVG.
- PDFs that are mostly bitmap (more than 25% of the page area covered by images) stay PNG only.
  An SVG of them would just wrap the same pixels.
- A PDF can't be embedded as a picture cross-platform (Word for Mac only). That's why the .docx
  uses SVG while the journal gets PDFs.
- To add SVGs to an existing, EndNote-formatted .docx without touching anything else, run
  `scripts/embed_svg.py IN.docx OUT.docx SVG_DIR <figure names in order>`. Map pictures by
  document order, and check against the hashes of the PNGs you rendered.

## Upload files: `scripts/make_submission_figs.py`
- **Layout:** one file per figure, with the panels placed as in the manuscript (rows centred,
  same widths).
- **Format:** **PDF**, which Elsevier accepts alongside EPS, TIFF and JPEG. SVG is not on
  Elsevier's list. Avoid EPS: matplotlib figures usually contain transparency (alpha 0.2–0.8),
  which EPS can't store.
- **Fonts:** matplotlib's default **Type 3** fonts are converted to outlines
  (`gs -sDEVICE=pdfwrite -dNoOutputFonts`), because preflight checks flag Type 3. For new plots,
  set `matplotlib.rcParams['pdf.fonttype'] = 42`.
- **Transparency:** bitmaps with soft masks are flattened onto white **in place**, keeping the
  colour profile and losslessly. Don't use PyMuPDF's `replace_image`: it keeps a second copy of
  every image.
- **Size:** keep each file under about 7 MB.
- `--tiff` writes a 600 dpi LZW TIFF for bitmap figures, and `--svg` writes SVGs. Neither is
  needed when PDF is accepted.

## Diagnosing a bitmap-heavy figure (e.g. exported from OmniGraffle)
Check with PyMuPDF:
- page size;
- each image's pixels, `Filter` (`DCTDecode` means JPEG-compressed) and `SMask` (alpha);
- placed size, giving dpi at print size;
- the ICC profile (sRGB is right, Display P3 would shift colours).

Advice for the author:
- Export the PDF **without image compression** and with a white, non-transparent background.
- Keep the canvas size, so the LaTeX `scale=` still fits.
- For ≥ 500 dpi at a larger print width, re-render the panels at ≥ 2000 px in the visualization
  program.

If a figure is re-exported, the *same figure in a different rendering*, give every Word file the
same new image. Otherwise Word Compare shows it as a changed figure.

## achemso: one picture per float, as typeset
`render_figs_achemso.py` renders every `figure`, `scheme`, `chart` and `graph`. Multi-panel or
TikZ floats (panel labels drawn with `\node[overlay]`) are typeset alone at the text width with
the manuscript preamble, cropped to the ink and used as a single picture. The labels then survive,
which they wouldn't if the panel files were placed side by side. It also writes `STEM_figN.pdf`
for every float, so `make_submission_figs.py $B/STEM_pandoc.tex $B out/` works on achemso papers.
Files are named Figure_N in float order, schemes and charts included, so rename as needed.
Transparent raster figures need ImageMagick there.
