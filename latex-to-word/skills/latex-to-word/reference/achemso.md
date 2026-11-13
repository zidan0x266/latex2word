# achemso (ACS) manuscripts and Supporting Information

`build.sh` switches to the achemso pipeline when the `.tex` uses `\documentclass[...]{achemso}`:
`render_figs_achemso.py` → `mkref.py --achemso` → `prep_achemso.py` → pandoc with
`elsarticle.lua` → `post.py` with the options `prep_achemso.py` writes to `STEM_post.opts`.
Tested with achemso 3.14 (2025): ACS Macro Letters (letter and SI), JACS (article and
`suppinfo`) and Biochemistry (round citations).

## Class settings come from TeX, not from the source
achemso decides headings, citation style and labels in three layers: class defaults, the journal's
`achemso-<journal>.cfg`, then the preamble. Many `.cfg` files use TeX conditionals (`\ifx
\acs@manuscript\acs@manuscript@communication … \fi`, `\expandafter\endinput`), and achemso
resets keys such as `super=` given in `\documentclass[...]`, which then have no effect. So
`prep_achemso.py` compiles a **probe** (`STEM_acsprobe.tex`: the preamble plus `\typeout`s) and
reads the effective values:

| Setting | Where it shows in the PDF | What the Word file does |
|---|---|---|
| `\SectionsOff` (e.g. all ACS Letters journals, JACS communications, `manuscript=note`) | No section headings at all; achemso logs "(Sub)section … ignored" | Headings dropped. Abstract, Acknowledgement, "Supporting Information Available" and References are always shown |
| `\SectionNumbersOn` (default off, on for `manuscript=review`) | "1 Title", "1.1 Title" | Same, no dot |
| `\AbstractOff` (some communications) | No abstract | Abstract dropped |
| natbib loaded `super` (default) | Superscript numbers **after** `.,;:` (natmove), no space before | Same; groups compressed, "2,3" and "1–4" |
| natbib loaded `round` (journal `.cfg` with `super = false`, e.g. Biochemistry) | "(1)", "(2, 3)", italic numbers, before the punctuation | Same |
| `\setkeys{acs}{super=false}` in the preamble | Still superscript, now "(1)" with italic numbers: achemso only changes brackets once natbib is loaded | Same (`citations=super-round`) |
| `manuscript=suppinfo` | Title "Supporting Information:" on its own line; Figure/Scheme/Table **S1**; citations and labels S1, (S1); pages S-1 | Same; equations keep (1), (2), … |
| `biblabel` | "(1)" (brackets, default), "1." (fullstop/period), "1" | Same label form in the reference list |

The prep script prints what it found, e.g. `achemso journal=amlccd manuscript=letter
citations=super sections=off`. Compare that with the PDF before going on.
Overrides, when the user wants the Word file to differ from the PDF:
`ACHEMSO_OPTS="--sections on --numbered on --prefix S" build.sh …`. Prefer instead to make the
same change in the scratch copy's preamble (see below), so the verification PDF matches.

## Supporting Information built from a Letter template
An SI written with `\documentclass[journal=amlccd,manuscript=letter]{achemso}` compiles with **no
section headings** (the Letters `.cfg` turns them off for every type), numbers its figures 1, 2, …
while the main text cites "Figure S4", and, here, also lacked `\usepackage{threeparttable}`, so
every table broke. Ask the user how the Word SI should look. If they want headings and S-numbers,
add to the **scratch copy's** preamble (never the user's file without asking):
```latex
\usepackage{threeparttable}            % only if missing
\SectionsOn\SectionNumbersOn           % or just \SectionsOn for unnumbered headings
\makeatletter\renewcommand*\thefigure{S\@arabic\c@figure}\renewcommand*\thetable{S\@arabic\c@table}\makeatother
```
Recompile. The probe then picks the changes up, and the PDF used for verification matches.
`\SectionsOn` works even after the `.cfg`'s `\SectionsOff`; `manuscript=suppinfo` would not
bring the headings back for a Letters journal.

