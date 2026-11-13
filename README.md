# latex2word

A [Claude Code](https://claude.com/claude-code) skill that converts a LaTeX manuscript into a
submission-ready Word file and checks it against the compiled PDF.

Supported document classes:

| Class | Journals | Notes |
|---|---|---|
| `elsarticle` | Elsevier | Front matter, numbered equations, EndNote citations |
| `achemso` | ACS (articles, letters, Supporting Information) | ACS citation styles, †/‡ author marks, S-numbering for an SI, booktabs tables |

The Word file has the same text, citations, equations and figures as the PDF:
- **Equations** are editable Word equations.
- **Figures** are vector (SVG), at their LaTeX size.
- **Citations** are either static numbers or live EndNote citations.

## Install

```zsh
claude plugin marketplace add zidan0x266/latex2word
claude plugin install latex-to-word@latex2word
```

Or copy the skill folder by hand:
`cp -R latex-to-word/skills/latex-to-word ~/.claude/skills/`.

**Tools** (once per machine, macOS):
```zsh
brew install pandoc ghostscript imagemagick      # plus MacTeX for LaTeX
zsh latex-to-word/skills/latex-to-word/scripts/setup_env.sh   # Python venv with PyMuPDF and lxml
```
Run the setup script from a clone of this repo, or ask Claude to set up the latex-to-word skill.
EndNote citations and marked copies also need EndNote 21 and Microsoft Word for Mac.

## Use

Open Claude Code in your paper's folder and ask, for example:

- "Convert main.tex to Word."
- "Convert main.tex and SI.tex to Word, with EndNote citations."
- "Check that the Word file matches the PDF."
- "Prepare the figures for upload."
- "Make a marked copy comparing the revision with the first submission."

Claude picks the skill up by itself, or you can call it with `/latex-to-word:latex-to-word`.

What happens:
1. Claude compiles a scratch copy of the paper. Your source files are never changed.
2. It builds the Word file and verifies it against the PDF: text, citations, equations,
   sub/superscripts, symbols and tables.
3. It saves the results in a `word/` folder inside the paper folder.

Claude asks before deciding anything the PDF can't settle, for example when a template hides the
SI's section headings. It tells you which steps you have to do by hand in EndNote: creating an
empty library, choosing the journal style, and **Update Citations and Bibliography**.

## Limitations

- Only `elsarticle` and `achemso` are supported. Other classes need their own prep script.
- English "References" heading and US Letter page size are assumed.
- The marked-copy script expects `elsarticle`-style "[n]" reference labels.

See [`latex-to-word/skills/latex-to-word/SKILL.md`](latex-to-word/skills/latex-to-word/SKILL.md)
for the full workflow and `reference/` for the details.
