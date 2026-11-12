#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.25 - a local deleted with the block that declared it.

    X spendForTip is not defined

...and the whole Walmart Ads tab rendered as that one line. v12.20 removed
v12.19's Ceiling ROAS block and took `const spendForTip` out with it, because
the declaration happened to sit inside the deleted span while two READS of it
survived in the TACoS tooltip below.

/!\ `node --check` PASSED IT. Scope is not syntax - the same lesson as v12.16,
and the same cost: a crash in the only thing no test executed.

This suite is the structural answer. It walks `renderAdsCampaigns` - the
function that draws this tab - collects every identifier it READS, and fails
the build on any that is declared neither inside it nor anywhere in the file.
A deletion that orphans a reference cannot ship again.
"""
import io, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % extra) if extra is not None else ""))


def fn_src(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def strip_noise(src):
    src = re.sub(r"/\*[\s\S]*?\*/", " ", src)
    src = re.sub(r"(?m)//.*$", " ", src)
    # template literals, then plain strings
    src = re.sub(r"`(?:[^`\\]|\\.)*`", " ", src)
    src = re.sub(r"'(?:[^'\\\n]|\\.)*'", " ", src)
    src = re.sub(r'"(?:[^"\\\n]|\\.)*"', " ", src)
    return src


print("\n" + "=" * 70)
print("  v12.25  no orphaned reference in the ads renderer")
print("=" * 70)

print("\nA. the defect, fixed")
ok("const spendForTip" in js, "A1  spendForTip is declared again")
ok(js.count("const spendForTip") == 1,
   "A2  /!\\ exactly once - two declarations is the next bug", js.count("const spendForTip"))
RAC = fn_src("renderAdsCampaigns")
# v12.27 - /!\ adsUpdateChart DRAWS THIS TAB TOO, and the next orphan
# landed in it. A census that covers one of two renderers is a census
# with a hole the size of the other.
AUC = fn_src("adsUpdateChart")
ok("const spendForTip" in RAC,
   "A3  /!\\ and INSIDE the function that reads it, not a global patched in")
# /!\ GUARDED. A missing declaration must FAIL section A, never crash
# before section B - which is the general census and the part that
# generalises past this one name.
ok("const spendForTip" in RAC and "Math.round(spendForTip)" in RAC
   and RAC.index("const spendForTip") < RAC.index("Math.round(spendForTip)"),
   "A4  /!\\ declared BEFORE its first read")

print("\nB. /!\\ THE CENSUS - every identifier this renderer reads is declared")
# Declarations visible to the function: its own locals and params, plus every
# top-level binding and function in the file.
body = strip_noise(RAC) + "\n" + strip_noise(AUC)

declared = set()
for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", body):
    declared.add(m.group(1))
# destructuring + for-of/in bindings + catch params + arrow/function params
for m in re.finditer(r"\b(?:const|let|var)\s*[\[{]([^\]}]*)[\]}]", body):
    for part in re.split(r"[,:]", m.group(1)):
        t = part.strip().strip(".")
        if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
            declared.add(t)
for m in re.finditer(r"catch\s*\(\s*([A-Za-z_$][\w$]*)", body):
    declared.add(m.group(1))
for m in re.finditer(r"\(([^()]*)\)\s*=>", body):
    for part in m.group(1).split(","):
        t = part.strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
            declared.add(t)
for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=>", body):
    declared.add(m.group(1))
for m in re.finditer(r"function\s*\w*\s*\(([^()]*)\)", body):
    for part in m.group(1).split(","):
        t = part.strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
            declared.add(t)
# the function's own parameters
for _fn, _src in (("renderAdsCampaigns", RAC), ("adsUpdateChart", AUC)):
    sig = re.match(r"(?:async\s+)?function\s+" + _fn + r"\s*\(([^()]*)\)", _src)
    for part in (sig.group(1) if sig else "").split(","):
        t = part.strip()
        if t:
            declared.add(t)

whole = js  # RAW: see the note above
for m in re.finditer(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", whole):
    declared.add(m.group(1))
for m in re.finditer(r"(?m)^\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)", whole):
    declared.add(m.group(1))
# multi-declarator lines: `let _adsBreakEven = {}, _adsAttribDeflate = {};`
for m in re.finditer(r"(?m)^\s*(?:const|let|var)\s+(.+)$", whole):
    for part in m.group(1).split(","):
        t = part.split("=")[0].strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
            declared.add(t)

BUILTINS = {
    "window", "document", "console", "Math", "Object", "Array", "JSON", "Date",
    "Number", "String", "Boolean", "Promise", "Set", "Map", "RegExp", "Error",
    "isNaN", "parseInt", "parseFloat", "setTimeout", "clearTimeout", "localStorage",
    "requestAnimationFrame", "Intl", "navigator", "location", "encodeURIComponent",
    "decodeURIComponent", "Infinity", "NaN", "undefined", "null", "true", "false",
    "this", "typeof", "new", "return", "if", "else", "for", "of", "in", "while",
    "try", "catch", "const", "let", "var", "function", "async", "await", "break",
    "continue", "switch", "case", "default", "delete", "instanceof", "void",
    "throw", "do", "class", "extends", "super", "yield", "Blob", "URL", "Chart",
    "fetch", "getComputedStyle", "structuredClone", "globalThis", "Symbol",
}

used = set()
for m in re.finditer(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*(?![\w$]*\s*:)", body):
    used.add(m.group(1))
# property names after a dot, and object-literal keys, are not references
missing = sorted(t for t in used
                 if t not in declared and t not in BUILTINS
                 and not re.fullmatch(r"[A-Z][A-Z0-9_]*", t))

ok(not missing,
   "B1  /!\\ every identifier BOTH ads renderers read is declared somewhere",
   ", ".join(missing[:12]))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
