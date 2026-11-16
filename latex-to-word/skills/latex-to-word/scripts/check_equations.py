"""Per display equation: letters, digits and Greek symbols of each \\begin{equation} in the .tex
vs its Word equation (m:t text plus the operator and delimiter characters OMML keeps as
attributes, e.g. the n-ary sum and angle brackets). Works for elsarticle and achemso output.
usage: python3 check_equations.py STEM.tex STEM.docx
"""
import collections, html, re, sys, zipfile

tex, docx = sys.argv[1:3]
GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ", "varepsilon": "ε", "zeta": "ζ",
         "eta": "η", "theta": "θ", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "rho": "ρ",
         "sigma": "σ", "tau": "τ", "phi": "ϕ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "pi": "π",
         "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
         "langle": "⟨", "rangle": "⟩", "sum": "∑", "prod": "∏", "int": "∫", "infty": "∞", "partial": "∂",
         "nabla": "∇", "propto": "∝", "approx": "≈", "pm": "±", "leq": "≤", "geq": "≥", "le": "≤", "ge": "≥", "times": "×"}
FUNCS = ("ln", "log", "exp", "cos", "sin", "tan", "cosh", "sinh", "tanh", "lim", "max", "min")
SYMS = "".join(GREEK.values())
src = re.sub(r"(?<!\\)%.*", "", open(tex, encoding="utf8").read())
eqs = re.findall(r"\\begin\{equation\}(.*?)\\end\{equation\}", src, re.S)
# argument-free user macros (\newcommand{\Ks}{K_\mathrm{s}}), expanded as prep.py does
macros = {}
for m in re.finditer(r"\\(?:re)?newcommand\*?\{?\\([A-Za-z]+)\}?\s*\{", src.split("\\begin{document}")[0]):
    depth, j = 0, m.end() - 1
    for j in range(m.end() - 1, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            break
    macros[m.group(1)] = src[m.end():j]
for _ in range(3):
    eqs = [re.sub(r"\\([A-Za-z]+)(?![A-Za-z])", lambda m: macros.get(m.group(1), m.group(0)), e) for e in eqs]


def latex_chars(e):
    e = re.sub(r"\\label\{[^}]*\}", "", e)
    e = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1), " %s " % m.group(1) if m.group(1) in FUNCS else " "), e)
    return collections.Counter(c for c in e if c.isalnum() or c in SYMS)


xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf8")
paras = re.findall(r"<m:oMathPara>.*?</m:oMathPara>", xml, re.S)
bad = 0
for n, (e, p) in enumerate(zip(eqs, paras), 1):
    txt = "".join(x or y for x, y in re.findall(r"<m:t(?: [^>]*)?>([^<]*)</m:t>|m:(?:chr|begChr|endChr) m:val=\"([^\"]*)\"", p))
    txt = re.sub(r"#[A-Z]?\d+\)?$", "", html.unescape(txt).rstrip("()"))   # Word's "#(n)" or "#(S1)" equation number
    a, b = latex_chars(e), collections.Counter(c for c in txt if c.isalnum() or c in SYMS)
    if a != b:
        bad += 1
        print(f"  ({n}) LaTeX-only {dict(a - b)}  Word-only {dict(b - a)}")
print(f"{tex}: {len(eqs)} equations in LaTeX, {len(paras)} in Word, {bad} with differing symbols")
