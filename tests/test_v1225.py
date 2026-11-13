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
print("  v12.25  no orphaned reference in the app's big renderers")
print("=" * 70)

print("\nA. the defect, fixed")
ok("const spendForTip" in js, "A1  spendForTip is declared again")
ok(js.count("const spendForTip") == 1,
   "A2  /!\\ exactly once - two declarations is the next bug", js.count("const spendForTip"))
# /!\ THE CENSUS POPULATION, in one list.
# v12.27 - adsUpdateChart DRAWS THE ADS TAB TOO, and the next orphan landed
#          in it. A census covering one of two renderers has a hole the size
#          of the other.
# v12.35 - the two Units Sold renderers join it. That release rewrote the
#          dataset loop and the control strip in both, which is precisely the
#          shape of edit that deletes a declaration and leaves its reads
#          behind. A SECOND census would be the hard-rule-#1 defect.
CENSUS_FNS = ["renderAdsCampaigns", "adsUpdateChart",
              "updateSalesChart", "updateChannelChart"]
SRCS = {n: fn_src(n) for n in CENSUS_FNS}
RAC = SRCS["renderAdsCampaigns"]
ok("const spendForTip" in RAC,
   "A3  /!\\ and INSIDE the function that reads it, not a global patched in")
# /!\ GUARDED. A missing declaration must FAIL section A, never crash
# before section B - which is the general census and the part that
# generalises past this one name.
ok("const spendForTip" in RAC and "Math.round(spendForTip)" in RAC
   and RAC.index("const spendForTip") < RAC.index("Math.round(spendForTip)"),
   "A4  /!\\ declared BEFORE its first read")

print("\nB. /!\\ THE CENSUS - every identifier each renderer reads is declared")

# /!\ PER FUNCTION, NOT POOLED. v12.27 concatenated two bodies into one
# `declared` set and v12.35 would have made that four - so a local in ONE
# renderer satisfied a read in ANOTHER, and the suite stayed green with a
# declaration deleted. A function's locals are its own.
def _params(txt):
    """A parameter list, flattened. `([bundleId, comps]) => {` is two
    perfectly good bindings; splitting the brackets in with them made both
    read as orphans, and a false positive costs a census as much as a miss."""
    out = []
    for part in txt.replace("[", " ").replace("]", " ").replace("{", " ").replace("}", " ").split(","):
        t = part.split("=")[0].split(":")[-1].strip().strip(".")
        if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
            out.append(t)
    return out


def _locals_of(src, fname):
    body = strip_noise(src)
    d = set()
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", body):
        d.add(m.group(1))
    for m in re.finditer(r"\b(?:const|let|var)\s*[\[{]([^\]}]*)[\]}]", body):
        for part in re.split(r"[,:]", m.group(1)):
            t = part.strip().strip(".")
            if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
                d.add(t)
    # multi-declarator: `let a = 1, b = 2;`
    for m in re.finditer(r"\b(?:const|let|var)\s+([^;\n]+)", body):
        for part in m.group(1).split(","):
            t = part.split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
                d.add(t)
    for m in re.finditer(r"catch\s*\(\s*([A-Za-z_$][\w$]*)", body):
        d.add(m.group(1))
    for m in re.finditer(r"\(([^()]*)\)\s*=>", body):
        for t in _params(m.group(1)):
            d.add(t)
    for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=>", body):
        d.add(m.group(1))
    for m in re.finditer(r"function\s*\w*\s*\(([^()]*)\)", body):
        for t in _params(m.group(1)):
            d.add(t)
    sig = re.match(r"(?:async\s+)?function\s+" + fname + r"\s*\(([^()]*)\)", src)
    for t in _params(sig.group(1) if sig else ""):
        d.add(t)
    return d, body


# Every top-level binding in the file. RAW source: stripping strings across
# 4.7MB with regexes swallows real code (the v12.25 lesson).
#
# /!\ AND HERE IS WHAT THIS CENSUS DOES NOT DO, written down rather than left
# to be discovered. `^\s*` matches an INDENTED declaration, so every LOCAL in
# the file lands in this set too - which means the check is really "is this
# name declared SOMEWHERE in 4.7MB". That catches a declaration deleted
# OUTRIGHT, which is v12.25's actual defect, and does NOT catch one deleted
# from a function where some other function declares the same name.
#
# Anchoring at column 0 fixes that and was tried: it reported SIX false
# positives immediately - `g` off a regex flag, `$`, and `div` / `total` /
# `range` leaking out of template literals the stripper does not fully
# remove. A census that cries wolf is worse than one with a known hole,
# because it teaches everyone to ignore a red suite. Closing it properly
# needs real scope analysis, not a better regex.
#
# The targeted check lives beside the code that changes: a release that adds
# locals to one of these renderers pins them by name, declared before first
# read, the way section A does for spendForTip.
GLOBALS = set()
for m in re.finditer(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", js):
    GLOBALS.add(m.group(1))
for m in re.finditer(r"(?m)^\s*(?:const|let|var)\s+(.+)$", js):
    for part in m.group(1).split(","):
        t = part.split("=")[0].strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", t or ""):
            GLOBALS.add(t)

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

orphans = {}
for _fn in CENSUS_FNS:
    _d, _body = _locals_of(SRCS[_fn], _fn)
    _used = set()
    for m in re.finditer(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*(?![\w$]*\s*:)", _body):
        _used.add(m.group(1))
    # property names after a dot, and object-literal keys, are not references
    miss = sorted(t for t in _used
                  if t not in _d and t not in GLOBALS and t not in BUILTINS
                  and not re.fullmatch(r"[A-Z][A-Z0-9_]*", t))
    if miss:
        orphans[_fn] = miss

ok(not orphans,
   "B1  /!\\ every identifier each of the %d renderers reads is declared"
   % len(CENSUS_FNS),
   "; ".join("%s: %s" % (k, ", ".join(v[:6])) for k, v in orphans.items()))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