## Front matter
- `\author`, then `\affiliation`: an affiliation belongs to every author since the previous one.
  `\alsoaffiliation` adds one to the last author. Symbols go to affiliations in order of first
  appearance (†, ‡, ¶, §, ‖, ⊥, #, @, △, ▽), then to `\altaffiliation` notes ("These authors
  contributed equally"). An author's marks read ∗ (has `\email`), affiliations, alternative
  affiliations: "Ann Author,†,§ … Cy Third,∗,‡ and Dee Fourth∗,†".
- "E-mail: a; b" is printed even with no `\email` (unless `email=false`), then "Phone: …",
  "Fax: …" lines.
- `\keywords` and `\abbreviations` print only with `keywords=true` / `abbreviations=true`; the
  prep script warns and leaves them out. achemso turns `\footnote` into reference-list notes;
  also warned, not reproduced.
- The `tocentry` (TOC graphic) is a separate upload, like Elsevier's graphical abstract.

## Floats
- `figure`, `scheme`, `chart`, `graph`: one picture each, in document order (`STEM_figN`).
  - A single `\includegraphics` uses the file itself. PDFs are rendered at 300 dpi plus an SVG;
    PNG/JPEG files are used unchanged (above 2400 px they are downsampled).
  - Anything else (subfigure panels, TikZ panel labels such as `\node[overlay] {(a)}`, chemfig)
    is typeset alone at the paper's text width with the manuscript preamble, cropped to its ink
    (`pdfcrop`) and rendered from that PDF. Overlay labels hang outside the TeX box; the ink
    crop keeps them. The Word width is the typeset width, capped at the text width.
- **Comment-only lines must vanish, not become blank lines.** A `% (b) panel` line between two
  subfigures turned into a paragraph break and put every panel on its own row.
- Tables: booktabs rules become Word borders (1 pt top and bottom, 0.5 pt under the header),
  `\multicolumn` spans are kept, and `\addlinespace`/`\cmidrule` are dropped. `\tnote{a}` becomes
  an italic superscript; `tablenotes` become "Table Note" paragraphs under the table. Captions
  and notes are indented to the table's width, as `threeparttable` sets them. Rows and notes are
  "keep with next", so a table stays on one page with its notes. That leaves white space where a
  long table moves to the next page.
- `\captionsetup` must not be mistaken for `\caption`: match `\caption(?![A-Za-z])`.

## Text details
- Macros with arguments are expanded (`\newcommand*\REF[1]{\textbf{[REF: #1]}}` gives bold
  "[REF: …]" placeholders); `\latin{}` is plain text.
- `$\mathrm{La}^{3+}$`, `O$_\mathrm{W}$`, `LaCl$_3$`, `nm$^3$` become text sub/superscripts.
  Charges use a real minus sign (−).
- T1 fonts ligature an en dash followed by a hyphen (`–-`, a Unicode dash plus `-`) into an
  **em dash**. The Word file copies the PDF; tell the user, since it is almost always a typo
  for `--`.
- `\subref{fig:1b}` gives "b" (from `sub@fig:1b` in the `.aux`); `\eqref` gives "(n)".

## Known differences in the checks (not errors)
- Inline formulas with stacked scripts (K<sub>s</sub><sup>0</sup>, k<sub>B</sub>T ln f) tokenize
  differently. Check those sentences against the `.tex` by hand.
- Symbols with two code points: ∆ (PDF) / Δ (Word), ◦ / ∘ (degree), and the tilde and radical
  accents that OMML stores as structure, not text.
- pandoc puts U+200B (zero-width space) into empty OMML bases (`$^\circ$`, ∑ limits) and after
  inline math that ends a table cell. It is invisible.
- Affiliation marks at the start of a line and `\tnote` tags inside table rows are missed by the
  PDF reader, so Word shows a few more superscripts.
- A near-full-width display equation (Cambria Math is wider than Computer Modern) gets its
  number right up against it in Word.
