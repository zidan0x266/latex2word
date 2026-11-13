---
name: latex-to-word
description: Convert an Elsevier elsarticle or ACS achemso LaTeX manuscript or Supporting Information (main.tex + .bib + figures) into a submission-ready Word .docx with numbered equations, SVG figures, the journal's front matter, booktabs tables, and either live EndNote citations from a dedicated per-paper library or static numbered citations. Also covers DOI verification, a one-PDF-per-figure upload set, an optional marked (redline) copy against an earlier version, and sentence-level checks against the compiled PDF. Use when the user wants a LaTeX paper or SI as a Word/.docx file for journal submission, an EndNote library for a paper, a manuscript with changes marked, or journal-ready figure files. The EndNote and Word steps need macOS with EndNote 21 and Microsoft Word.
---

# LaTeX (elsarticle or achemso) → Word manuscript

Turns an `elsarticle` (Elsevier) or `achemso` (ACS) LaTeX paper into a Word file whose text,
citations, equations and figures match the compiled PDF. Scripts live in `scripts/` next to this
file. Detailed procedures are in `reference/`: read the file for a step before doing it.
`build.sh` picks the pipeline from `\documentclass`. For `achemso`, also read
`reference/achemso.md` before building.

## Ground rules (learned the hard way)

- **Compile and build in a scratch copy** of the paper (`rsync` it to a temp folder). Put only
  final files into the user's folder, which is often cloud-synced (Box, Dropbox).
- **New files go in a `word/` folder inside the paper folder** (the .docx files, submission
  figures, the EndNote library, marked copies), never next to `main.tex`.
- **Before replacing or editing any .docx, check for a Word lock file** (`~$name.docx`). Never
  write a document that is open in Word.
- **Edit saved .docx files surgically**, for example by swapping one image or removing one
  paragraph, instead of regenerating them. Regenerating loses EndNote formatting and the user's
  edits.
- **Keep only the current, correct version of each file.** Don't make backup copies unless the
  user asks; verify changes instead.
