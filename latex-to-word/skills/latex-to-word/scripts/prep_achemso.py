"""Rewrite an achemso (ACS) manuscript or Supporting Information into LaTeX that pandoc converts
cleanly to docx. The achemso counterpart of prep.py (elsarticle).

Numbers for sections, floats, equations and citations are taken from the LaTeX run (STEM.aux,
STEM.bbl) so the Word file matches the compiled PDF. Class behaviour (headings on/off and
numbered, abstract, citation style, label and float/page prefixes) comes from a probe run of the
manuscript's own preamble, i.e. after the class, the journal's achemso-<journal>.cfg and the
preamble (\\setkeys{acs}{...}, \\SectionsOn, \\renewcommand\\thefigure{S...}) have all acted.

usage: python3 prep_achemso.py BUILD_DIR STEM OUT.tex EQNUMS.json [CITES.json]
                               [--sections auto|on|off] [--numbered auto|on|off] [--prefix auto|S|none]
  BUILD_DIR must contain STEM.tex, STEM.aux, png/STEM_figs.json (render_figs_achemso.py) and,
  with citations, STEM.bbl. CITES.json: {bibkey: {"author", "year", "rec"}} -> EndNote
  temporary citations. Also writes BUILD_DIR/STEM_post.opts (options for post.py).
"""
import argparse
import json
import os
import re
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("build"); ap.add_argument("stem"); ap.add_argument("out_tex"); ap.add_argument("out_eq")
ap.add_argument("cites", nargs="?")
ap.add_argument("--sections", choices=["auto", "on", "off"], default="auto")
ap.add_argument("--numbered", choices=["auto", "on", "off"], default="auto")
ap.add_argument("--prefix", default="auto")
args = ap.parse_args()
build, stem = args.build, args.stem
endnote = json.load(open(args.cites, encoding="utf8")) if args.cites else None
warnings = []


def warn(msg):
    warnings.append(msg)
    print("WARNING:", msg, file=sys.stderr)


def read(name):
    with open(os.path.join(build, name), encoding="utf8") as f:
        return f.read()


def group(s, i):
    """s[i] == '{' -> (content, index after the matching '}')."""
    assert s[i] == "{", (s[i:i + 40])
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError("unbalanced braces near: " + s[i:i + 60])


def skip_ws(s, i):
    while i < len(s) and s[i] in " \t\n":
        i += 1
    return i


def strip_comments(src):
    out = []
    for line in src.split("\n"):
        m = re.search(r"(?<!\\)%", line)
        if m is None:
            out.append(line + "\n")
            continue
        before = line[:m.start()]
        if before.strip() == "":
            continue  # comment-only line: TeX produces nothing, not even a blank line (= paragraph break)
        out.append(before)
    return "".join(out)


src = strip_comments(read(stem + ".tex"))
aux = read(stem + ".aux")
bbl = read(stem + ".bbl") if os.path.exists(os.path.join(build, stem + ".bbl")) else ""

labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))
bibnum = {k: int(v) for k, v in re.findall(r"\\bibcite\{([^}]+)\}\{\{(\d+)\}", aux)}

pre, rest = src.split("\\begin{document}", 1)
body = rest.split("\\end{document}", 1)[0]

# ---------------------------------------------------------------- class settings, as achemso applies them
# A probe run of the manuscript's own preamble prints the effective settings after the class, the
# journal's achemso-<journal>.cfg (which uses TeX conditionals) and the preamble have all acted.
# (\documentclass[...] options for keys such as super= are reset by achemso and have no effect.)
cls_opts = dict(re.findall(r"(\w+)\s*=\s*([\w-]+)", re.search(r"\\documentclass\s*\[([^\]]*)\]", pre).group(1))) \
    if re.search(r"\\documentclass\s*\[", pre) else {}
