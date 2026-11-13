# EndNote: a per-paper library and live citations (EndNote 21, macOS)

## Why a dedicated library
A library containing exactly the paper's references, where **record *n* = reference [*n*]**,
keeps the citations portable (the library can travel with the paper in a synced folder) and easy
to check. The user's main library is only ever *read*.

## Steps
1. **Empty library.** EndNote's AppleScript can't create one: `make new document` just times
   out. Ask the user to choose **File › New** and save, e.g., `PAPER.enl` in the paper folder.
   Have them close their main library when they do manual EndNote edits, to avoid editing the
   wrong one.
2. **Collect the records:**
   `python3 scripts/build_enxml.py BIB AUX "<main library>.enl" refs.xml cites.json [--prefer KEY=REC]`.
   - The main library must be open in EndNote. It is matched read-only through
     `<library>.Data/sdb/sdb.eni`, and records are exported through EndNote.
   - Duplicates in the main library are reported. Choose one with `--prefer`.
   - References missing from the main library are built from the .bib (book, proceedings,
     software, journal types). Tell the user which ones they are.
3. **Import** in citation order, as pure-ASCII XML (non-ASCII as `&#NNNN;`):
   ```python
   open("refs_ascii.xml", "w").write(xml.encode("ascii", "xmlcharrefreplace").decode())
   ```
   `osascript scripts/en_import.applescript refs_ascii.xml PAPER.enl`. Then confirm with a
   read-only query that the ids are exactly 1..N, in order, and that every title matches.
4. **DOIs:** `python3 scripts/verify_doi.py PAPER.Data/sdb/sdb.eni doi_check.json`.
   - It compares each DOI's registered title, first author and year, and searches Crossref for
     missing DOIs.
   - Only accept a DOI found by search if title, first author and year match. Many books,
     software, very old papers and conference items have no DOI.
   - If a year conflicts, check PubMed or Crossref dates. The year of the volume/issue wins over
     an "online first / Just Accepted" date when volume and pages are cited.
   - Strip `https://doi.org/` from DOI fields. Most styles add that prefix themselves, which
     otherwise prints it twice.
5. **Field fixes:** `osascript scripts/en_setfield.applescript PAPER.enl REC "<Field label>" value.txt`.
   - Write the value to a UTF-8 file first, normalized to **NFC**. Downloaded records often
     contain decomposed accents, and EndNote then prints initials like "C.d." for "Cédric".
   - Field labels depend on the reference type: `fields of "<RecordID …/>"` lists them.
   - Check the result read-only in the database.
6. **Changing a reference type:** `set field "Reference Type"` is silently ignored. Use
   `osascript scripts/en_setrecord.applescript PAPER.enl REC record.xml` with a **bare
   `<record>…</record>`** element. With the `<xml><records>` wrapper it reports success but
   changes nothing. The record number is kept. Or ask the user to change the type in the record
   window.
7. **Citations in Word:**
   - Build the .docx with `cites.json`, which writes placeholders `{Surname, Year #Rec}`.
   - The user installs the journal's output style. Styles from endnote.com go in
     `~/Documents/EndNote/Styles`; then restart EndNote. They open the .docx with only the paper
     library open and click **EndNote › Update Citations and Bibliography**.
   - Then run `python3 scripts/tidy_docx.py IN.docx OUT.docx`. It removes the empty paragraph
     EndNote leaves under the "References" heading, and merges Word-renamed duplicate styles.
8. **Keep the map in sync:** EndNote matches a placeholder on surname **and** year **and**
   record number. After correcting an author or year in the library, run
   `python3 scripts/sync_cites.py cites.json PAPER.Data/sdb/sdb.eni` before rebuilding. Otherwise
   EndNote reports "Author, Year #n not found". It handles both "Last, First" and "First Last"
   author forms.
9. **Updating from newer downloads:** `python3 scripts/en_diff.py PAPER.Data/sdb/sdb.eni "<main>.Data/sdb/sdb.eni" diff.json`
   lists field differences against the newest copy in the main library. Keep verified fixes, such
   as bare DOIs and corrected years.

## AppleScript facts
- Record specifiers are text like `<RecordID database="2" recNum="28" />`. The database number is
  EndNote's per-session id for an open library. Find it with
  `retrieve "all" records in document "PAPER.enl"`, or let the helper scripts do it.
- `export … as "RSXML"` returns UTF-8 bytes mis-decoded as MacRoman ("–" becomes "‚Äì").
  `scripts/en_export.py` undoes that with `s.encode("mac_roman").decode("utf-8")`.
- `format bibliography … with "<style>"` only sees EndNote's built-in styles, not personal ones,
  and wrote no file in testing. Check formatting in Word instead.
- Journal-name abbreviations come from the library's **Journals term list**, not the record. If a
  style abbreviates only some journals, look for entries with Abbreviation 1 set. A duplicate
  term without an abbreviation wins the lookup. Term lists can only be edited in the GUI
  (Library › Open Term Lists), and each library has its own.

## Style quirks seen with the Elsevier "J Membrane Science" style
- **Electronic Article** records print no volume: change them to Journal Article.
- **Conference Proceedings** and **Conference Paper** print no DOI. Series titles aren't printed
  either.

## achemso (ACS) papers
The same library workflow applies. Placeholders are put where achemso prints the citation:
after `.,;:` for superscript citations (natmove), before the punctuation in round style.
`\citenum` stays a plain number. The user installs the journal's ACS output style (e.g. "J Am
Chem Soc" or "ACS") from endnote.com. With an SI (`manuscript=suppinfo`), the SI's own
references are numbered S1, S2, … in the PDF. Check that the EndNote style can do that, or keep
the SI's citations static.
