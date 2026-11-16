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
  temporary citations. Also writes BUILD_DIR/STEM_post.opts (options for post.py) and
  BUILD_DIR/STEM_tables.json (the rules and \tabcolsep of each table).
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
# natbib: \bibcite{key}{{num}{year}{{short authors}}{{long authors}}} -> what \citeauthor prints
bibauthor = {}
for m in re.finditer(r"\\bibcite\{([^}]+)\}\{", aux):
    fields, i = [], m.end()
    while i < len(aux) and aux[i] == "{" and len(fields) < 3:
        v, i = group(aux, i)
        fields.append(v)
    if len(fields) == 3:
        bibauthor[m.group(1)] = re.sub(r"^\{(.*)\}$", r"\1", fields[2], flags=re.S)

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
\acsprobe{tocname}{\expandafter\strip@prefix\meaning\tocentryname}
\acsprobe{tocprint}{\expandafter\strip@prefix\meaning\acs@tocentry@print}
\acsprobe{absextras}{\expandafter\strip@prefix\meaning\acs@abstract@extras}
\@for\acs@tmp:={figure,scheme,chart,graph,table,section,equation}\do{%
  \acsprobe{the\acs@tmp}{\expandafter\expandafter\expandafter\strip@prefix\expandafter\meaning\csname the\acs@tmp\endcsname}}
