#!/bin/zsh
# usage: build.sh BUILD_DIR STEM OUT.docx [ENDNOTE_CITES.json]   (BUILD_DIR already compiled with latexmk)
# The document class decides the pipeline: achemso (ACS) or elsarticle (Elsevier, the default).
# achemso: extra prep options, e.g. ACHEMSO_OPTS="--sections on --numbered on --prefix S"
set -e
T=${0:A:h}; B=$1; STEM=$2; OUT=$3
PY=${PYMUPDF_PYTHON:-python3}
[[ -f $B/default-ref.docx ]] || pandoc -o $B/default-ref.docx --print-default-data-file reference.docx
if grep -Eq '^[^%]*\\documentclass[^{]*\{achemso\}' $B/$STEM.tex; then
  $PY $T/render_figs_achemso.py $B $STEM > /dev/null
  python3 $T/mkref.py $B/default-ref.docx $B/reference.docx --achemso > /dev/null
  python3 $T/prep_achemso.py $B $STEM $B/${STEM}_pandoc.tex $B/${STEM}_eqnums.json $4 ${=ACHEMSO_OPTS}
  pandoc -f latex -t docx $B/${STEM}_pandoc.tex --resource-path=$B --reference-doc=$B/reference.docx \
    --lua-filter=$T/elsarticle.lua -o $B/${STEM}_raw.docx
  python3 $T/post.py $B/${STEM}_raw.docx $B/${STEM}_eqnums.json $OUT $(<$B/${STEM}_post.opts)
  if $PY -c 'import pymupdf' 2> /dev/null; then
    python3 $T/embed_svg.py $OUT $OUT.svg.docx $B/svg $(grep -o 'png/[^}]*\.png' $B/${STEM}_pandoc.tex | sed 's#png/##; s#\.png##')
    mv $OUT.svg.docx $OUT
  else
    echo "PyMuPDF not found: figures stay PNG (set PYMUPDF_PYTHON to a python with pymupdf)"
  fi
  exit 0
fi
python3 $T/render_figs.py $B $STEM > /dev/null
# intermediate style files go in the build folder, not next to the scripts
python3 $T/mkref.py $B/default-ref.docx $B/reference.docx > /dev/null
python3 $T/prep.py $B $STEM $B/${STEM}_pandoc.tex $B/${STEM}_eqnums.json $4  # $4: optional EndNote cites JSON
pandoc -f latex -t docx $B/${STEM}_pandoc.tex --resource-path=$B --reference-doc=$B/reference.docx \
  --lua-filter=$T/elsarticle.lua -o $B/${STEM}_raw.docx
python3 $T/post.py $B/${STEM}_raw.docx $B/${STEM}_eqnums.json $OUT
# SVG figures (vector in Word 2016+, PNG kept as fallback); needs PyMuPDF, e.g.
# PYMUPDF_PYTHON=.venv/bin/python after: python3 -m venv .venv && .venv/bin/pip install pymupdf
if $PY -c 'import pymupdf' 2> /dev/null; then
  $PY $T/render_svgs.py $B $STEM > /dev/null
  python3 $T/embed_svg.py $OUT $OUT.svg.docx $B/svg $(grep -o 'png/[^}]*\.png' $B/${STEM}_pandoc.tex | sed 's#png/##; s#\.png##')
  mv $OUT.svg.docx $OUT
else
  echo "PyMuPDF not found: figures stay PNG (set PYMUPDF_PYTHON to a python with pymupdf)"
fi
