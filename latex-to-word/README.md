# latex-to-word (Claude Code plugin)

A skill that has Claude Code turn an **Elsevier `elsarticle`** or **ACS `achemso`** LaTeX
manuscript (or its Supporting Information) into a **submission-ready Word file** and check it
carefully against the compiled PDF.

## What you get
- **`main.docx`**:
  - **Text:** identical to the PDF, sentence by sentence, with the journal's front matter:
    elsarticle (affiliation letters, corresponding authors, keywords) or achemso (†/‡/¶ marks,
    E-mail line, ACS citation style, S-numbering for an SI).
  - **Equations:** editable Word equations, numbered (1), (2), … at the right margin.
  - **Figures:** vector (SVG, with PNG fallback) at their LaTeX size. Multi-panel figures with
    LaTeX-drawn panel labels are kept as typeset.
  - **Tables (achemso):** booktabs rules, table notes, each table kept on one page.
  - **Citations:** either **live EndNote citations** from a per-paper EndNote library, or static
    numbered citations linked to a reference list.
  - **Layout:** no line numbers (submission systems add their own) and page numbers.
- **A per-paper EndNote library** where record *n* is reference [*n*]. Records come from your own
  EndNote library and DOIs are checked against Crossref/DataCite.
- **`submission_figures/`**: one vector PDF per figure, with fonts converted to outlines and no
  transparency.
- **`marked.docx`** (optional), for a revision: changes since an earlier version, additions
  highlighted and deletions in red strikethrough, with nothing in the margin.
- **Checks:** text, citation numbers, equations, sub-/superscripts, symbols and pictures, compared
  against the PDF.

## Requirements
- pandoc ≥ 3, TeX Live/MacTeX (`latexmk`), Ghostscript, ImageMagick 7, Python 3.
- PyMuPDF and lxml: run `skills/latex-to-word/scripts/setup_env.sh` once.
- For the EndNote and Word-comparison steps: **macOS, EndNote 21 and Microsoft Word**. You make
  a few clicks yourself: creating the empty library, installing the journal style, and
  *Update Citations and Bibliography*. Claude tells you when.

## Install
```zsh
claude plugin marketplace add zidan0x266/latex2word
claude plugin install latex-to-word@latex2word
```
Then run `skills/latex-to-word/scripts/setup_env.sh` once (or ask Claude to set the skill up).

## Use
Open Claude Code in your paper's folder and say, e.g.:
- "Convert main.tex to a Word file for submission, with EndNote citations."
- "Convert our ACS paper and its SI (main.tex, SI.tex) to Word."
- "Make a marked copy comparing the revision with the initial submission."
- "Prepare the figures for upload."

## Limits
- Built and tested on `elsarticle` (Journal of Membrane Science style, EndNote 21, Word for Mac)
  and `achemso` 3.14 (ACS Macro Letters with SI, JACS, Biochemistry). Other document classes need
  a prep script of their own.
- The marked copy (`make_redline.py`) expects elsarticle's "[n]" reference labels.
- It assumes English section names ("References") and US Letter pages.
