"""Rewrite an elsarticle manuscript into LaTeX that pandoc converts cleanly to docx.

Numbers for sections, figures, equations and citations are taken from the LaTeX run
(main.aux / main.bbl) so the Word file matches the compiled PDF.

usage: python3 prep.py BUILD_DIR STEM OUT.tex EQNUMS.json
  BUILD_DIR must contain STEM.tex, STEM.aux, STEM.bbl and png/<figure>.png (300 dpi renders)
"""
import json
import os
import re
import struct
import sys

build, stem, out_tex, out_eq = sys.argv[1:5]
# optional: JSON {bibkey: {"author", "year", "rec"}} -> EndNote temporary citations instead of numbers
endnote = json.load(open(sys.argv[5], encoding="utf8")) if len(sys.argv) > 5 else None
DPI = 300
TEXTWIDTH_IN = 6.5
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
            j += 2  # skip escaped character, e.g. \{ or \}
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
            continue  # comment-only line: TeX produces nothing, not even a blank line
        out.append(before)  # trailing %: newline is swallowed
    return "".join(out)


src = strip_comments(read(stem + ".tex"))
aux = read(stem + ".aux")
bbl = read(stem + ".bbl")

labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))
bibnum = {k: int(v) for k, v in re.findall(r"\\bibcite\{([^}]+)\}\{\{(\d+)\}", aux)}

pre, rest = src.split("\\begin{document}", 1)
body_all = rest.split("\\end{document}", 1)[0]

# ---------------------------------------------------------------- macros
macros = {}
for m in re.finditer(r"\\(?:re)?newcommand\*?\{?\\([A-Za-z]+)\}?", pre):
    j = skip_ws(pre, m.end())
    if pre[j] == "[":
        macros.setdefault("__witharg__", []).append(m.group(1))
        continue
    val, _ = group(pre, j)
    macros[m.group(1)] = val.replace("\\xspace", "")
witharg = macros.pop("__witharg__", [])


def expand_macros(t):
    for _ in range(3):  # allow nested definitions
        for name, val in macros.items():
            t = re.sub(r"\\%s(?![A-Za-z])(\{\})?" % name, lambda m: val, t)
    for name in witharg:
        if re.search(r"\\%s(?![A-Za-z])" % name, t):
            warn(f"macro with arguments \\{name} used in body; left unexpanded")
    return t


# ---------------------------------------------------------------- front matter
fm_start = body_all.index("\\begin{frontmatter}")
fm_end = body_all.index("\\end{frontmatter}")
fm = body_all[fm_start + len("\\begin{frontmatter}"):fm_end]
body = body_all[fm_end + len("\\end{frontmatter}"):]

title, _ = group(fm, skip_ws(fm, fm.index("\\title") + 6))

authors, affils, corrtext, emails = [], {}, {}, []
for m in re.finditer(r"\\(author|ead|cortext|affiliation)(?![A-Za-z])", fm):
    i = skip_ws(fm, m.end())
    opt = None
    if fm[i] == "[":
        k = fm.index("]", i)
        opt, i = fm[i + 1:k], skip_ws(fm, k + 1)
    arg, _ = group(fm, i)
    kind = m.group(1)
    if kind == "author":
        corr = re.findall(r"\\corref\{([^}]+)\}", arg)
        name = re.sub(r"\\corref\{[^}]+\}", "", arg).strip()
        authors.append({"name": name, "aff": [a.strip() for a in (opt or "").split(",") if a.strip()],
                        "corr": corr, "email": None})
    elif kind == "ead":
        authors[-1]["email"] = arg.strip()
    elif kind == "cortext":
        corrtext[opt] = arg.strip()
    elif kind == "affiliation":
        fields = {}
        for fm_ in re.finditer(r"(\w+)\s*=\s*\{", arg):
            fields[fm_.group(1)], _ = group(arg, fm_.end() - 1)
        order = ["organization", "addressline", "city", "postcode", "state", "country"]
        affils[opt] = ", ".join(fields[k] for k in order if k in fields)

aff_letter = {lab: "abcdefghijklmnopqrstuvwxyz"[i] for i, lab in enumerate(affils)}
corr_order = []
for a in authors:
    for c in a["corr"]:
        if c not in corr_order:
            corr_order.append(c)
corr_sym = {c: "\u2217" * (i + 1) for i, c in enumerate(corr_order)}

author_line = ", ".join(
    a["name"] + "\\textsuperscript{%s}" % ",".join([aff_letter[x] for x in a["aff"]] + [corr_sym[c] for c in a["corr"]])
    for a in authors)
aff_lines = "\n\n".join("\\textsuperscript{%s}%s" % (aff_letter[lab], txt) for lab, txt in affils.items())
corr_lines = ["\\textsuperscript{%s}%s" % (corr_sym[c], corrtext.get(c, "Corresponding author.")) for c in corr_order]
mail = [f"{a['email']} ({a['name']})" for a in authors if a["email"]]
if mail:
    corr_lines.append("\\textit{Email address%s:} " % ("es" if len(mail) > 1 else "") + ", ".join(mail))

abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", fm, re.S).group(1).strip()
kw = re.search(r"\\begin\{keyword\}(.*?)\\end\{keyword\}", fm, re.S)
keywords = ", ".join(k.strip() for k in kw.group(1).split("\\sep")) if kw else None

front = [
    "\\begin{fmauthors}\n" + author_line + "\n\\end{fmauthors}",
    "\\begin{fmaffils}\n" + aff_lines + "\n\\end{fmaffils}",
    "\\begin{fmcorr}\n" + "\n\n".join(corr_lines) + "\n\\end{fmcorr}",
    "\\section*{Abstract}\n" + abstract,
]
if keywords:
    front.append("\\begin{fmkeywords}\n\\textit{Keywords:} " + keywords + "\n\\end{fmkeywords}")
if "\\linenumbers" not in body:
    front.append("ZZSECTIONBREAK")

doc = "\n\n".join(front) + "\n\n" + body
doc = expand_macros(doc)
title = expand_macros(title)

# ---------------------------------------------------------------- figures
fig_no = 0


with open(os.path.join(build, "png", "natural_widths.json")) as f:
    natural_widths = json.load(f)  # written by render_figs.py


def png_width_in(name):
    return natural_widths[name]


def convert_figure(m):
    global fig_no
    fig_no += 1
    env = m.group(1)
    ci = env.index("\\caption")
    cap, cend = group(env, skip_ws(env, ci + len("\\caption")))
    imgs_part = env[:ci] + env[cend:]
    lab = re.findall(r"\\label\{([^}]+)\}", cap + imgs_part)
    for l in lab:
        if labels.get(l) != str(fig_no):
            warn(f"figure label {l}: aux says {labels.get(l)}, sequential count {fig_no}")
    rows = []
    for chunk in re.split(r"\\\\", imgs_part):
        row = []
        for g in re.finditer(r"\\includegraphics\s*(?:\[([^\]]*)\])?\{([^}]+)\}", chunk):
            opts, name = g.group(1) or "", os.path.splitext(os.path.basename(g.group(2)))[0]
            nat = png_width_in(name)
            sc = re.search(r"scale\s*=\s*([\d.]+)", opts)
            wd = re.search(r"width\s*=\s*([\d.]*)\\(textwidth|linewidth)", opts)
            wabs = re.search(r"width\s*=\s*([\d.]+)\s*(cm|mm|in|pt)", opts)
            if sc:
                w = nat * float(sc.group(1))
            elif wd:
                w = TEXTWIDTH_IN * float(wd.group(1) or 1)
            elif wabs:
                w = float(wabs.group(1)) / {"cm": 2.54, "mm": 25.4, "in": 1, "pt": 72.27}[wabs.group(2)]
            else:
                w = min(nat, TEXTWIDTH_IN)
            row.append([name, w])
        if row:
            tot = sum(w for _, w in row)
            if tot > TEXTWIDTH_IN:
                for r in row:
                    r[1] *= TEXTWIDTH_IN / tot
            rows.append(row)
    cap = re.sub(r"\\label\{[^}]+\}", "", cap).strip()
    lines = ["".join("\\includegraphics[width=%.3fin]{png/%s.png}" % (w, n) for n, w in row) for row in rows]
    return ("\\begin{figure}\n\\centering\n" + "\\\\\n".join(lines) +
            "\n\\caption{Figure %d: %s}\n\\end{figure}" % (fig_no, cap))


doc = re.sub(r"\\begin\{figure\*?\}(?:\[[^\]]*\])?(.*?)\\end\{figure\*?\}", convert_figure, doc, flags=re.S)
if re.search(r"\\begin\{table", doc):
    warn("tables present; they are passed to pandoc unchanged")

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
counters = [0, 0, 0]


def convert_heading(m):
    level = {"section": 0, "subsection": 1, "subsubsection": 2}[m.group(1)]
    text, end = group(doc_ref[0], m.end() - 1)
    text_labels = re.findall(r"\\label\{([^}]+)\}", text)
    text = re.sub(r"\\label\{[^}]+\}", "", text).strip()
    if m.group(2):  # starred
        return "\\%s*{%s}" % (m.group(1), text), end
    counters[level] += 1
    for k in range(level + 1, 3):
        counters[k] = 0
    num = ".".join(str(c) for c in counters[:level + 1])
    for l in text_labels:
        if labels.get(l) != num:
            warn(f"section label {l}: aux says {labels.get(l)}, computed {num}")
    return "\\%s*{%s. %s}" % (m.group(1), num, text), end


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

# ---------------------------------------------------------------- citations / references


