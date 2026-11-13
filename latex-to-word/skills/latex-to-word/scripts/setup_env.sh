#!/bin/zsh
# Check the tools the latex-to-word skill needs and create its Python environment.
# usage: setup_env.sh [VENV_DIR]   (default ~/.venv-latex-to-word)
V=${1:-$HOME/.venv-latex-to-word}
ok=1
for c in pandoc latexmk pdflatex bibtex gs magick python3; do
  if command -v $c > /dev/null; then echo "found   $c"; else echo "MISSING $c"; ok=0; fi
done
pandoc --version 2> /dev/null | head -1
[[ -d $V ]] || python3 -m venv $V
$V/bin/pip -q install --upgrade pymupdf lxml && echo "Python venv ready: $V (PyMuPDF, lxml)"
echo "Use:  export PYMUPDF_PYTHON=$V/bin/python"
[[ $ok == 1 ]] || echo "Install the missing tools first (e.g. brew install pandoc ghostscript imagemagick; MacTeX for LaTeX)."
command -v osascript > /dev/null && echo "macOS: EndNote 21 + Microsoft Word are needed for the EndNote / Word Compare steps."