journal, manuscript = cls_opts.get("journal", "jacsat"), cls_opts.get("manuscript", "article")
PROBE = r"""\makeatletter
\def\acsprobe#1#2{\immediate\write16{ACSPROBE #1=#2}}
\def\acsprobeif#1{\expandafter\ifx\csname if#1\endcsname\iftrue true\else false\fi}
\acsprobe{sections}{\ifx\section\acs@sections@none off\else on\fi}
\acsprobe{numbered}{\ifx\@startsection\acs@startsection@alt off\else on\fi}
\acsprobe{abstract}{\ifx\abstract\acs@abstract@start off\else on\fi}
\acsprobe{natbibsuper}{\acsprobeif{NAT@super}}
\acsprobe{open}{\expandafter\strip@prefix\meaning\NAT@open}
\acsprobe{email}{\acsprobeif{acs@email}}
\acsprobe{keywords}{\acsprobeif{acs@keywords}}
\acsprobe{abbreviations}{\acsprobeif{acs@abbreviations}}
\acsprobe{bibnumfmt}{\expandafter\strip@prefix\meaning\bibnumfmt}
\acsprobe{citenumfont}{\expandafter\strip@prefix\meaning\citenumfont}
\acsprobe{page}{\expandafter\strip@prefix\meaning\thepage}
\@for\acs@tmp:={figure,scheme,chart,graph,table}\do{%
  \acsprobe{the\acs@tmp}{\expandafter\expandafter\expandafter\strip@prefix\expandafter\meaning\csname the\acs@tmp\endcsname}}
\makeatother
"""
raw_pre = read(stem + ".tex").split("\\begin{document}", 1)[0]
probe_tex = os.path.join(build, stem + "_acsprobe.tex")
open(probe_tex, "w", encoding="utf8").write(raw_pre + "\\begin{document}\n" + PROBE + "\\end{document}\n")
r = subprocess.run(["pdflatex", "-draftmode", "-interaction=nonstopmode", os.path.basename(probe_tex)],
                   cwd=build, capture_output=True, text=True, errors="replace")
probe = dict(re.findall(r"^ACSPROBE (\w+)=(.*)$", r.stdout, re.M))
if len(probe) < 10 or not probe.get("bibnumfmt"):
    warn("class probe failed (see %s.log): assuming achemso defaults" % probe_tex[:-4])
    probe = {}
sections_on = probe.get("sections", "on") == "on"
numbered = probe.get("numbered", "off") == "on"
abstract_on = probe.get("abstract", "on") == "on"
if args.sections != "auto":
    sections_on = args.sections == "on"
if args.numbered != "auto":
    numbered = args.numbered == "on"
# citations: natbib is loaded with the journal's super setting; a later \setkeys{acs}{super=...}
# changes only brackets and number font (the citation stays superscript): achemso's own quirk.
paren = probe.get("open", "").endswith("(")
if probe.get("natbibsuper", "true") == "true":
    cite_mode = "super-round" if paren else "super"
else:
    cite_mode = "round"
    if not paren:
        warn("journal loads round citations but the preamble switches to superscript: check citations by hand")
ITALIC_NUMS = "textit" in probe.get("citenumfont", "")
CITE_PREFIX = "S" if "S#1" in probe.get("citenumfont", "") else ""   # suppinfo: S1, S2, ...
fmt = probe.get("bibnumfmt", "#1->(#1)").split("->", 1)[-1].replace(" ", "")
LABEL_MARK = "P" if fmt.startswith("(") and fmt.endswith(")") else "D" if fmt.endswith(".") else "N"
PAGE_PREFIX = re.sub(r"\\.*", "", probe.get("page", "->").split("->", 1)[-1])   # suppinfo: "S-"


def float_prefix(kind):
    if args.prefix != "auto":
        return "" if args.prefix == "none" else args.prefix
    return re.sub(r"\\.*", "", probe.get("the" + kind, "->").split("->", 1)[-1]).strip()   # "S\@arabic..." -> "S"


suppinfo = manuscript == "suppinfo"
for k in ("keywords", "abbreviations"):
    if probe.get(k) == "true" and re.search(r"\\%s\s*\{" % k, pre):
        warn(f"{k}=true: achemso prints the {k}; not reproduced, add them by hand")

# ---------------------------------------------------------------- macros (also with arguments)
macros, argmacros = {}, {}
for m in re.finditer(r"\\(?:re)?newcommand\*?\{?\\([A-Za-z]+)\}?", pre):
    j = skip_ws(pre, m.end())
    nargs = 0
    if pre[j] == "[":
        k = pre.index("]", j)
        nargs, j = int(pre[j + 1:k]), skip_ws(pre, k + 1)
    if pre[j] != "{":
        continue
    val, _ = group(pre, j)
    if nargs:
        argmacros[m.group(1)] = (nargs, val)
    elif not m.group(1).startswith("the"):  # \thefigure etc. are counters, not text macros
        macros[m.group(1)] = val.replace("\\xspace", "")
