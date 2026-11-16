# Verifying the Word file against the compiled PDF

Run both checks on a *copy* of the .docx if Word has the original open.

## `scripts/compare_docx_pdf.py main.docx main.pdf`
It reads both documents independently:
- **PDF side:** fonts tell body text (12 pt) from captions, affiliations and footnotes (10 pt),
  figure-internal text (Arial, DejaVu, Helvetica) and line numbers. It drops pure-math blocks,
  which are display equations.
- **Word side:** it collects `w:t` text plus inline math, skips display equations, and never reads
  field codes.

It reports:
1. **Body text:** word-level differences.
2. **Small text:** captions, affiliations and footnotes.
3. **Citation groups:** the sequence of citation numbers must be identical.
4. **Display equations:** the numbering.
5. **Reference list:** entries compared on content (authors, title, journal, volume, year,
   pages). It ignores capitalization, initials spacing, issue numbers and DOI links, because
   EndNote styles and `elsarticle-num` format these differently.

Known artefacts of reading the PDF, which are not real differences:
- Page numbers mid-sentence, and words hyphenated across a page break.
- Inline formulas with stacked sub- and superscripts, such as α_S^{A/B}. The PDF splits them into
  fragments that land elsewhere. Check those sentences against the `.tex` source by hand.
- The centred dot: the PDF gives U+00B7 and Word U+22C5, both from `\cdot`. Likewise µ (micro
  sign) vs μ (mu), and Word storing math minus as "-" (drawn as a minus sign).
- `unicodedata` NFKC folds ϕ→φ and ϵ→ε. Don't use NFKC when comparing math symbols.

For "every sentence identical", add a pass that keeps punctuation tokens (`\w+|[^\w\s]`) after
normalizing dash and quote characters.

## achemso: `scripts/compare_achemso.py` and `scripts/check_scripts_achemso.py`
Same arguments and the same idea, adapted to the ACS layout (details in `achemso.md`):
- **Classification:** affiliations are body size. Caption blocks are recognised by their first
  line ("Figure/Scheme/Chart/Table N:"), since achemso sets the abstract in `\small`. The TOC
  entry's heading (taken from the Word file) is skipped; after the references, reading stops
  there. Its picture is checked by eye against the PDF.
- **Tables** are found by their booktabs rules and compared as a bag of words, since the PDF
  reads cells in layout order.
- **Citations:** Word citations are the runs linked to `#_bibN` (or inside an EndNote field).
  Superscript groups are compared in sequence (round "(1)" groups in round mode), with
  `\citenum` left out on both sides.
- **The reference list** is compared entry by entry, with "(n)"/"(Sn)" labels.
- **`[REF: …]`-style placeholders** are listed and compared in order when the paper has them.
- `check_scripts_achemso.py` ends with an order-independent count of script characters per kind.
  Everything in the PDF must be in Word. Word may have a few more, where the PDF reader misses
  marks at line starts.

## `scripts/check_equations.py main.tex main.docx`
For each `\begin{equation}`: letters, digits and symbols of the LaTeX (Greek commands mapped to
their glyphs, argument-free user macros expanded) against the Word equation, including the
∑ and ⟨ ⟩ that OMML stores as attributes. Expect 0 equations with differing symbols.

## `scripts/check_scripts.py main.docx main.pdf`
- Lists every sub- and superscript: in the PDF from font size and baseline offset, in Word from
  `w:vertAlign` plus OMML `m:sSub`, `m:sSup` and `m:sSubSup`. It also counts non-ASCII symbols.
- Compare **order-independently**: count script characters per type. The order differs because
  floats move captions and footnotes sit at the page bottom.
- Also scan Word runs for chemical formulas with plain digits, e.g. `\b(CO|CH|H|N|C)\d` in a
  non-script run. That count should be zero.

## Display equations
Compare the symbols of each `\begin{equation}` in the `.tex` with its Word equation (`m:t` text):
- Strip `\label{…}` and layout commands first.
- Map Greek commands to the glyphs LaTeX uses: `\phi`→ϕ (U+03D5) and `\epsilon`→ϵ (U+03F5).

## Rendering through Word
Word sandbox: work in `~/Library/Containers/com.microsoft.Word/Data/Documents/<tmp>/` and use
**fresh file names every time**. Reopening a path Word has seen shows a "Welcome back" prompt,
and AppleScript then fails with "object does not exist".
```applescript
tell application "Microsoft Word"
  open file name "<tmp>/check_123.docx"
  -- find the document whose full name contains "check_123", then:
  save as d file name "<tmp>/check_123.pdf" file format format PDF
  close d saving no
end tell
```
- Check the fonts in the exported PDF: there should be no fallback or LastResort font. Crop and
  view the abstract, a units-heavy methods page, an inline-formula sentence and a caption.
- Word for Mac's Save as PDF rasterizes pictures to about 150 dpi, so judge figure sharpness in
  Word itself.
- Delete the temporary folder afterwards.

## Pictures
Compare the media of each `<a:blip>` (PNG and its `svgBlip`) in document order against the
expected document. The same number and identical bytes rule out duplicates and stale figures.
