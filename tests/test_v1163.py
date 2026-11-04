#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" v11.63 - the version chip is the DEPLOY INDICATOR, so it has to be true.

Jason: "github hasn't deployed."

It had. The live file was byte-identical to HEAD 61 seconds after the v11.62
commit, and carried every v11.58-v11.62 marker. The chip said v11.57, which is
the only thing on screen that answers "did my push land", so five shipped
releases read as a failed deploy.

NINETEEN assertions across fifteen suites were checking that chip at the time
and every one of them was green, because v11.39 converted them from a literal
to `>v11\\.\\d+ <dot> [\\d-]+<` - a shape check. It proves the chip has SOME
version, never the RIGHT one.

This suite checks the VALUE without pinning a literal, by requiring the chip
and CLAUDE.md's own "current version" line to AGREE. That never needs editing
on a bump and goes red exactly when the two drift - which is the defect.
"""
import io, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1163_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
doc = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", newline="").read()

D = chr(0x00b7)          # /!\ via chr(), never pasted and never escaped (v11.41)
CHIP_RE = r">v11\.\d+ " + re.escape(D) + r" [\d-]+<"

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


# ===========================================================================
print("\nA. The chip exists, once, and is well formed")
# ===========================================================================
chips = re.findall(CHIP_RE, s)
eq("A1  exactly one version chip", len(chips), 1)
chip = chips[0] if chips else ""
m = re.match(r">v(11\.\d+) " + re.escape(D) + r" (\d{4}-\d{2}-\d{2})<", chip)
ok(m is not None, "A2  chip is `vN.NN <dot> YYYY-MM-DD`", chip)
chip_ver, chip_date = (m.group(1), m.group(2)) if m else ("", "")

# ===========================================================================
print("\nB. /!\\ THE CHIP AGREES WITH CLAUDE.md - the whole point of this suite")
# ===========================================================================
# CLAUDE.md names the shipping release in one place. Two hand-typed spellings
# of one fact is the rule #1 divergence; there is no build step in a
# single-file app to derive one from the other, so they are converged by
# ASSERTION instead. This is the only assertion in the repo that reads the
# chip's VALUE, and it needs no edit on a bump.
decl = re.findall(r"current version \*\*v(11\.\d+)\*\*", doc)
eq("B1  CLAUDE.md declares the current version exactly once", len(decl), 1)
doc_ver = decl[0] if decl else ""
eq("B2  the chip and CLAUDE.md name the SAME release", chip_ver, doc_ver)

# The newest `## vN.NN` entry in CLAUDE.md is that same release, so a bumped
# version line with no entry behind it does not pass either.
entries = re.findall(r"(?m)^## v(11\.\d+)\b", doc)
ok(entries and entries[0] == doc_ver,
   "B3  the newest CLAUDE.md entry is that release too",
   entries[0] if entries else None)

# ===========================================================================
print("\nC. /!\\ THE OLD GUARD, REPRODUCED - it passes on a stale chip")
# ===========================================================================
# Not a claim that the shape check was vacuous: the measurement.
STALE = s.replace(chip, ">v11.00 " + D + " 1999-01-01<", 1)
ok(len(re.findall(CHIP_RE, STALE)) == 1,
   "C1  a chip reading v11.00 from 1999 still satisfies the SHAPE check")
stale_ver = re.match(r">v(11\.\d+)", ">v11.00 " + D + " 1999-01-01<").group(1)
ok(stale_ver != doc_ver,
   "C2  ...while THIS suite's agreement check rejects it")
# And the converse: a chip that is merely absent must fail the shape check, so
# C1 is not reporting that the pattern matches anything at all.
GONE = s.replace(chip, ">dashboard<", 1)
eq("C3  a MISSING chip does fail the shape check",
   len(re.findall(CHIP_RE, GONE)), 0)

# ===========================================================================
print("\nD. The date is a date, and the provenance comments are NOT the chip")
# ===========================================================================
y, mo, dy = (int(x) for x in chip_date.split("-")) if chip_date else (0, 0, 0)
ok(2025 <= y <= 2100 and 1 <= mo <= 12 and 1 <= dy <= 31,
   "D1  the chip's date is a plausible calendar date", chip_date)

# /!\ A `// vN.NN - ...` source comment records WHEN A MECHANISM ARRIVED and
# must never be swept along with the chip. v11.58 learned the same thing about
# tooltips: the UI carries no release numbers, the SOURCE carries them all.
prov = len(re.findall(r"// v11\.\d+ ", s))
ok(prov >= 40, "D2  source provenance markers survive in bulk", prov)
ok(re.search(r">v11\.\d+ " + re.escape(D) + r" [\d-]+<", s) is not None
   and s.count("v11." + chip_ver.split(".")[1]) >= 1,
   "D3  the chip's own version is spelled in the markup")

# ===========================================================================
print("\nE. The file still parses")
# ===========================================================================
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)
p = os.path.join(SP, "app.js")
io.open(p, "w", encoding="utf-8", newline="").write(js)
r = subprocess.run(["node", "--check", p], capture_output=True, text=True, encoding="utf-8")
eq("E1  node --check clean", r.returncode, 0)

print("\n%s  %d passed, %d failed" % ("PASS" if not failed else "FAIL", passed, failed))
sys.exit(1 if failed else 0)