argmacros.setdefault("latin", (1, "#1"))   # achemso: \providecommand{\latin}[1]{#1}


def expand_macros(t):
    for _ in range(3):
        for name, val in macros.items():
            t = re.sub(r"\\%s(?![A-Za-z])(\{\})?" % name, lambda m: val, t)
    for name, (nargs, val) in argmacros.items():
        out, pos = [], 0
        for m in re.finditer(r"\\%s(?![A-Za-z])" % name, t):
            if m.start() < pos:
                continue
            i, vals = m.end(), []
            for _ in range(nargs):
                j = skip_ws(t, i)
                if j >= len(t) or t[j] != "{":   # single-token argument
                    vals.append(t[j]); i = j + 1
                else:
                    a, i = group(t, j)
                    vals.append(a)
            rep = val
            for n, a in enumerate(vals, 1):
                rep = rep.replace("#%d" % n, a)
            out.append(t[pos:m.start()] + rep)
            pos = i
        out.append(t[pos:])
        t = "".join(out)
    return t


# ---------------------------------------------------------------- front matter (achemso)
SYMBOLS = ["\u2020", "\u2021", "\u00b6", "\u00a7", "\u2016", "\u22a5", "#", "@", "\u25b3", "\u25bd"]
title, _ = group(pre, skip_ws(pre, re.search(r"\\title\s*(\[[^\]]*\])?", pre).end()))
authors, pending, affils, alts = [], [], [], []
for m in re.finditer(r"\\(author|affiliation|altaffiliation|alsoaffiliation|email|phone|fax)(?![A-Za-z])", pre):
    i = skip_ws(pre, m.end())
    if pre[i] == "[":
        i = skip_ws(pre, pre.index("]", i) + 1)
    arg, _ = group(pre, i)
    arg = re.sub(r"\s+", " ", arg).strip()
    kind = m.group(1)
    if kind == "author":
        authors.append({"name": arg, "aff": [], "alt": [], "email": None, "phone": None, "fax": None})
        pending.append(authors[-1])
    elif kind in ("affiliation", "alsoaffiliation"):
        if arg not in affils:
            affils.append(arg)
        for a in (pending if kind == "affiliation" else authors[-1:]):
            a["aff"].append(arg)
        if kind == "affiliation":
            pending = []
    elif kind == "altaffiliation":
        if arg not in alts:
            alts.append(arg)
        authors[-1]["alt"].append(arg)
    else:
        authors[-1][kind] = arg
# achemso: affiliations (incl. \alsoaffiliation, in order of appearance) take the symbols first,
# then the alternative (footnote) affiliations; corresponding authors (\email) get an asterisk
sym = {a: SYMBOLS[i] for i, a in enumerate(affils + alts)}


def marks(a):
    return ",".join((["\u2217"] if a["email"] else []) + [sym[x] for x in a["aff"] + a["alt"]])


parts = []
for k, a in enumerate(authors):
    last = k == len(authors) - 1 and len(authors) > 1
    sep = "," if not last and len(authors) > 2 else ""
    mk = marks(a)
    parts.append(("and " if last else "") + a["name"] + sep + ("\\textsuperscript{%s}" % mk if mk else ""))
front = ["\\begin{fmauthors}\n" + " ".join(parts) + "\n\\end{fmauthors}"]
if affils + alts:
    front.append("\\begin{fmaffils}\n" + "\n\n".join("\\textsuperscript{%s}%s" % (sym[x], x) for x in affils + alts)
                 + "\n\\end{fmaffils}")
contact = []
if probe.get("email", "true") == "true":
    contact.append("E-mail: " + "; ".join(a["email"] for a in authors if a["email"]))
for kind, name in (("phone", "Phone"), ("fax", "Fax")):
    vals = [a[kind] for a in authors if a[kind]]
    if vals:
        contact.append(f"{name}: " + "; ".join(vals))