\makeatother
"""
raw_pre = read(stem + ".tex").split("\\begin{document}", 1)[0]
probe_tex = os.path.join(build, stem + "_acsprobe.tex")
open(probe_tex, "w", encoding="utf8").write(raw_pre + "\\begin{document}\n" + PROBE + "\\end{document}\n")
r = subprocess.run(["pdflatex", "-draftmode", "-interaction=nonstopmode", os.path.basename(probe_tex)],
                   cwd=build, capture_output=True, text=True, errors="replace",
                   env=dict(os.environ, max_print_line="100000"))   # one probe, one line
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


def probe_prefix(kind):
    return re.sub(r"\\.*", "", probe.get("the" + kind, "->").split("->", 1)[-1]).strip()   # "S\@arabic..." -> "S"


def float_prefix(kind):
    if args.prefix != "auto":
        return "" if args.prefix == "none" else args.prefix
    return probe_prefix(kind)


SEC_PREFIX, EQ_PREFIX = probe_prefix("section"), probe_prefix("equation")   # \renewcommand\thesection{S\arabic{section}}


suppinfo = manuscript == "suppinfo"
for k in ("keywords", "abbreviations"):
    # printed with keywords=true, or by journals whose .cfg prints them after the abstract (jpclcd)
    extras = probe.get("absextras", "")
    always = "%s@print" % k in extras and "ifacs@%s" % k not in extras
    if (probe.get(k) == "true" or always) and re.search(r"\\%s\s*\{" % k, pre):
        warn(f"{k}: achemso prints the {k} here ({k}=true or the journal .cfg); not reproduced, add them by hand")

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

# TOC entry: achemso prints it under \tocentryname in a frame (render_figs_achemso.py typesets
# the frame as one picture), on a page of its own at the end of the document; some journals'
# .cfg print it after the abstract instead (e.g. J. Phys. Chem. Lett.)
toc_json = os.path.join(build, "png", stem + "_toc.json")
toc_fig = json.load(open(toc_json)) if "\\begin{tocentry}" in body and os.path.exists(toc_json) else None
toc_name = probe.get("tocname", "TOC Graphic").strip()
for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\tocentryname\}?\s*\{", src):
    toc_name, _ = group(src, m.end() - 1)                  # \renewcommand*{\tocentryname}{...}, also in the body
toc_at_end = "AtEndDocument" in probe.get("tocprint", "AtEndDocument")
if "\\begin{tocentry}" in body and toc_fig is None:
    warn("tocentry present but not rendered (png/%s_toc.json missing): run render_figs_achemso.py" % stem)


def toc_block(heading_prefix=""):
    if toc_fig is None:
        return ""
    return ("\\section*{%s%s}\n\n\\begin{tocgraphic}\n\\includegraphics[width=%.3fin]{png/%s.png}\n\\end{tocgraphic}\n"
            % (heading_prefix, expand_macros(toc_name), toc_fig["width_in"], toc_fig["name"]))


body = re.sub(r"\\begin\{tocentry\}.*?\\end\{tocentry\}", "", body, flags=re.S)
# headings achemso always prints (\acs@section*), even with \SectionsOff
ALWAYS = "ZZACSHEADING"
toc_after_abstract = "" if toc_at_end else "\n\n" + toc_block(ALWAYS)
body, n_abs = re.subn(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                      lambda m: ("\\section*{%sAbstract}\n" % ALWAYS + m.group(1).strip() if abstract_on else "")
                      + toc_after_abstract, body, flags=re.S)
if toc_after_abstract and not n_abs:
    body = toc_after_abstract + "\n\n" + body
for env, name in (("acknowledgement", "Acknowledgement"), ("suppinfo", "Supporting Information Available")):
    body = re.sub(r"\\begin\{%s\}(.*?)\\end\{%s\}" % (env, env),
                  lambda m: "\\section*{%s%s}\n" % (ALWAYS, name) + m.group(1).strip(), body, flags=re.S)
if re.search(r"\\footnote(?![A-Za-z])", body):
    warn("\\footnote: achemso turns footnotes into reference-list notes; not reproduced, check by hand")

def tex_file(name):
    for p in (name, name + ".tex"):
        if os.path.isfile(os.path.join(build, p)):
            return p
    return None


def resolve_inputs(t):
    """\\IfFileExists{f}{yes}{no} as LaTeX decides it in the build folder, then \\input{f} inlined."""
    for _ in range(5):
        out, pos, changed = [], 0, False
        for m in re.finditer(r"\\IfFileExists\s*\{", t):
            if m.start() < pos:
                continue
            f, i = group(t, m.end() - 1)
            yes, i = group(t, skip_ws(t, i))
            no, i = group(t, skip_ws(t, i))
            out.append(t[pos:m.start()] + (yes if tex_file(f.strip()) else no))
            pos, changed = i, True
        t = "".join(out) + t[pos:]

        def inline(m):
            f = tex_file(m.group(1).strip())
            if f is None:
                warn(f"\\input{{{m.group(1)}}}: file not found in the build folder")
                return m.group(0)
            return strip_comments(read(f))
        t, n = re.subn(r"\\(?:input|include)\{([^}]+)\}", inline, t)
        if not changed and not n:
            break
    return t


doc = "\n\n".join(front) + "\n\n" + body
doc = expand_macros(resolve_inputs(expand_macros(doc)))
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
        table_rules.extend([None] * len(tabs))
        return m.group(0)
    spec, si = group(env, tabs[0].end())
    rows = env[si:env.index("\\end{tabular}")]
    rules = rules_of(rows)
    sep = re.search(r"\\setlength\s*\{?\\tabcolsep\}?\s*\{\s*([\d.]+)\s*pt\s*\}", env[:tabs[0].start()])
    if sep:
        rules["colsep_pt"] = float(sep.group(1))   # \setlength{\tabcolsep}{3pt}: Word cell margins
    table_rules.append(rules)
    rows = re.sub(r"\\(addlinespace|cmidrule)(\([^)]*\))?(\[[^\]]*\])?(\{[^}]*\})?", "", tnote(rows))
    rows = re.sub(r"\\cline\{[^}]*\}", "", rows)
    # indents such as "\quad on them": a literal em space, which pandoc keeps at the start of a cell
    rows = re.sub(r"\\qquad(?![A-Za-z])\s*", "\u2003\u2003", rows)
    rows = re.sub(r"\\quad(?![A-Za-z])\s*", "\u2003", rows)
    notes = []
    # text set below the tabular without threeparttable (e.g. "$^a$ Measured at 298 K."):
    # full-width notes, centred as achemso sets the float
    foot = env[env.index("\\end{tabular}") + len("\\end{tabular}"):]
    foot = re.sub(r"\\(footnotesize|small|scriptsize|centering|par|medskip|smallskip|bigskip)(?![A-Za-z])", "", foot)
    foot = re.sub(r"\\(vspace|setlength)\*?\{[^}]*\}(\{[^}]*\})?|\\label\{[^}]*\}", "", foot)
    foot = re.sub(r"\\begin\{tablenotes\}.*?\\end\{tablenotes\}", "", foot, flags=re.S)
    foot = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", foot)]
    foot = [p for p in foot if p and not re.fullmatch(r"\\end\{threeparttable\}", p)]
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
    if foot:
        out += "\n\\begin{tablefoot}\n" + "\n\n".join(foot) + "\n\\end{tablefoot}\n"
    return out


def rules_of(rows):
    """Rules inside a tabular, for post.py: {"top", "bottom": "thick"|"thin"|None,
    "mid": [[after_row, first_col, last_col], ...]} (rows and columns from 0; last_col -1 = all)."""
    toks = re.finditer(r"\\(toprule|midrule|bottomrule|hline)(?:\[[^\]]*\])?|\\(cline|cmidrule)(?:\([^)]*\))?(?:\[[^\]]*\])?"
                       r"\{(\d+)-(\d+)\}|(?<!\\)\\\\(?:\[[^\]]*\])?", rows)
    n, mid, top, last_rule, pending = 0, [], None, None, []
    for t in toks:
        if t.group(0).startswith("\\\\"):
            n += 1
            pending = []
            continue
        kind = t.group(1) or t.group(2)
        weight = "thick" if kind in ("toprule", "bottomrule") else "thin"
        if n == 0:
            top = weight
            continue
        if kind in ("cline", "cmidrule"):
            rule = [n - 1, int(t.group(3)) - 1, int(t.group(4)) - 1]
        else:
            rule = [n - 1, 0, -1]
        mid.append(rule)
        pending.append(rule)
        last_rule = weight
    # rules after the last row are the bottom rule, not a rule under that row
    bottom = None
    if pending:
        for r in pending:
            mid.remove(r)
        bottom = last_rule
    return {"top": top, "bottom": bottom, "mid": mid}


table_rules = []


doc = re.sub(r"\\begin\{table\*?\}(?:\[[^\]]*\])?(.*?)\\end\{table\*?\}", convert_table, doc, flags=re.S)

# ---------------------------------------------------------------- equations
eqnums = []


def convert_eq(m):
    n = EQ_PREFIX + str(len(eqnums) + 1)
    inner = m.group(1)
    for l in re.findall(r"\\label\{([^}]+)\}", inner):
        if labels.get(l) != n:
            warn(f"equation label {l}: aux says {labels.get(l)}, sequential count {n}")
    inner = re.sub(r"\\label\{[^}]+\}", "", inner).strip()
    eqnums.append(n)
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
    num = SEC_PREFIX + ".".join(str(c) for c in sec[:level + 1])
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


def citeauthor(m):
    keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
    for k in keys:
        if k not in bibauthor:
            warn(f"\\citeauthor{{{k}}}: not in aux")
    return ", ".join(bibauthor.get(k, "?") for k in keys)


doc = re.sub(r"\\citeauthor\{([^}]+)\}", citeauthor, doc)
if re.search(r"\\(citeauthor\*|citeyear|citealt|Citeauthor)", doc):
    warn("\\citeauthor*, \\citeyear, \\citealt or \\Citeauthor present: not converted, check by hand")
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
    # U^*: LaTeX sets math * as the asterisk operator (U+2217); pandoc writes "*" even for \ast
    v = math_segments(v, lambda seg: re.sub(r"\^\s*(\{\s*(\*|\\ast)\s*\}|\*|\\ast(?![A-Za-z]))", "^{\u2217}", seg))
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
doc = re.sub(r"\\FloatBarrier(?![A-Za-z])", "", doc)
# T1 letters pandoc does not know
for c, u in (("DJ", "\u0110"), ("dj", "\u0111"), ("NG", "\u014a"), ("ng", "\u014b")):
    doc = re.sub(r"\\%s(?![A-Za-z])(\{\}|[ \t]+)?" % c, u, doc)

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
    if toc_fig and toc_at_end:
        bib_block = "\n\nZZPAGEBREAK\n\n" + toc_block() + "\n\nZZPAGEBREAK\n\n" + bib_block
        print("EndNote: the TOC entry stands before References, since EndNote appends the bibliography at "
              "the end; move it after the bibliography once EndNote has updated it")
doc, nsub = re.subn(r"\\bibliography\{[^}]*\}", lambda m: bib_block, doc)
if nsub > 1:
    warn("more than one \\bibliography command")
if nsub == 0 and bibnum:
    warn("citations but no \\bibliography command")

if toc_fig and toc_at_end and endnote is None:
    doc += "\n\nZZPAGEBREAK\n\n" + toc_block()                # \AtEndDocument: a page of its own
final = "\\title{%s}\n\\begin{document}\n\\maketitle\n\n%s\n\\end{document}\n" % (title.strip(), doc)
with open(args.out_tex, "w", encoding="utf8") as f:
    f.write(final)
with open(args.out_eq, "w") as f:
    json.dump(eqnums, f)
with open(os.path.join(build, stem + "_tables.json"), "w") as f:
    json.dump(table_rules, f)
post_opts = ["--tables", "--rules", stem + "_tables.json"] + \
    (["--page-prefix", PAGE_PREFIX] if PAGE_PREFIX else [])
with open(os.path.join(build, stem + "_post.opts"), "w") as f:
    f.write(" ".join(post_opts) + "\n")
floats = " ".join(f"{k}s={v}" for k, v in counters.items() if v)
print(f"achemso journal={journal} manuscript={manuscript} citations={cite_mode} sections={'on' if sections_on else 'off'}"
      f"{' numbered' if numbered and sections_on else ''} | {floats} equations={len(eqnums)} refs={len(refs)} "
      f"{'toc=' + ('end ' if toc_at_end else 'abstract ') if toc_fig else ''}"
      f"authors={len(authors)} affiliations={len(affils)}+{len(alts)} warnings={len(warnings)}")