def citelink(n):
    # internal link to the bookmark elsarticle.lua puts on reference entry n (as hyperref does)
    return "\\hyperlink{bib%d}{%d}" % (n, n)


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
    return ", ".join(parts)


def tex_escape(t):
    return re.sub(r"([&%#_$])", r"\\\1", t)


def endnote_cite(keys):
    """{Author, Year #Rec;...}: EndNote's unformatted citation, resolved by Update Citations."""
    keys = sorted(keys, key=lambda k: bibnum.get(k, 0))
    return "\\{" + ";".join(tex_escape("%s, %s #%s" % (endnote[k]["author"], endnote[k]["year"], endnote[k]["rec"]))
                            for k in keys) + "\\}"


def cite(m):
    keys = [k.strip() for k in m.group(1).split(",")]
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
    return "[" + (compress(nums) if nums else "?") + "]"


doc = re.sub(r"\\cite[pt]?\{([^}]+)\}", cite, doc)


def ref(m):
    k = m.group(1)
    if k not in labels:
        warn(f"reference {k} not in aux")
        return "??"
    return labels[k]


doc = re.sub(r"\\(?:ref|autoref|eqref)\{([^}]+)\}", ref, doc)
doc = re.sub(r"\\label\{[^}]+\}", "", doc)

# ---------------------------------------------------------------- chemistry / text subscripts


def ce(m):
    return re.sub(r"(?<=[A-Za-z)\]])(\d+)", r"\\textsubscript{\1}", m.group(1))


def ce_math(m):
    return "\\mathrm{" + re.sub(r"(?<=[A-Za-z)\]])(\d+)", r"_{\1}", m.group(1)) + "}"


def math_segments(v, fn):
    """apply fn to the contents of $...$, \\[...\\] and \\(...\\) math only."""
    pat = r"(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\[.*?\\\]|\\\(.*?\\\)"
    return re.sub(pat, lambda m: fn(m.group(0)), v, flags=re.S)


for t in ("doc", "title"):
    v = globals()[t]
    v = math_segments(v, lambda seg: re.sub(r"\\ce\{([^{}]*)\}", ce_math, seg))
    v = re.sub(r"\\ce\{([^{}]*)\}", ce, v)
    v = re.sub(r"\$_\{?\\mathrm\{([^{}]*)\}\}?\$", r"\\textsubscript{\1}", v)
    v = re.sub(r"\$_\{([A-Za-z0-9]+)\}\$", r"\\textsubscript{\1}", v)
    v = re.sub(r"\$\^\{([A-Za-z0-9+\-]+)\}\$", r"\\textsuperscript{\1}", v)
    v = v.replace("$'$", "\u2032").replace("$^\\prime$", "\u2032")
    globals()[t] = v
if "\\ce{" in doc:
    warn("unconverted \\ce{} with nested braces remains")

# ---------------------------------------------------------------- layout markers
doc = doc.replace("\\linenumbers", "\n\nZZSECTIONBREAK\n\n")
doc = re.sub(r"\\(clearpage|newpage)", "\n\nZZPAGEBREAK\n\n", doc)
for c in ("bibliographystyle", "biboptions"):
    doc = re.sub(r"\\%s\{[^}]*\}" % c, "", doc)

# ---------------------------------------------------------------- bibliography from .bbl
items = re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})", bbl, re.S)
refs = []
for n, (key, txt) in enumerate(items, 1):
    if bibnum.get(key) != n:
        warn(f"bib order mismatch for {key}: aux {bibnum.get(key)} vs bbl position {n}")
    txt = re.sub(r"\\newblock\s*", " ", txt)
    txt = re.sub(r"\\newline\s*", " ", txt)
    txt = txt.replace("\\urlprefix", "URL ")
    txt = re.sub(r"\\href\s*\{([^}]*)\}\s*\{", r"\\href{\1}{", txt)
    txt = re.sub(r"\\path\{([^}]*)\}", r"\1", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    refs.append(f"ZZBIB{n}ZZ {txt}")
bib_block = "\\section*{References}\n\n\\begin{bibentries}\n\n" + "\n\n".join(refs) + "\n\n\\end{bibentries}\n"
if endnote is not None:
    bib_block = "\\section*{References}\n"  # EndNote appends its bibliography at the end of the document
doc, nsub = re.subn(r"\\bibliography\{[^}]*\}", lambda m: bib_block, doc)
if nsub != 1:
    warn("\\bibliography command not found; references appended at end")
    doc += "\n\n" + bib_block

final = "\\title{%s}\n\\begin{document}\n\\maketitle\n\n%s\n\\end{document}\n" % (title.strip(), doc)
with open(out_tex, "w", encoding="utf8") as f:
    f.write(final)
with open(out_eq, "w") as f:
    json.dump(eqnums, f)
print(f"figures={fig_no} equations={len(eqnums)} refs={len(refs)} authors={len(authors)} warnings={len(warnings)}")