if contact:
    front.append("\\begin{fmcorr}\n" + "\n\n".join(contact) + "\n\\end{fmcorr}")
if suppinfo:
    title = "Supporting Information:\\\\ " + title

# TOC graphic: a separate upload item, as the Graphical Abstract is for Elsevier
body = re.sub(r"\\begin\{tocentry\}.*?\\end\{tocentry\}", "", body, flags=re.S)
# headings achemso always prints (\acs@section*), even with \SectionsOff
ALWAYS = "ZZACSHEADING"
body = re.sub(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
              lambda m: "\\section*{%sAbstract}\n" % ALWAYS + m.group(1).strip() if abstract_on else "", body, flags=re.S)
for env, name in (("acknowledgement", "Acknowledgement"), ("suppinfo", "Supporting Information Available")):
    body = re.sub(r"\\begin\{%s\}(.*?)\\end\{%s\}" % (env, env),
                  lambda m: "\\section*{%s%s}\n" % (ALWAYS, name) + m.group(1).strip(), body, flags=re.S)
if re.search(r"\\footnote(?![A-Za-z])", body):
    warn("\\footnote: achemso turns footnotes into reference-list notes; not reproduced, check by hand")

doc = "\n\n".join(front) + "\n\n" + body
doc = expand_macros(doc)
title = expand_macros(title)

# ---------------------------------------------------------------- floats with pictures (render_figs_achemso.py)
with open(os.path.join(build, "png", stem + "_figs.json")) as f:
    figs = json.load(f)
FLOAT_NAMES = {"figure": "Figure", "scheme": "Scheme", "chart": "Chart", "graph": "Graph"}
counters = {k: 0 for k in list(FLOAT_NAMES) + ["table"]}
fig_seq = [0]


def caption_of(env):
    m = re.search(r"\\caption(?![A-Za-z])\s*(\[[^\]]*\])?", env)
    if not m:
        return None
    cap, _ = group(env, skip_ws(env, m.end()))
    return cap


def convert_float(m):
    kind, env = m.group(1), m.group(2)
    counters[kind] += 1
    num = float_prefix(kind) + str(counters[kind])
    fig = figs[fig_seq[0]]
    fig_seq[0] += 1
    for l in re.findall(r"\\label\{([^}]+)\}", env):
        if labels.get(l) != num and not labels.get(l, "").startswith(num):
            warn(f"{kind} label {l}: aux says {labels.get(l)}, sequential count {num}")
    cap = caption_of(env)
    if cap is None:
        warn(f"{kind} {num} has no caption")
        cap = ""
    cap = re.sub(r"\\label\{[^}]+\}", "", cap).strip()
    return ("\\begin{figure}\n\\centering\n\\includegraphics[width=%.3fin]{png/%s.png}"
            "\n\\caption{%s %s: %s}\n\\end{figure}" % (fig["width_in"], fig["name"], FLOAT_NAMES[kind], num, cap))


doc = re.sub(r"\\begin\{(figure|scheme|chart|graph)\*?\}(?:\[[^\]]*\])?(.*?)\\end\{\1\*?\}", convert_float, doc, flags=re.S)
if fig_seq[0] != len(figs):
    warn(f"{fig_seq[0]} picture floats but {len(figs)} rendered figures")

# ---------------------------------------------------------------- tables (booktabs, optionally threeparttable)


def tnote(t):
    return re.sub(r"\\tnote\{([^}]*)\}", r"\\textsuperscript{\\textit{\1}}", t)


