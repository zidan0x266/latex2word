---
name: latex-to-word
description: Convert a LaTeX manuscript or Supporting Information (main.tex + .bib + figures) into a submission-ready Word .docx with numbered equations, SVG figures, the journal's front matter, tables, and either live EndNote citations from a dedicated per-paper library or static numbered citations. Ready-made pipelines for Elsevier elsarticle and ACS achemso; any other class or unusual construct is adapted on the spot. Also covers DOI verification, a one-PDF-per-figure upload set, an optional marked (redline) copy against an earlier version, and sentence-level checks against the compiled PDF. Use when the user wants a LaTeX paper or SI as a Word/.docx file for journal submission, an EndNote library for a paper, a manuscript with changes marked, or journal-ready figure files. The EndNote and Word steps need macOS with EndNote 21 and Microsoft Word.
---

# LaTeX → Word manuscript

Turns a LaTeX paper into a Word file whose text, citations, equations and figures match the
compiled PDF. Scripts live in `scripts/` next to this file. Detailed procedures are in
`reference/`: read the file for a step before doing it.
`build.sh` picks the pipeline from `\documentclass`: `achemso` (ACS; also read
`reference/achemso.md` before building) or `elsarticle` (Elsevier). For anything else, or anything
the scripts don't handle, see **When something is unusual** at the end: adapt the pipeline, don't
stop at it.

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
- Compile every document that is to be converted (e.g. `main.tex` and `SI.tex`). An SI kept in a
  subfolder (`esi/esi.tex`) is compiled and built in that subfolder, as Overleaf compiles it.

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
  - **Tables (achemso):** the rules as LaTeX draws them (booktabs, `\hline`, `\cline`), columns
    sized to their content and the table's `\tabcolsep`, `threeparttable` notes or a plain note
    below, each table kept on one page with its caption and notes.
  - **Chemistry and cross-references:** `\ce{}` and `La$^{3+}$`-style chemistry as real
    sub/superscripts; cross-references and `\citeauthor` names resolved from the `.aux`.
  - **TOC entry (achemso):** where the PDF prints it (usually a page of its own at the end), under
    its heading (`\tocentryname`) and framed at the journal's size, as one picture.
- Not included: elsarticle's Graphical Abstract and Highlights. They are separate upload items.

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

## When something is unusual

The scripts encode what has been met so far; papers vary. Treat them as a starting point you are
expected to extend, and fix whatever the paper needs. The compiled PDF stays the reference, and
the verification steps decide when the work is done.

- **Work on copies.** Copy the scripts into the build folder and change them there. An installed
  skill may be read-only, and a plugin update would overwrite edits. If a fix is general, offer to
  add it to the skill.
- **Another document class** (revtex, rsc, Wiley, IEEEtran, plain `article`, …): `build.sh` would
  fall back to the elsarticle pipeline, so don't run it unchanged. Write a prep script for the
  class, starting from the closer of `prep.py` and `prep_achemso.py`.
  - Usually only these change: the front matter, headings, the citation style and the
    reference-list format.
  - Figures, tables, equations, `post.py`, `elsarticle.lua` and the checks carry over.
  - Find out what the class really prints by reading the PDF, the `.cls`/config files, or a TeX
    probe of the preamble, as `prep_achemso.py` does. Don't guess from the source.
- **A construct the scripts don't handle**, for example:
  - a new float type, `align`/`gather`, `\citet`/`\citeyear`, footnotes;
  - macros the regexes miss, or a package that changes captions or numbering.
  Extend the prep script, or rewrite that part of the scratch `.tex` into a form the pipeline
  handles. Check that the compiled PDF is unchanged, then rebuild.
- **Other assumptions to adjust when they don't hold:**
  - the "References" heading (other languages, "Notes and References");
  - US Letter pages (set the A4 size in `post.py`'s `sectPr`);
  - Times New Roman 12 pt (`mkref.py`);
  - the "[n]" labels `make_redline.py` matches.
- **Figures that render oddly** (huge bitmaps, transparency, fonts missing in the SVG, panels
  placed by `\llap` or `picture`): typeset the float alone at the text width and crop it, as
  `render_figs_achemso.py` does. That renders whatever LaTeX draws. For another class, extend its
  `ACS_ONLY` list with the class's own preamble commands, which the plain `article` class lacks.
- **Math pandoc can't convert** (`\substack`, unusual environments, custom operators): simplify a
  copy of the expression to an equivalent pandoc reads, and check it with `check_equations.py`.
- **Warnings are work items.** `warnings=N` must reach 0. Every difference the checks report must
  be fixed or explained; extend the checks when the layout differs, as `compare_achemso.py` does
  for achemso.
- **Ask the user** only about decisions the PDF can't settle (see the ground rules). Then report
  what you adapted, and why.
