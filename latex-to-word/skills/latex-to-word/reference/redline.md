# Marked copy (changes since an earlier version)

Reviewers usually want changes shown **inline**: additions highlighted, deletions struck through,
with nothing in the margin. Tracked changes put balloons and change bars in the margin, so convert
them into plain formatting.

## Inputs
- `original.docx`, e.g. built from the initial-submission LaTeX with the same pipeline, and
  `revised.docx`.
- **Both formatted by EndNote from the same library state.** If references were corrected in the
  library after the original was formatted, run Update Citations on the original again. Otherwise
  those references appear as "new".
- **Unchanged figures must be identical images in both files.** Copy the revised picture's bytes
  into the original if only the rendering differs. Word Compare marks any image difference as
  old-deleted plus new-inserted.

## Word Compare by AppleScript
Use fresh file names in Word's container folder; see verification.md about "Welcome back".
```applescript
tell application "Microsoft Word"
  open file name "<tmp>/orig_123.docx"
  -- orig := the document whose full name contains "orig_123"
  compare orig path "<tmp>/rev_123.docx" author name "<author>" target compare target new ¬
    ignore all comparison warnings true add to recent files false
  -- res := the document whose full name does not contain "orig_123"
  save as res file name "<tmp>/compare.docx" file format format document
  -- close all documents in <tmp> saving no
end tell
```
Check direction: text that exists only in the revised file must sit inside `<w:ins>`.

## Static redline
`$PYMUPDF_PYTHON scripts/make_redline.py compare.docx revised.docx original.docx marked.docx` (needs lxml)
- **Tracked changes to formatting:** `w:ins` becomes yellow highlight, `w:del` becomes red
  strikethrough (`w:delText` turned into `w:t`). It works inside math runs (`m:r`) too, and drops
  paragraph-mark markers.
- **Deleted pictures** are dropped, because strikethrough can't hide an image. So is any paragraph
  that only held one.
- **Fields** (EndNote) are reduced to their displayed text. Changed citation numbers read
  [~~old~~ new].
- **The reference list** is rebuilt *per reference* from the two EndNote bibliographies, matched by
  entry text after the "[n]" label. New references are fully highlighted, and renumbered ones get
  "[~~old~~ new]". Word's own diff of a renumbered list pairs neighbouring references word by word
  and is unreadable.

## Verify (all must hold)
- With the red-struck text removed, body text and the reference list equal the revised file word
  for word.
- With the highlighted text removed, the body equals the original word for word, and the reference
  entries equal the original's as a set. The order follows the revised list.
- The pictures (PNG and SVG) equal the revised file's in number, order and bytes.
- No tracked changes (`w:ins`, `w:del`, `w:moveFrom`, `w:moveTo`) and no `fldChar` are left. The
  file validates.
- The Word render looks right: open a copy and export it to PDF.

## Limitation
`make_redline.py` matches reference-list entries after an elsarticle "[n]" label. For achemso's
"(n)" lists, adapt its `label` pattern and the "[~~old~~ new]" rewrite first, and test.