def convert_table(m):
    counters["table"] += 1
    env = m.group(1)
    num = float_prefix("table") + str(counters["table"])
    for l in re.findall(r"\\label\{([^}]+)\}", env):
        if labels.get(l) != num:
            warn(f"table label {l}: aux says {labels.get(l)}, sequential count {num}")
    cap = caption_of(env) or ""
    cap = re.sub(r"\s+", " ", tnote(re.sub(r"\\label\{[^}]+\}", "", cap))).strip()
    tabs = list(re.finditer(r"\\begin\{tabular\}", env))
    if len(tabs) != 1:
        warn(f"table {num}: {len(tabs)} tabular environments; passed to pandoc unchanged")
        return m.group(0)
    spec, si = group(env, tabs[0].end())
    rows = env[si:env.index("\\end{tabular}")]
    rows = re.sub(r"\\(addlinespace|cmidrule)(\([^)]*\))?(\[[^\]]*\])?(\{[^}]*\})?", "", tnote(rows))
    notes = []
    nm = re.search(r"\\begin\{tablenotes\}(?:\[[^\]]*\])?(.*?)\\end\{tablenotes\}", env, re.S)
    if nm:
        for tag, txt in re.findall(r"\\item(?:\[([^\]]*)\])?(.*?)(?=\\item|$)", nm.group(1), re.S):
            txt = re.sub(r"\\(footnotesize|small|scriptsize)(?![A-Za-z])", "", txt)
            txt = re.sub(r"\s+", " ", txt).strip()
            notes.append(("\\textsuperscript{\\textit{%s}} " % tag if tag else "") + txt)
    out = ("\\begin{table}\n\\caption{Table %s: %s}\n\\begin{tabular}{%s}%s\\end{tabular}\n\\end{table}\n"
           % (num, cap, spec, rows))
    if notes:
        out += "\n\\begin{tablenotes}\n" + "\n\n".join(notes) + "\n\\end{tablenotes}\n"
    return out


doc = re.sub(r"\\begin\{table\*?\}(?:\[[^\]]*\])?(.*?)\\end\{table\*?\}", convert_table, doc, flags=re.S)

# ---------------------------------------------------------------- equations
eqnums = []


def convert_eq(m):
    n = len(eqnums) + 1
    inner = m.group(1)
    for l in re.findall(r"\\label\{([^}]+)\}", inner):
        if labels.get(l) != str(n):
            warn(f"equation label {l}: aux says {labels.get(l)}, sequential count {n}")
    inner = re.sub(r"\\label\{[^}]+\}", "", inner).strip()
    eqnums.append(str(n))
    return "\n\\[\n" + inner + "\n\\]\n"


doc = re.sub(r"\\begin\{equation\}(.*?)\\end\{equation\}", convert_eq, doc, flags=re.S)
if re.search(r"\\begin\{(align|eqnarray|gather|multline|equation\*)", doc) or "\\[" in body:
    warn("other display-math environments present; numbering list may not line up")

# ---------------------------------------------------------------- headings
sec = [0, 0, 0]


def convert_heading(m):
    level = {"section": 0, "subsection": 1, "subsubsection": 2}[m.group(1)]
    text, end = group(doc_ref[0], m.end() - 1)
    text_labels = re.findall(r"\\label\{([^}]+)\}", text)
    text = re.sub(r"\\label\{[^}]+\}", "", text).strip()
    if text.startswith(ALWAYS):
        return "\\section*{%s}" % text[len(ALWAYS):], end
    if not sections_on:
        return "", end                                   # \SectionsOff: no heading in the PDF
    if m.group(2) or not numbered:
        return "\\%s*{%s}" % (m.group(1), text), end
    sec[level] += 1
    for k in range(level + 1, 3):
        sec[k] = 0
    num = ".".join(str(c) for c in sec[:level + 1])
    for l in text_labels:
        if labels.get(l) != num:
            warn(f"section label {l}: aux says {labels.get(l)}, computed {num}")
    return "\\%s*{%s %s}" % (m.group(1), num, text), end   # achemso numbering: "1 Title", no dot


doc_ref = [doc]
out, pos = [], 0
for m in re.finditer(r"\\(section|subsection|subsubsection)(\*?)\{", doc):
    if m.start() < pos:
        continue
    rep, end = convert_heading(m)
    out.append(doc[pos:m.start()] + rep)
    pos = end
out.append(doc[pos:])
doc = "".join(out)

# ---------------------------------------------------------------- citations
def citelink(n):
    num = CITE_PREFIX + str(n)
    return "\\hyperlink{bib%d}{%s}" % (n, "\\textit{%s}" % num if ITALIC_NUMS else num)


def compress(nums):
    nums = sorted(set(nums))
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{citelink(nums[i])}--{citelink(nums[j])}")
        else:
            parts.extend(citelink(n) for n in nums[i:j + 1])
        i = j + 1
    return (", " if cite_mode == "round" else ",").join(parts)