- **When the compiled PDF itself is wrong** (a missing package breaks the tables, a template hides
  the SI's section headings, numbering disagrees with the main text), tell the user and ask how
  the Word file should handle it. Don't silently copy the defect or silently fix it. Make agreed
  changes only in the scratch copy, so the PDF used for verification matches the Word file.
- **Never write an EndNote `.enl` or `sdb.eni` file with sqlite.** EndNote-only collations and
  trigger functions would corrupt it. Read-only queries (`file:…?mode=ro`) are fine; make every
  change through EndNote's AppleScript. Ask before changing the user's main (synced) library.
- **Never send the user's email address to an external service**, such as Crossref's `mailto`
  parameter.
- **After copying a large file into a cloud-synced folder, `touch` it.** Finder can otherwise
  keep showing a size it saw mid-write (once exactly 4 MiB for a 15 MB file).
- Tell the user plainly about every manual step: creating an EndNote library, installing a style,
  and the EndNote **Update Citations and Bibliography** click. EndNote's Word add-in can't be
  scripted.

## Setup (once per machine)

`scripts/setup_env.sh` checks for pandoc ≥ 3, TeX Live (latexmk), Ghostscript and ImageMagick 7.
It also creates a Python venv with PyMuPDF and lxml, and prints the
`PYMUPDF_PYTHON=…` line to use. Without PyMuPDF, builds keep PNG figures and say so.
ImageMagick is only needed for the upload figures (flattening transparent bitmaps) and TIFFs;
the build falls back to macOS `sips` for resizing.

## Workflow

### 1. Compile the LaTeX (gives `.aux` / `.bbl`, which hold the numbering)
```zsh
B=$(mktemp -d)/build
rsync -a --exclude .DS_Store "<paper folder>/" "$B/"
(cd "$B" && latexmk -pdf -interaction=nonstopmode main.tex)
```
- Check the log for real errors (`grep '^! ' main.log`), not just latexmk's exit code.
- If latexmk stops early, for example because BibTeX fails on a paper with no `\cite` yet, run
  `pdflatex` (and `bibtex`) by hand until the references settle.
- Compile every document that is to be converted (e.g. `main.tex` and `SI.tex`).

### 2. Build the Word file
```zsh
PYMUPDF_PYTHON=<venv>/bin/python scripts/build.sh "$B" main "$B/main.docx" [cites.json]
```
- Without `cites.json`: citations become static numbers with internal links to a reference list
  rebuilt from the `.bbl`: `[1–3]` for elsarticle, and for achemso the journal's own form
  (superscript after punctuation as natmove places them, or round `(1)`).
- With `cites.json` (step 3): citations become EndNote placeholders `{Author, Year #Rec}`.
- The prep script checks its section, float and equation numbers against the `.aux` file and
  prints `warnings=N`. It must be 0. For achemso it also prints the class settings it found
  (journal, citation style, headings on/off); check they match the PDF.
- What the build produces:
  - **Layout:** US Letter, Times New Roman 12 pt, 1.5 spacing, page numbers (`S-1` for an achemso
    SI), no line numbers.
  - **Front matter:** elsarticle: authors with affiliation letters, ∗/∗∗ corresponding authors,
    abstract, keywords. achemso: authors with †/‡/¶ marks, ∗ for corresponding authors, the
    E-mail (and Phone/Fax) line, abstract.
  - **Headings and equations:** section numbers typed into Word's built-in Heading styles;
    equations numbered with Word's native `#(n)` form.
  - **Figures:** a 300 dpi PNG with an SVG for vector figures, captioned "Figure N:". achemso
    multi-panel or TikZ figures are typeset as in the manuscript and rendered as one picture, so
    LaTeX-drawn panel labels are kept; schemes and charts are captioned "Scheme N:", "Chart N:".
  - **Tables (achemso):** booktabs rules, columns sized to content, `threeparttable` notes
    below, each table kept on one page with its notes.
  - **Chemistry and cross-references:** `\ce{}` and `La$^{3+}$`-style chemistry as real
    sub/superscripts; cross-references resolved from the `.aux`.
- Not included: elsarticle's Graphical Abstract and Highlights, achemso's TOC graphic. They are
  separate upload items.

### 3. EndNote citations (when the user wants live citations), see `reference/endnote.md`
1. The user creates an **empty library** in EndNote (File › New) in the paper folder.
2. `scripts/build_enxml.py` collects every cited reference in citation order. It takes the user's
   own records (matched by DOI, then title) where they exist, and builds the rest from the .bib.
   Import with `scripts/en_import.applescript`, then check in the database that record *n* is
   reference [*n*].
3. `scripts/verify_doi.py` checks every DOI against Crossref or DataCite and searches for missing
   ones. Fix records with `en_setfield.applescript`, or `en_setrecord.applescript` when the type
   must change.
4. Build with `cites.json`. The user installs the journal's output style and clicks **Update
   Citations and Bibliography**. Then run `scripts/tidy_docx.py`, which removes the blank line
   EndNote leaves under "References".
5. After any author or year change in the library, run `scripts/sync_cites.py` before
   rebuilding. Placeholders must match on author, year and record number.

### 4. Submission figures, see `reference/figures.md`
`scripts/make_submission_figs.py <pandoc.tex> <figure dir> submission_figures/ [graphical_abstract.pdf]`
writes one vector PDF per figure, laid out as in the manuscript. It converts Type 3 fonts to
outlines, flattens transparent bitmaps losslessly, and stays under Elsevier's ~7 MB per figure.
Use PDF, not EPS: most matplotlib figures use transparency, which EPS can't store. For achemso,
the figure dir is the build folder (`$B`), which holds one PDF per float.

### 5. Verify (always, before calling the work done), see `reference/verification.md`
- elsarticle: `scripts/compare_docx_pdf.py main.docx main.pdf` and
  `scripts/check_scripts.py main.docx main.pdf`.
- achemso: `scripts/compare_achemso.py` and `scripts/check_scripts_achemso.py` (same arguments).
- Both compare the text and captions word by word, citations, equation numbers and the reference
  list entry by entry, then every sub-/superscript and every non-ASCII symbol.
- `scripts/check_equations.py main.tex main.docx`: the symbols of every display equation against
  its LaTeX.
- Export a copy through Word to PDF and confirm it uses only Times New Roman and Cambria Math,
  with no fallback fonts. Look at the pages with the most scripts, symbols and tables.
- Explain every remaining difference to the user. The usual causes are known artefacts of reading
  the PDF; the reference file lists them.

### 6. Marked copy for a revision (optional), see `reference/redline.md`
Run Word Compare (original vs. revised, by AppleScript), then `scripts/make_redline.py`. The
result has additions highlighted and deletions in red strikethrough, as plain formatting: no
tracked changes and nothing in the margin. The reference list is rebuilt per reference. Both
inputs must be EndNote-updated from the same library state, and unchanged figures must be
byte-identical images. Verify that the redline without its deletions equals the revised file,
that without its additions it equals the original, and that the pictures are identical.

## Limitations

- Built for `elsarticle` and `achemso`. Other classes need a prep script of their own; the
  achemso one (`prep_achemso.py`) shows the parts that change: front matter, headings,
  citations and the reference list.
- English section name "References" and US Letter page size are assumed.
- Display equations come out as Word equations. Very unusual LaTeX math may need checking by eye.
- `make_redline.py` expects elsarticle's "[n]" reference labels.