def tex_escape(t):
    return re.sub(r"([&%#_$])", r"\\\1", t)


def endnote_cite(keys):
    """{Author, Year #Rec;...}: EndNote's unformatted citation, resolved by Update Citations."""
    keys = sorted(keys, key=lambda k: bibnum.get(k, 0))
    return "\\{" + ";".join(tex_escape("%s, %s #%s" % (endnote[k]["author"], endnote[k]["year"], endnote[k]["rec"]))
                            for k in keys) + "\\}"


def cite_text(keys):
    if endnote is not None:
        for k in keys:
            if k not in endnote:
                warn(f"citation {k} has no EndNote record")
        return endnote_cite([k for k in keys if k in endnote])
    nums = []
    for k in keys:
        if k in bibnum:
            nums.append(bibnum[k])
        else:
            warn(f"citation {k} not in aux")
    inner = compress(nums) if nums else "?"
    if cite_mode == "super":
        return "\\textsuperscript{%s}" % inner
    if cite_mode == "super-round":
        return "\\textsuperscript{(%s)}" % inner
    return "(%s)" % inner


def cite(m):
    pre_ws, cmd, keys, punct = m.group(1), m.group(2), m.group(3), m.group(4) or ""
    keys = [k.strip() for k in keys.split(",") if k.strip()]
    if cmd == "citenum":   # a plain number; with EndNote there is no #bibN bookmark to link to
        link = (lambda n: CITE_PREFIX + str(n)) if endnote is not None else citelink
        nums = ", ".join(link(bibnum[k]) if k in bibnum else "?" for k in keys)
        return pre_ws + nums + punct
    if cmd not in ("cite", "citep"):
        warn(f"\\{cmd} converted like \\cite")
    if cite_mode in ("super", "super-round"):
        # natbib superscripts drop the space before them; natmove moves them after . , ; :
        if punct.startswith(".") and doc_ref[0][m.start() - 1:m.start()] == ".":
            punct = punct[1:]                           # natmove: no doubled full stop after "et al."
        return punct + cite_text(keys)
    return pre_ws + cite_text(keys) + punct


doc_ref = [doc]
doc = re.sub(r"(\s*)\\(cite|citep|citet|citenum)\*?\{([^}]+)\}([.,;:])?", cite, doc)


def ref(m):
    k = ("sub@" if m.group(1) == "subref" else "") + m.group(2)
    if k not in labels:
        warn(f"reference {k} not in aux")
        return "??"
    return "(%s)" % labels[k] if m.group(1) == "eqref" else labels[k]


doc = re.sub(r"\\(subref|ref|autoref|eqref)\{([^}]+)\}", ref, doc)
doc = re.sub(r"\\label\{[^}]+\}", "", doc)

# ---------------------------------------------------------------- chemistry: scripts as text, not math


def ce(m):
    return re.sub(r"(?<=[A-Za-z)\]])(\d+)", r"\\textsubscript{\1}", m.group(1))


def ce_math(m):
    return "\\mathrm{" + re.sub(r"(?<=[A-Za-z)\]])(\d+)", r"_{\1}", m.group(1)) + "}"


def math_segments(v, fn):
    pat = r"(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\[.*?\\\]|\\\(.*?\\\)"
    return re.sub(pat, lambda m: fn(m.group(0)), v, flags=re.S)


def script(t):
    return t.replace("-", "\u2212")    # charge: minus sign, as LaTeX math sets it


for t in ("doc", "title"):
    v = globals()[t]
    v = math_segments(v, lambda seg: re.sub(r"\\ce\{([^{}]*)\}", ce_math, seg))
    v = re.sub(r"\\ce\{([^{}]*)\}", ce, v)
    v = re.sub(r"\$\\mathrm\{([A-Za-z]+)\}\^\{([0-9+\-]+)\}\$",
               lambda m: m.group(1) + "\\textsuperscript{%s}" % script(m.group(2)), v)       # $\mathrm{La}^{3+}$
    v = re.sub(r"\$\\mathrm\{([A-Za-z]+)\}_\{\\mathrm\{([A-Za-z]+)\}\}\$",
               r"\1\\textsubscript{\2}", v)                                                   # $\mathrm{O}_{\mathrm{w}}$
    v = re.sub(r"\$_\{?\\mathrm\{([^{}]*)\}\}?\$", r"\\textsubscript{\1}", v)                 # $_\mathrm{W}$
    v = re.sub(r"\$_\{([A-Za-z0-9]+)\}\$", r"\\textsubscript{\1}", v)
    v = re.sub(r"\$_([A-Za-z0-9])\$", r"\\textsubscript{\1}", v)                               # $_3$
    v = re.sub(r"\$\^\{([A-Za-z0-9+\-]+)\}\$", lambda m: "\\textsuperscript{%s}" % script(m.group(1)), v)
    v = re.sub(r"\$\^([A-Za-z0-9])\$", r"\\textsuperscript{\1}", v)                            # nm$^3$
    v = v.replace("$'$", "\u2032").replace("$^\\prime$", "\u2032")
    v = v.replace("\u2013-", "\u2014")   # T1 font ligature: an en dash followed by "-" prints as an em dash
    globals()[t] = v
if "\\ce{" in doc:
    warn("unconverted \\ce{} with nested braces remains")

# ---------------------------------------------------------------- layout markers
doc = re.sub(r"\\(clearpage|newpage)", "\n\nZZPAGEBREAK\n\n", doc)
for c in ("bibliographystyle", "biboptions", "captionsetup"):
    doc = re.sub(r"\\%s\{[^}]*\}" % c, "", doc)

# ---------------------------------------------------------------- bibliography from the mciteplus .bbl
items = re.findall(r"\\bibitem(?:\[(?:[^\[\]]|\[[^\]]*\])*\])?\{([^}]+)\}(.*?)\\EndOfBibitem", bbl, re.S)
refs = []
for n, (key_, txt) in enumerate(items, 1):
    if bibnum.get(key_) != n:
        warn(f"bib order mismatch for {key_}: aux {bibnum.get(key_)} vs bbl position {n}")
    end_punct = "." if "\\mciteBstWouldAddEndPuncttrue" in txt else ""
    txt = txt.split("\\mciteBstWouldAddEndPunct")[0]
    txt = re.sub(r"\\relax\s*$", "", txt.strip())
    txt = re.sub(r"\\newblock\s*", " ", txt)
    txt = re.sub(r"\\doi\{([^}]*)\}", r"\\url{\1}", txt)
    txt = re.sub(r"\\href\s*\{([^}]*)\}\s*\{", r"\\href{\1}{", txt)
    txt = expand_macros(re.sub(r"\s+", " ", txt).strip()) + end_punct
    refs.append(f"ZZBIB{LABEL_MARK}{n}L{CITE_PREFIX}{n}ZZ {txt}")
bib_block = "\\section*{References}\n\n\\begin{bibentries}\n\n" + "\n\n".join(refs) + "\n\n\\end{bibentries}\n"
if endnote is not None:
    bib_block = "\\section*{References}\n"  # EndNote appends its bibliography at the end of the document
doc, nsub = re.subn(r"\\bibliography\{[^}]*\}", lambda m: bib_block, doc)
if nsub > 1:
    warn("more than one \\bibliography command")
if nsub == 0 and bibnum:
    warn("citations but no \\bibliography command")

final = "\\title{%s}\n\\begin{document}\n\\maketitle\n\n%s\n\\end{document}\n" % (title.strip(), doc)
with open(args.out_tex, "w", encoding="utf8") as f:
    f.write(final)
with open(args.out_eq, "w") as f:
    json.dump(eqnums, f)
post_opts = ["--tables"] + (["--page-prefix", PAGE_PREFIX] if PAGE_PREFIX else [])
with open(os.path.join(build, stem + "_post.opts"), "w") as f:
    f.write(" ".join(post_opts) + "\n")
floats = " ".join(f"{k}s={v}" for k, v in counters.items() if v)
print(f"achemso journal={journal} manuscript={manuscript} citations={cite_mode} sections={'on' if sections_on else 'off'}"
      f"{' numbered' if numbered and sections_on else ''} | {floats} equations={len(eqnums)} refs={len(refs)} "
      f"authors={len(authors)} affiliations={len(affils)}+{len(alts)} warnings={len(warnings)}")
