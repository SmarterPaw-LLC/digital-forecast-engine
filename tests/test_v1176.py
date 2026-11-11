#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.76 - the upload guard measures a file against the file that came
before IT, and a failed coverage read can be retried.

Jason, on an FBA Inventory upload: "the amazon fba inventory keeps giving me
this warning. i think it is showing all canada, or canada meow instead of
dog." Then, on the coverage grid beside it: "also wtf is this message? why
can't we get this upload messaging correct?"

He is right on both. These files arrive ONE BRAND AT A TIME, and v11.44's
size check held only the REGION constant, so a CA Doggijuana file of 21
ASINs was measured against CA 2026-11-03 = Meowijuana (22) + Kitty Ka-Zoom
(21) = 43, and reported a 51% drop. That brand's own previous file had 21.

  * A  the real uploadGuardBaseline on the REAL CA history: the session that
       actually matches, the tie-break, the overlap floor, and what happens
       with no session column at all.
  * B  /!\ THE DEFECT REPRODUCED - v11.44's size rule run beside the shipped
       one on the rows that produced the warning in Jason's screenshot.
  * C  the real uploadGuardCheck end to end: his upload raises NOTHING, a
       genuinely truncated file still warns, and the twin check still fires.
  * D  check 2 says exactly which rows the upsert replaces.
  * E  static: the coverage retry is wired, and the retired rule is gone from
       live code but survives in a comment.
"""
import io, os, re, sys, json, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

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


def nocomment(t):
    # LINE comments only - v11.63: block-stripping index.html eats 824,674
    # characters, because a `/*` inside a string pairs with a distant `*/`.
    return re.sub(r"(?m)^\s*//.*$", "", t)


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name, kw="function"):
    pat = kw + " " + name + "("
    i = js.index(pat)
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("{", i)] + _bal(js.index("{", i)) + ";"


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("v11.76 - a file is measured against the file that came before IT")
print("=" * 68)

NC = nocomment(js)

# The REAL rows, read off fba_inventory_snapshots for region CA on
# 2026-11-09. [asin, snapshot_date, uploaded_at, afn_fulfillable_quantity]
CA = json.loads(r"""[["B00U6DJCR8","2026-11-02","2026-11-02 23:21:09",415],["B00U6EGXGK","2026-11-02","2026-11-02 23:21:09",1536],["B00U869UMK","2026-11-02","2026-11-02 23:21:09",794],["B00U86E6Z6","2026-11-02","2026-11-02 23:21:09",2127],["B0108I6PZC","2026-11-02","2026-11-02 23:21:09",0],["B017ME6VMW","2026-11-02","2026-11-02 23:21:09",116],["B01MEEJAML","2026-11-02","2026-11-02 23:21:09",0],["B07KPRTSMT","2026-11-02","2026-11-02 23:21:09",5654],["B07WGHX6M3","2026-11-02","2026-11-02 23:21:09",3185],["B081ZDBFXP","2026-11-02","2026-11-02 23:21:09",261],["B0844RR5FH","2026-11-02","2026-11-02 23:21:09",153],["B08W24837G","2026-11-02","2026-11-02 23:21:09",123],["B08ZGL2CNL","2026-11-02","2026-11-02 23:21:09",106],["B08ZGZDYFG","2026-11-02","2026-11-02 23:21:09",26],["B08ZHDPPNH","2026-11-02","2026-11-02 23:21:09",113],["B0BL5MM9V5","2026-11-02","2026-11-02 23:21:09",26],["B0BL5P83QD","2026-11-02","2026-11-02 23:21:09",40],["B0BSM9K4CH","2026-11-02","2026-11-02 23:21:09",39],["B0BSMBZN6Y","2026-11-02","2026-11-02 23:21:09",35],["B0BSMC7RWX","2026-11-02","2026-11-02 23:21:09",0],["B0BSMP5RL3","2026-11-02","2026-11-02 23:21:09",63],["B0BSMQF7C5","2026-11-02","2026-11-02 23:21:09",15],["B0BV3DYBR3","2026-11-02","2026-11-02 23:21:09",745],["B0C1QKDPRM","2026-11-02","2026-11-02 23:21:09",54],["B0C1QV5B9P","2026-11-02","2026-11-02 23:21:09",18],["B0C1QWRDT8","2026-11-02","2026-11-02 23:21:09",65],["B0C1QYBG5Y","2026-11-02","2026-11-02 23:21:09",39],["B0C1T4VQWV","2026-11-02","2026-11-02 23:21:09",0],["B0C1T81NMW","2026-11-02","2026-11-02 23:21:09",17],["B0CLPFTC7K","2026-11-02","2026-11-02 23:21:09",0],["B0D9PMWYGM","2026-11-02","2026-11-02 23:21:09",34],["B0D9PN38GG","2026-11-02","2026-11-02 23:21:09",23],["B0D9PNDC1Q","2026-11-02","2026-11-02 23:21:09",0],["B0D9ZHY9TF","2026-11-02","2026-11-02 23:21:09",0],["B0D9ZLLH9C","2026-11-02","2026-11-02 23:21:09",128],["B0DKVFG2RF","2026-11-02","2026-11-02 23:21:09",266],["B0DKVHHPDZ","2026-11-02","2026-11-02 23:21:09",0],["B0DKVHP6MS","2026-11-02","2026-11-02 23:21:09",0],["B0DKVNCGJ6","2026-11-02","2026-11-02 23:21:09",27],["B0DL1LCWQ3","2026-11-02","2026-11-02 23:21:09",16],["B0DL72SKBS","2026-11-02","2026-11-02 23:21:09",0],["B0DNLGFDBJ","2026-11-02","2026-11-02 23:21:09",147],["B0DNLQ49TS","2026-11-02","2026-11-02 23:21:09",42],["B0DNLVN8JY","2026-11-02","2026-11-02 23:21:09",12],["B0DQF8R5XL","2026-11-02","2026-11-02 23:21:09",926],["B0DYKD1S8V","2026-11-02","2026-11-02 23:21:09",139],["B0F69Y3YKP","2026-11-02","2026-11-02 23:21:09",28],["B0F6B4BXJR","2026-11-02","2026-11-02 23:21:09",78],["B0FFTS34FF","2026-11-02","2026-11-02 23:21:09",16],["B0FGKK9FFG","2026-11-02","2026-11-02 23:21:09",0],["B0FGKNPX45","2026-11-02","2026-11-02 23:21:09",29],["B0FGKQY7SM","2026-11-02","2026-11-02 23:21:09",0],["B0FGL9Q5W2","2026-11-02","2026-11-02 23:21:09",174],["B0FGLJ4MR2","2026-11-02","2026-11-02 23:21:09",33],["B0FGLJHD3N","2026-11-02","2026-11-02 23:21:09",41],["B0FGLNL5L6","2026-11-02","2026-11-02 23:21:09",37],["B0FGLQ32YD","2026-11-02","2026-11-02 23:21:09",0],["B0FH7LWFBR","2026-11-02","2026-11-02 23:21:09",29],["B0FN8FMTZ3","2026-11-02","2026-11-02 23:21:09",204],["B0FR8XSWS2","2026-11-02","2026-11-02 23:21:09",41],["B0FR9C8PX5","2026-11-02","2026-11-02 23:21:09",79],["B0FR9CD1CG","2026-11-02","2026-11-02 23:21:09",0],["B0FR9GXP8K","2026-11-02","2026-11-02 23:21:09",1],["B0FR9GYG6K","2026-11-02","2026-11-02 23:21:09",0],["B0FR9KBCMW","2026-11-02","2026-11-02 23:21:09",64],["B0FR9S9G21","2026-11-02","2026-11-02 23:21:09",75],["B0FR9SSDB3","2026-11-02","2026-11-02 23:21:09",303],["B0FR9V5YN6","2026-11-02","2026-11-02 23:21:09",35],["B0FVG6YHGW","2026-11-02","2026-11-02 23:21:09",19],["B0FVGCFNVQ","2026-11-02","2026-11-02 23:21:09",30],["B0G3D17RJ1","2026-11-02","2026-11-02 23:21:09",66],["B0G3D2DLJW","2026-11-02","2026-11-02 23:21:09",67],["B0GXLQD7DQ","2026-11-02","2026-11-02 23:21:09",44],["B0GXLTHJ2R","2026-11-02","2026-11-02 23:21:09",68],["B0GXLWDHL8","2026-11-02","2026-11-02 23:21:09",73],["B0GXLYYVBT","2026-11-02","2026-11-02 23:21:09",38],["B0GXM5FTQS","2026-11-02","2026-11-02 23:21:09",73],["B0GXMK2H6T","2026-11-02","2026-11-02 23:21:09",45],["B0HBR9JB81","2026-11-02","2026-11-02 23:21:09",194],["B0HBRB2ZR3","2026-11-02","2026-11-02 23:21:09",85],["B0HBRF6ZPZ","2026-11-02","2026-11-02 23:21:09",230],["B0HBRN8MQ3","2026-11-02","2026-11-02 23:21:09",59],["B0HBRQJHBQ","2026-11-02","2026-11-02 23:21:09",45],["B0HBRVF18K","2026-11-02","2026-11-02 23:21:09",98],["B0HBRVTD66","2026-11-02","2026-11-02 23:21:09",42],["B0HJDBGVVW","2026-11-02","2026-11-02 23:21:09",15],["B0HJDDN85X","2026-11-02","2026-11-02 23:21:09",20],["B0HJDGDXM4","2026-11-02","2026-11-02 23:21:09",36],["B0HNWX96D6","2026-11-02","2026-11-02 23:21:09",0],["B0HNWZCKTB","2026-11-02","2026-11-02 23:21:09",0],["B0CYJX7L6M","2026-11-02","2026-11-02 23:21:31",0],["B0CYJY8DJN","2026-11-02","2026-11-02 23:21:31",0],["B0CYK66K6L","2026-11-02","2026-11-02 23:21:31",0],["B0CZ1R2GGG","2026-11-02","2026-11-02 23:21:31",4584],["B0CZ2DX1NW","2026-11-02","2026-11-02 23:21:31",0],["B0CZ2DYMFN","2026-11-02","2026-11-02 23:21:31",483],["B0CZ2F4G84","2026-11-02","2026-11-02 23:21:31",2],["B0CZ2TDMWV","2026-11-02","2026-11-02 23:21:31",183],["B0CZ2VWSD3","2026-11-02","2026-11-02 23:21:31",0],["B0CZ7KB218","2026-11-02","2026-11-02 23:21:31",423],["B0D4312MXF","2026-11-02","2026-11-02 23:21:31",12],["B0D4379H26","2026-11-02","2026-11-02 23:21:31",0],["B0DHWJSYZN","2026-11-02","2026-11-02 23:21:31",1],["B0GXHV6VPT","2026-11-02","2026-11-02 23:21:31",30],["B0GXHWXKRQ","2026-11-02","2026-11-02 23:21:31",23],["B0GXHZBXVT","2026-11-02","2026-11-02 23:21:31",211],["B0GXJ2MSBZ","2026-11-02","2026-11-02 23:21:31",28],["B0GXJ3FGBF","2026-11-02","2026-11-02 23:21:31",11],["B0GXJKL444","2026-11-02","2026-11-02 23:21:31",33],["B0GXKXXVL1","2026-11-02","2026-11-02 23:21:31",31],["B0GXL65T4P","2026-11-02","2026-11-02 23:21:31",21],["B0HNX2ZYRC","2026-11-02","2026-11-02 23:21:31",0],["B0B1GHMGN2","2026-11-02","2026-11-02 23:25:29",0],["B0BG3K6JD4","2026-11-02","2026-11-02 23:25:29",0],["B0BKLWF3JL","2026-11-02","2026-11-02 23:25:29",356],["B0C1QC5BD4","2026-11-02","2026-11-02 23:25:29",289],["B0CVLJWR4W","2026-11-02","2026-11-02 23:25:29",0],["B0CVLY7TNZ","2026-11-02","2026-11-02 23:25:29",43],["B0D9PMQQG1","2026-11-02","2026-11-02 23:25:29",0],["B0D9PN1VZP","2026-11-02","2026-11-02 23:25:29",96],["B0D9PP78X9","2026-11-02","2026-11-02 23:25:29",22],["B0D9PPT37N","2026-11-02","2026-11-02 23:25:29",42],["B0DKQ63JJP","2026-11-02","2026-11-02 23:25:29",19],["B0DKQDJGBM","2026-11-02","2026-11-02 23:25:29",42],["B0DMN768YM","2026-11-02","2026-11-02 23:25:29",215],["B0DNV2YYL1","2026-11-02","2026-11-02 23:25:29",75],["B0DNV32517","2026-11-02","2026-11-02 23:25:29",0],["B0F1CDR3HS","2026-11-02","2026-11-02 23:25:29",0],["B0FR9V1JRC","2026-11-02","2026-11-02 23:25:29",28],["B0FVG84MDR","2026-11-02","2026-11-02 23:25:29",15],["B0FVGBRKTG","2026-11-02","2026-11-02 23:25:29",19],["B0FVGD1GW6","2026-11-02","2026-11-02 23:25:29",23],["B0HNWJHCCZ","2026-11-02","2026-11-02 23:25:29",0],["B00U6DJCR8","2026-11-03","2026-11-03 17:28:49",73],["B07KPRTSMT","2026-11-03","2026-11-03 17:28:49",20],["B07WGHX6M3","2026-11-03","2026-11-03 17:28:49",476],["B081ZDBFXP","2026-11-03","2026-11-03 17:28:49",124],["B08ZGL2CNL","2026-11-03","2026-11-03 17:28:49",183],["B08ZHDPPNH","2026-11-03","2026-11-03 17:28:49",0],["B0BL5MM9V5","2026-11-03","2026-11-03 17:28:49",11],["B0BSM9K4CH","2026-11-03","2026-11-03 17:28:49",1],["B0D9PNDC1Q","2026-11-03","2026-11-03 17:28:49",0],["B0D9ZLLH9C","2026-11-03","2026-11-03 17:28:49",28],["B0DKVHHPDZ","2026-11-03","2026-11-03 17:28:49",0],["B0DL72SKBS","2026-11-03","2026-11-03 17:28:49",0],["B0DN8KMKRK","2026-11-03","2026-11-03 17:28:49",0],["B0DN8L8DHN","2026-11-03","2026-11-03 17:28:49",0],["B0DQF8R5XL","2026-11-03","2026-11-03 17:28:49",39],["B0FGLQ32YD","2026-11-03","2026-11-03 17:28:49",4],["B0FR9SSDB3","2026-11-03","2026-11-03 17:28:49",14],["B0GXLQD7DQ","2026-11-03","2026-11-03 17:28:49",54],["B0HBRVF18K","2026-11-03","2026-11-03 17:28:49",24],["B0HJDDN85X","2026-11-03","2026-11-03 17:28:49",0],["B0HNWX96D6","2026-11-03","2026-11-03 17:28:49",0],["B0HNWZCKTB","2026-11-03","2026-11-03 17:28:49",0],["B0CYJX7L6M","2026-11-03","2026-11-03 17:29:35",0],["B0CYK66K6L","2026-11-03","2026-11-03 17:29:35",241],["B0CZ1R2GGG","2026-11-03","2026-11-03 17:29:35",0],["B0CZ2DX1NW","2026-11-03","2026-11-03 17:29:35",352],["B0CZ2DYMFN","2026-11-03","2026-11-03 17:29:35",1345],["B0CZ2F4G84","2026-11-03","2026-11-03 17:29:35",1545],["B0CZ2TDMWV","2026-11-03","2026-11-03 17:29:35",239],["B0CZ7KB218","2026-11-03","2026-11-03 17:29:35",8],["B0D4312MXF","2026-11-03","2026-11-03 17:29:35",116],["B0D4379H26","2026-11-03","2026-11-03 17:29:35",0],["B0DHWGQYSC","2026-11-03","2026-11-03 17:29:35",11],["B0DHWJSYZN","2026-11-03","2026-11-03 17:29:35",122],["B0GXHV6VPT","2026-11-03","2026-11-03 17:29:35",38],["B0GXHWXKRQ","2026-11-03","2026-11-03 17:29:35",39],["B0GXHZBXVT","2026-11-03","2026-11-03 17:29:35",14],["B0GXJ2MSBZ","2026-11-03","2026-11-03 17:29:35",59],["B0GXJ3FGBF","2026-11-03","2026-11-03 17:29:35",11],["B0GXJKL444","2026-11-03","2026-11-03 17:29:35",91],["B0GXKXXVL1","2026-11-03","2026-11-03 17:29:35",27],["B0GXL65T4P","2026-11-03","2026-11-03 17:29:35",13],["B0HNX2ZYRC","2026-11-03","2026-11-03 17:29:35",0],["B0B1GHMGN2","2026-11-09","2026-11-09 15:23:42",0],["B0BG3K6JD4","2026-11-09","2026-11-09 15:23:42",0],["B0BKLWF3JL","2026-11-09","2026-11-09 15:23:42",355],["B0C1QC5BD4","2026-11-09","2026-11-09 15:23:42",286],["B0CVLJWR4W","2026-11-09","2026-11-09 15:23:42",0],["B0CVLY7TNZ","2026-11-09","2026-11-09 15:23:42",66],["B0D9PMQQG1","2026-11-09","2026-11-09 15:23:42",0],["B0D9PN1VZP","2026-11-09","2026-11-09 15:23:42",92],["B0D9PP78X9","2026-11-09","2026-11-09 15:23:42",22],["B0D9PPT37N","2026-11-09","2026-11-09 15:23:42",41],["B0DKQ63JJP","2026-11-09","2026-11-09 15:23:42",29],["B0DKQDJGBM","2026-11-09","2026-11-09 15:23:42",116],["B0DMN768YM","2026-11-09","2026-11-09 15:23:42",215],["B0DNV2YYL1","2026-11-09","2026-11-09 15:23:42",69],["B0DNV32517","2026-11-09","2026-11-09 15:23:42",0],["B0F1CDR3HS","2026-11-09","2026-11-09 15:23:42",0],["B0FR9V1JRC","2026-11-09","2026-11-09 15:23:42",27],["B0FVG84MDR","2026-11-09","2026-11-09 15:23:42",12],["B0FVGBRKTG","2026-11-09","2026-11-09 15:23:42",19],["B0FVGD1GW6","2026-11-09","2026-11-09 15:23:42",21],["B0HNWJHCCZ","2026-11-09","2026-11-09 15:23:42",0]]""")

CORE = (const_obj("UPLOAD_GUARD_RULES") + "\n"
        + re.search(r"const UPLOAD_GUARD_TWIN_PCT = [\d.]+;", js).group(0) + "\n"
        + re.search(r"const UPLOAD_GUARD_MIN_KEYS = \d+;", js).group(0) + "\n"
        + re.search(r"const UPLOAD_GUARD_COUNT_PCT = [\d.]+;", js).group(0) + "\n"
        + re.search(r"const UPLOAD_GUARD_OVERLAP_PCT = [\d.]+;", js).group(0) + "\n"
        + fn("uploadGuardBaseline") + "\n")

FIXTURE = """
// [asin, snapshot_date, uploaded_at, afn]
const CA = """ + json.dumps(json.loads(r"""[["B00U6DJCR8","2026-11-02","2026-11-02 23:21:09",415],["B00U6EGXGK","2026-11-02","2026-11-02 23:21:09",1536],["B00U869UMK","2026-11-02","2026-11-02 23:21:09",794],["B00U86E6Z6","2026-11-02","2026-11-02 23:21:09",2127],["B0108I6PZC","2026-11-02","2026-11-02 23:21:09",0],["B017ME6VMW","2026-11-02","2026-11-02 23:21:09",116],["B01MEEJAML","2026-11-02","2026-11-02 23:21:09",0],["B07KPRTSMT","2026-11-02","2026-11-02 23:21:09",5654],["B07WGHX6M3","2026-11-02","2026-11-02 23:21:09",3185],["B081ZDBFXP","2026-11-02","2026-11-02 23:21:09",261],["B0844RR5FH","2026-11-02","2026-11-02 23:21:09",153],["B08W24837G","2026-11-02","2026-11-02 23:21:09",123],["B08ZGL2CNL","2026-11-02","2026-11-02 23:21:09",106],["B08ZGZDYFG","2026-11-02","2026-11-02 23:21:09",26],["B08ZHDPPNH","2026-11-02","2026-11-02 23:21:09",113],["B0BL5MM9V5","2026-11-02","2026-11-02 23:21:09",26],["B0BL5P83QD","2026-11-02","2026-11-02 23:21:09",40],["B0BSM9K4CH","2026-11-02","2026-11-02 23:21:09",39],["B0BSMBZN6Y","2026-11-02","2026-11-02 23:21:09",35],["B0BSMC7RWX","2026-11-02","2026-11-02 23:21:09",0],["B0BSMP5RL3","2026-11-02","2026-11-02 23:21:09",63],["B0BSMQF7C5","2026-11-02","2026-11-02 23:21:09",15],["B0BV3DYBR3","2026-11-02","2026-11-02 23:21:09",745],["B0C1QKDPRM","2026-11-02","2026-11-02 23:21:09",54],["B0C1QV5B9P","2026-11-02","2026-11-02 23:21:09",18],["B0C1QWRDT8","2026-11-02","2026-11-02 23:21:09",65],["B0C1QYBG5Y","2026-11-02","2026-11-02 23:21:09",39],["B0C1T4VQWV","2026-11-02","2026-11-02 23:21:09",0],["B0C1T81NMW","2026-11-02","2026-11-02 23:21:09",17],["B0CLPFTC7K","2026-11-02","2026-11-02 23:21:09",0],["B0D9PMWYGM","2026-11-02","2026-11-02 23:21:09",34],["B0D9PN38GG","2026-11-02","2026-11-02 23:21:09",23],["B0D9PNDC1Q","2026-11-02","2026-11-02 23:21:09",0],["B0D9ZHY9TF","2026-11-02","2026-11-02 23:21:09",0],["B0D9ZLLH9C","2026-11-02","2026-11-02 23:21:09",128],["B0DKVFG2RF","2026-11-02","2026-11-02 23:21:09",266],["B0DKVHHPDZ","2026-11-02","2026-11-02 23:21:09",0],["B0DKVHP6MS","2026-11-02","2026-11-02 23:21:09",0],["B0DKVNCGJ6","2026-11-02","2026-11-02 23:21:09",27],["B0DL1LCWQ3","2026-11-02","2026-11-02 23:21:09",16],["B0DL72SKBS","2026-11-02","2026-11-02 23:21:09",0],["B0DNLGFDBJ","2026-11-02","2026-11-02 23:21:09",147],["B0DNLQ49TS","2026-11-02","2026-11-02 23:21:09",42],["B0DNLVN8JY","2026-11-02","2026-11-02 23:21:09",12],["B0DQF8R5XL","2026-11-02","2026-11-02 23:21:09",926],["B0DYKD1S8V","2026-11-02","2026-11-02 23:21:09",139],["B0F69Y3YKP","2026-11-02","2026-11-02 23:21:09",28],["B0F6B4BXJR","2026-11-02","2026-11-02 23:21:09",78],["B0FFTS34FF","2026-11-02","2026-11-02 23:21:09",16],["B0FGKK9FFG","2026-11-02","2026-11-02 23:21:09",0],["B0FGKNPX45","2026-11-02","2026-11-02 23:21:09",29],["B0FGKQY7SM","2026-11-02","2026-11-02 23:21:09",0],["B0FGL9Q5W2","2026-11-02","2026-11-02 23:21:09",174],["B0FGLJ4MR2","2026-11-02","2026-11-02 23:21:09",33],["B0FGLJHD3N","2026-11-02","2026-11-02 23:21:09",41],["B0FGLNL5L6","2026-11-02","2026-11-02 23:21:09",37],["B0FGLQ32YD","2026-11-02","2026-11-02 23:21:09",0],["B0FH7LWFBR","2026-11-02","2026-11-02 23:21:09",29],["B0FN8FMTZ3","2026-11-02","2026-11-02 23:21:09",204],["B0FR8XSWS2","2026-11-02","2026-11-02 23:21:09",41],["B0FR9C8PX5","2026-11-02","2026-11-02 23:21:09",79],["B0FR9CD1CG","2026-11-02","2026-11-02 23:21:09",0],["B0FR9GXP8K","2026-11-02","2026-11-02 23:21:09",1],["B0FR9GYG6K","2026-11-02","2026-11-02 23:21:09",0],["B0FR9KBCMW","2026-11-02","2026-11-02 23:21:09",64],["B0FR9S9G21","2026-11-02","2026-11-02 23:21:09",75],["B0FR9SSDB3","2026-11-02","2026-11-02 23:21:09",303],["B0FR9V5YN6","2026-11-02","2026-11-02 23:21:09",35],["B0FVG6YHGW","2026-11-02","2026-11-02 23:21:09",19],["B0FVGCFNVQ","2026-11-02","2026-11-02 23:21:09",30],["B0G3D17RJ1","2026-11-02","2026-11-02 23:21:09",66],["B0G3D2DLJW","2026-11-02","2026-11-02 23:21:09",67],["B0GXLQD7DQ","2026-11-02","2026-11-02 23:21:09",44],["B0GXLTHJ2R","2026-11-02","2026-11-02 23:21:09",68],["B0GXLWDHL8","2026-11-02","2026-11-02 23:21:09",73],["B0GXLYYVBT","2026-11-02","2026-11-02 23:21:09",38],["B0GXM5FTQS","2026-11-02","2026-11-02 23:21:09",73],["B0GXMK2H6T","2026-11-02","2026-11-02 23:21:09",45],["B0HBR9JB81","2026-11-02","2026-11-02 23:21:09",194],["B0HBRB2ZR3","2026-11-02","2026-11-02 23:21:09",85],["B0HBRF6ZPZ","2026-11-02","2026-11-02 23:21:09",230],["B0HBRN8MQ3","2026-11-02","2026-11-02 23:21:09",59],["B0HBRQJHBQ","2026-11-02","2026-11-02 23:21:09",45],["B0HBRVF18K","2026-11-02","2026-11-02 23:21:09",98],["B0HBRVTD66","2026-11-02","2026-11-02 23:21:09",42],["B0HJDBGVVW","2026-11-02","2026-11-02 23:21:09",15],["B0HJDDN85X","2026-11-02","2026-11-02 23:21:09",20],["B0HJDGDXM4","2026-11-02","2026-11-02 23:21:09",36],["B0HNWX96D6","2026-11-02","2026-11-02 23:21:09",0],["B0HNWZCKTB","2026-11-02","2026-11-02 23:21:09",0],["B0CYJX7L6M","2026-11-02","2026-11-02 23:21:31",0],["B0CYJY8DJN","2026-11-02","2026-11-02 23:21:31",0],["B0CYK66K6L","2026-11-02","2026-11-02 23:21:31",0],["B0CZ1R2GGG","2026-11-02","2026-11-02 23:21:31",4584],["B0CZ2DX1NW","2026-11-02","2026-11-02 23:21:31",0],["B0CZ2DYMFN","2026-11-02","2026-11-02 23:21:31",483],["B0CZ2F4G84","2026-11-02","2026-11-02 23:21:31",2],["B0CZ2TDMWV","2026-11-02","2026-11-02 23:21:31",183],["B0CZ2VWSD3","2026-11-02","2026-11-02 23:21:31",0],["B0CZ7KB218","2026-11-02","2026-11-02 23:21:31",423],["B0D4312MXF","2026-11-02","2026-11-02 23:21:31",12],["B0D4379H26","2026-11-02","2026-11-02 23:21:31",0],["B0DHWJSYZN","2026-11-02","2026-11-02 23:21:31",1],["B0GXHV6VPT","2026-11-02","2026-11-02 23:21:31",30],["B0GXHWXKRQ","2026-11-02","2026-11-02 23:21:31",23],["B0GXHZBXVT","2026-11-02","2026-11-02 23:21:31",211],["B0GXJ2MSBZ","2026-11-02","2026-11-02 23:21:31",28],["B0GXJ3FGBF","2026-11-02","2026-11-02 23:21:31",11],["B0GXJKL444","2026-11-02","2026-11-02 23:21:31",33],["B0GXKXXVL1","2026-11-02","2026-11-02 23:21:31",31],["B0GXL65T4P","2026-11-02","2026-11-02 23:21:31",21],["B0HNX2ZYRC","2026-11-02","2026-11-02 23:21:31",0],["B0B1GHMGN2","2026-11-02","2026-11-02 23:25:29",0],["B0BG3K6JD4","2026-11-02","2026-11-02 23:25:29",0],["B0BKLWF3JL","2026-11-02","2026-11-02 23:25:29",356],["B0C1QC5BD4","2026-11-02","2026-11-02 23:25:29",289],["B0CVLJWR4W","2026-11-02","2026-11-02 23:25:29",0],["B0CVLY7TNZ","2026-11-02","2026-11-02 23:25:29",43],["B0D9PMQQG1","2026-11-02","2026-11-02 23:25:29",0],["B0D9PN1VZP","2026-11-02","2026-11-02 23:25:29",96],["B0D9PP78X9","2026-11-02","2026-11-02 23:25:29",22],["B0D9PPT37N","2026-11-02","2026-11-02 23:25:29",42],["B0DKQ63JJP","2026-11-02","2026-11-02 23:25:29",19],["B0DKQDJGBM","2026-11-02","2026-11-02 23:25:29",42],["B0DMN768YM","2026-11-02","2026-11-02 23:25:29",215],["B0DNV2YYL1","2026-11-02","2026-11-02 23:25:29",75],["B0DNV32517","2026-11-02","2026-11-02 23:25:29",0],["B0F1CDR3HS","2026-11-02","2026-11-02 23:25:29",0],["B0FR9V1JRC","2026-11-02","2026-11-02 23:25:29",28],["B0FVG84MDR","2026-11-02","2026-11-02 23:25:29",15],["B0FVGBRKTG","2026-11-02","2026-11-02 23:25:29",19],["B0FVGD1GW6","2026-11-02","2026-11-02 23:25:29",23],["B0HNWJHCCZ","2026-11-02","2026-11-02 23:25:29",0],["B00U6DJCR8","2026-11-03","2026-11-03 17:28:49",73],["B07KPRTSMT","2026-11-03","2026-11-03 17:28:49",20],["B07WGHX6M3","2026-11-03","2026-11-03 17:28:49",476],["B081ZDBFXP","2026-11-03","2026-11-03 17:28:49",124],["B08ZGL2CNL","2026-11-03","2026-11-03 17:28:49",183],["B08ZHDPPNH","2026-11-03","2026-11-03 17:28:49",0],["B0BL5MM9V5","2026-11-03","2026-11-03 17:28:49",11],["B0BSM9K4CH","2026-11-03","2026-11-03 17:28:49",1],["B0D9PNDC1Q","2026-11-03","2026-11-03 17:28:49",0],["B0D9ZLLH9C","2026-11-03","2026-11-03 17:28:49",28],["B0DKVHHPDZ","2026-11-03","2026-11-03 17:28:49",0],["B0DL72SKBS","2026-11-03","2026-11-03 17:28:49",0],["B0DN8KMKRK","2026-11-03","2026-11-03 17:28:49",0],["B0DN8L8DHN","2026-11-03","2026-11-03 17:28:49",0],["B0DQF8R5XL","2026-11-03","2026-11-03 17:28:49",39],["B0FGLQ32YD","2026-11-03","2026-11-03 17:28:49",4],["B0FR9SSDB3","2026-11-03","2026-11-03 17:28:49",14],["B0GXLQD7DQ","2026-11-03","2026-11-03 17:28:49",54],["B0HBRVF18K","2026-11-03","2026-11-03 17:28:49",24],["B0HJDDN85X","2026-11-03","2026-11-03 17:28:49",0],["B0HNWX96D6","2026-11-03","2026-11-03 17:28:49",0],["B0HNWZCKTB","2026-11-03","2026-11-03 17:28:49",0],["B0CYJX7L6M","2026-11-03","2026-11-03 17:29:35",0],["B0CYK66K6L","2026-11-03","2026-11-03 17:29:35",241],["B0CZ1R2GGG","2026-11-03","2026-11-03 17:29:35",0],["B0CZ2DX1NW","2026-11-03","2026-11-03 17:29:35",352],["B0CZ2DYMFN","2026-11-03","2026-11-03 17:29:35",1345],["B0CZ2F4G84","2026-11-03","2026-11-03 17:29:35",1545],["B0CZ2TDMWV","2026-11-03","2026-11-03 17:29:35",239],["B0CZ7KB218","2026-11-03","2026-11-03 17:29:35",8],["B0D4312MXF","2026-11-03","2026-11-03 17:29:35",116],["B0D4379H26","2026-11-03","2026-11-03 17:29:35",0],["B0DHWGQYSC","2026-11-03","2026-11-03 17:29:35",11],["B0DHWJSYZN","2026-11-03","2026-11-03 17:29:35",122],["B0GXHV6VPT","2026-11-03","2026-11-03 17:29:35",38],["B0GXHWXKRQ","2026-11-03","2026-11-03 17:29:35",39],["B0GXHZBXVT","2026-11-03","2026-11-03 17:29:35",14],["B0GXJ2MSBZ","2026-11-03","2026-11-03 17:29:35",59],["B0GXJ3FGBF","2026-11-03","2026-11-03 17:29:35",11],["B0GXJKL444","2026-11-03","2026-11-03 17:29:35",91],["B0GXKXXVL1","2026-11-03","2026-11-03 17:29:35",27],["B0GXL65T4P","2026-11-03","2026-11-03 17:29:35",13],["B0HNX2ZYRC","2026-11-03","2026-11-03 17:29:35",0],["B0B1GHMGN2","2026-11-09","2026-11-09 15:23:42",0],["B0BG3K6JD4","2026-11-09","2026-11-09 15:23:42",0],["B0BKLWF3JL","2026-11-09","2026-11-09 15:23:42",355],["B0C1QC5BD4","2026-11-09","2026-11-09 15:23:42",286],["B0CVLJWR4W","2026-11-09","2026-11-09 15:23:42",0],["B0CVLY7TNZ","2026-11-09","2026-11-09 15:23:42",66],["B0D9PMQQG1","2026-11-09","2026-11-09 15:23:42",0],["B0D9PN1VZP","2026-11-09","2026-11-09 15:23:42",92],["B0D9PP78X9","2026-11-09","2026-11-09 15:23:42",22],["B0D9PPT37N","2026-11-09","2026-11-09 15:23:42",41],["B0DKQ63JJP","2026-11-09","2026-11-09 15:23:42",29],["B0DKQDJGBM","2026-11-09","2026-11-09 15:23:42",116],["B0DMN768YM","2026-11-09","2026-11-09 15:23:42",215],["B0DNV2YYL1","2026-11-09","2026-11-09 15:23:42",69],["B0DNV32517","2026-11-09","2026-11-09 15:23:42",0],["B0F1CDR3HS","2026-11-09","2026-11-09 15:23:42",0],["B0FR9V1JRC","2026-11-09","2026-11-09 15:23:42",27],["B0FVG84MDR","2026-11-09","2026-11-09 15:23:42",12],["B0FVGBRKTG","2026-11-09","2026-11-09 15:23:42",19],["B0FVGD1GW6","2026-11-09","2026-11-09 15:23:42",21],["B0HNWJHCCZ","2026-11-09","2026-11-09 15:23:42",0]]"""), separators=(',', ':')) + """;
const asRows = (a) => a.map(r => ({
  asin: r[0], snapshot_date: r[1], uploaded_at: r[2], afn_fulfillable_quantity: r[3] }));
const ALL   = asRows(CA);
const PRIOR = ALL.filter(r => r.snapshot_date < '2026-11-09');
const MINE_ROWS = ALL.filter(r => r.snapshot_date === '2026-11-09');
const mineOf = (rows) => new Map(rows.map(r => [String(r.asin), Number(r.afn_fulfillable_quantity || 0)]));
const RULE = UPLOAD_GUARD_RULES.fba_inventory;
"""

# ---------------------------------------------------------------------------
print("\nA. the real uploadGuardBaseline on the real CA history")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1176_a.js"), CORE + FIXTURE + r"""
const mine = mineOf(MINE_ROWS);
const base = uploadGuardBaseline(PRIOR, mine, RULE);

// The v11.44 fallback: no session column, so a PERIOD is the unit.
const noSess = Object.assign({}, RULE); delete noSess.sessionCol;
const flat = uploadGuardBaseline(PRIOR, mine, noSess);

// A file sharing nothing with anything loaded before.
const alien = new Map([...Array(20).keys()].map(i => ['ZZZ' + i, 5]));

// A tie on overlap must go to the NEWEST upload. Both of these contain the
// same single key, so overlap is equal.
const tieKeys = [...Array(10).keys()].map(i => 'T' + i);
const tieRows = [].concat(
  tieKeys.map(k => ({ asin: k, snapshot_date: '2026-01-01', uploaded_at: '2026-01-01 09:00:00', afn_fulfillable_quantity: 1 })),
  tieKeys.map(k => ({ asin: k, snapshot_date: '2026-02-01', uploaded_at: '2026-02-01 09:00:00', afn_fulfillable_quantity: 1 })));
const tieMine = new Map(tieKeys.map(k => [k, 1]));

console.log(JSON.stringify({
  priorRows: PRIOR.length,
  mineSize: mine.size,
  sessions: new Set(PRIOR.map(r => r.snapshot_date + '|' + r.uploaded_at)).size,
  period:  base && base.period,
  session: base && base.session,
  keys:    base && base.keys.size,
  overlap: base && base.overlap,
  afn:     base && [...base.keys.values()].reduce((a, v) => a + v, 0),
  mineAfn: [...mine.values()].reduce((a, v) => a + v, 0),
  flatPeriod: flat && flat.period,
  flatKeys:   flat && flat.keys.size,
  alien:   uploadGuardBaseline(PRIOR, alien, RULE),
  // overlap below the floor, even though the keys are real
  tiny:    uploadGuardBaseline(PRIOR, new Map([...mine].slice(0, 3)), RULE),
  tie:     (() => { const b = uploadGuardBaseline(tieRows, tieMine, Object.assign({}, RULE)); return b && b.period; })(),
  noRows:  uploadGuardBaseline([], mine, RULE),
  noMine:  uploadGuardBaseline(PRIOR, new Map(), RULE),
  nullRows: uploadGuardBaseline(null, mine, RULE),
}));
""")

eq("A1  the real prior CA history, as loaded", A["priorRows"], 176)
eq("A2  five distinct uploads inside it", A["sessions"], 5)
eq("A3  the file being uploaded holds 21 ASINs", A["mineSize"], 21)
# /!\ 2026-11-03 is the NEWER date. It is not the baseline, because the file
# loaded that day is a different brand and shares no ASIN with this one.
eq("A4  the baseline is 2026-11-02, not the newer 2026-11-03", A["period"], "2026-11-02")
eq("A5  ... and the Doggijuana upload within it", A["session"], "2026-11-02 23:25:29")
eq("A6  which held exactly the same 21 ASINs", A["keys"], 21)
eq("A7  every one of them overlapping", A["overlap"], 21)
eq("A8  its units were 1,284", A["afn"], 1284)
eq("A9  against this file's 1,370", A["mineAfn"], 1370)

# /!\ Why the session column is load-bearing rather than a nicety.
eq("A10 with no session column the unit is the PERIOD", A["flatPeriod"], "2026-11-02")
eq("A11 ... and it reads 133 ASINs - every brand loaded that day",
   A["flatKeys"], 133)

ok(A["alien"] is None, "A12 a file sharing nothing with history has NO baseline", A["alien"])
ok(A["tiny"] is None, "A13 ... and neither does one whose overlap is below the floor", A["tiny"])
eq("A14 a tie on overlap goes to the NEWEST upload", A["tie"], "2026-02-01")
ok(A["noRows"] is None and A["noMine"] is None and A["nullRows"] is None,
   "A15 no history, no file and null all answer null rather than throwing",
   [A["noRows"], A["noMine"], A["nullRows"]])

# ---------------------------------------------------------------------------
print("\nB. /!\\ THE DEFECT REPRODUCED - v11.44's rule beside the shipped one")
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "_v1176_b.js"), CORE + FIXTURE + r"""
const mine = mineOf(MINE_ROWS);
const scope = 'CA', noun = RULE.noun;

// ---- the PRE-v11.76 size check, exactly as it stood --------------------
function oldSize(prevRows, mine) {
  const out = [];
  if (prevRows && prevRows.length) {
    const prevPeriod = prevRows[0][RULE.periodCol];
    const prev = prevRows.filter(r => r[RULE.periodCol] === prevPeriod);
    const pn = prev.length, mn = mine.size;
    if (pn >= UPLOAD_GUARD_MIN_KEYS && Math.abs(mn - pn) / pn >= UPLOAD_GUARD_COUNT_PCT) {
      out.push(`This file has ${mn.toLocaleString()} ${noun}; the last ${scope} load (${prevPeriod}) had `
        + `${pn.toLocaleString()}. That is a ${mn > pn ? 'rise' : 'drop'} of `
        + `${Math.round(Math.abs(mn - pn) / pn * 100)}%.`);
    }
    const pt = prev.reduce((a, r) => a + Number(r[RULE.numCol] || 0), 0);
    const mt = [...mine.values()].reduce((a, v) => a + v, 0);
    if (pt > 0 && Math.abs(mt - pt) / pt >= UPLOAD_GUARD_COUNT_PCT) {
      out.push(`Total ${RULE.numCol.replace(/_/g, ' ')} is ${mt.toLocaleString()}; `
        + `the last ${scope} load had ${pt.toLocaleString()}.`);
    }
  }
  return out;
}

// ---- the SHIPPED size check -------------------------------------------
function newSize(prevRows, mine) {
  const out = [];
  const base = uploadGuardBaseline(prevRows, mine, RULE);
  if (base) {
    const pn = base.keys.size, mn = mine.size;
    if (pn >= UPLOAD_GUARD_MIN_KEYS && Math.abs(mn - pn) / pn >= UPLOAD_GUARD_COUNT_PCT) {
      out.push(`This file has ${mn.toLocaleString()} ${noun}; the last ${scope} upload of these `
        + `${noun} (${base.period}) had ${pn.toLocaleString()}. That is a `
        + `${mn > pn ? 'rise' : 'drop'} of ${Math.round(Math.abs(mn - pn) / pn * 100)}%.`);
    }
    const pt = [...base.keys.values()].reduce((a, v) => a + v, 0);
    const mt = [...mine.values()].reduce((a, v) => a + v, 0);
    if (pt > 0 && Math.abs(mt - pt) / pt >= UPLOAD_GUARD_COUNT_PCT) {
      out.push(`Total ${RULE.numCol.replace(/_/g, ' ')} is ${mt.toLocaleString()}; `
        + `that upload had ${pt.toLocaleString()}.`);
    }
  }
  return out;
}

// The query orders by period descending, which is what put 2026-11-03 first.
const prior = [...PRIOR].sort((a, b) => (a.snapshot_date < b.snapshot_date ? 1 : -1));

// And a file that really HAS been truncated: 10 of the 21.
const cut = mineOf(MINE_ROWS.slice(0, 10));
// The same truncation with the units gone too, which is the shape that
// trips BOTH halves of the check.
const cutUnits = new Map([...cut].map(([k, v]) => [k, Math.round(v * 0.2)]));
const base = uploadGuardBaseline(prior, mine, RULE);

console.log(JSON.stringify({
  old: oldSize(prior, mine),
  nu:  newSize(prior, mine),
  oldCut: oldSize(prior, cut),
  nuCut:  newSize(prior, cut),
  nuCutUnits: newSize(prior, cutUnits),
  baseAfn: [...base.keys.values()].reduce((a, v) => a + v, 0),
  cutAfn:  [...cut.values()].reduce((a, v) => a + v, 0),
}));
""")

eq("B1  v11.44 raised TWO concerns on a file with nothing wrong with it",
   len(B["old"]), 2)
# /!\ This is the text in Jason's screenshot, byte for byte.
eq("B2  ... the first being the one he screenshotted", B["old"][0],
   "This file has 21 ASINs; the last CA load (2026-11-03) had 43. "
   "That is a drop of 51%.")
eq("B3  ... and the second", B["old"][1],
   "Total afn fulfillable quantity is 1,370; the last CA load had 5,322.")
eq("B4  the shipped rule raises NOTHING on the same file", B["nu"], [])

# /!\ And the check still does its job, which is the half that matters.
eq("B5  a genuinely truncated file still raises the size concern",
   len(B["nuCut"]), 1)
ok(B["nuCut"][0].startswith("This file has 10 ASINs; the last CA upload of these ASINs (2026-11-02) had 21."),
   "B6  ... measured against the right predecessor", B["nuCut"][0])
# My own expectation was that both halves fire here. They do not, and the
# code is right: half the ASINs still carry 1,204 of the baseline's 1,284
# units, which is a 6% move, so the UNITS check has nothing to report. The
# two halves answer different questions and are supposed to disagree.
eq("B7  the baseline's units", B["baseAfn"], 1284)
ok(abs(B["cutAfn"] - B["baseAfn"]) / B["baseAfn"] < 0.5,
   "B8  ... and the truncated file's are within half of them, so the units "
   "half correctly stays quiet", [B["cutAfn"], B["baseAfn"]])
eq("B9  with the units gone too, BOTH halves fire", len(B["nuCutUnits"]), 2)
ok("that upload had 1,284" in B["nuCutUnits"][1],
   "B10 ... the second measured against that upload's units", B["nuCutUnits"][1])
ok("(2026-11-03)" not in json.dumps(B["nuCut"] + B["nuCutUnits"]),
   "B11 the unrelated day is never named again", B["nuCut"])

# ---------------------------------------------------------------------------
print("\nC. the real uploadGuardCheck, end to end")
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "_v1176_c.js"), CORE + FIXTURE + "\n"
             + fn("uploadGuardCheck") + r"""
// A chainable stand-in for the supabase client, over the real rows.
function makeSB(rows) {
  return async () => ({
    from: () => {
      let data = rows.slice();
      const api = {
        select: (_c, opts) => {
          if (opts && opts.head) { api._head = true; }
          return api;
        },
        eq: (c, v) => { data = data.filter(r => String(r[c]) === String(v)); return api; },
        lt: (c, v) => { data = data.filter(r => String(r[c]) < String(v)); return api; },
        order: (c, o) => {
          const dir = (o && o.ascending) ? 1 : -1;
          data.sort((a, b) => (a[c] < b[c] ? -dir : a[c] > b[c] ? dir : 0));
          return api;
        },
        limit: (n) => { data = data.slice(0, n); return api; },
        then: (res) => res({ data, count: data.length, error: null }),
      };
      return api;
    },
  });
}

(async () => {
  const out = {};
  const mkPayload = (rows, region, date) => rows.map(r => ({
    asin: r.asin, region, snapshot_date: date,
    afn_fulfillable_quantity: r.afn_fulfillable_quantity }));

  // 1. Jason's actual upload. Every CA row is in the table; the payload is
  //    the 2026-11-09 Doggijuana file.
  globalThis.getSB = makeSB(ALL.filter(r => r.snapshot_date < '2026-11-09')
    .map(r => ({ ...r, region: 'CA' })));
  out.real = await uploadGuardCheck('fba_inventory',
    mkPayload(MINE_ROWS, 'CA', '2026-11-09'));

  // 2. The same file truncated to 10 ASINs.
  out.cut = await uploadGuardCheck('fba_inventory',
    mkPayload(MINE_ROWS.slice(0, 10), 'CA', '2026-11-09'));

  // 3. THE TWIN, which is the failure the guard was built for: the US file
  //    uploaded a second time with the region set to CA.
  const usRows = MINE_ROWS.map(r => ({ ...r, region: 'US', snapshot_date: '2026-11-09' }));
  globalThis.getSB = makeSB(usRows);
  out.twin = await uploadGuardCheck('fba_inventory',
    mkPayload(MINE_ROWS, 'CA', '2026-11-09'));

  // 4. A guard that cannot run must not stop the upload.
  globalThis.getSB = async () => { throw new Error('boom'); };
  out.broken = await uploadGuardCheck('fba_inventory',
    mkPayload(MINE_ROWS, 'CA', '2026-11-09'));

  // 5. An unguarded source and an empty payload.
  out.unknown = await uploadGuardCheck('not_a_source', mkPayload(MINE_ROWS, 'CA', '2026-11-09'));
  out.empty = await uploadGuardCheck('fba_inventory', []);
  console.log(JSON.stringify(out));
})();
""")

eq("C1  Jason's real upload raises NOTHING at all", C["real"], [])
# Exactly one, for the reason B7-B8 measured: half the ASINs still carry
# most of the units, so the units half has nothing to say.
eq("C2  the truncated one raises exactly the size concern", len(C["cut"]), 1)
eq("C3  ... the size one at high", C["cut"][0]["level"], "high")
ok("(2026-11-02) had 21" in C["cut"][0]["text"],
   "C4  ... against the right predecessor", C["cut"][0]["text"])
ok(any(x["level"] == "high" and "IDENTICAL" in x["text"] for x in C["twin"]),
   "C5  the twin check still fires on a US file stamped CA", C["twin"])
ok(any('as "US"' in x["text"] for x in C["twin"]),
   "C6  ... and names the region it really belongs to", C["twin"])
eq("C7  a guard that throws returns no concerns rather than blocking",
   C["broken"], [])
eq("C8  an unguarded source is simply unguarded", C["unknown"], [])
eq("C9  and an empty payload is not a concern", C["empty"], [])

# ---------------------------------------------------------------------------
print("\nD. check 2 - exactly which rows the upsert replaces")
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "_v1176_d.js"), CORE + FIXTURE + "\n"
             + fn("uploadGuardCheck") + r"""
function makeSB(rows) {
  return async () => ({ from: () => {
    let data = rows.slice();
    const api = {
      select: () => api,
      eq: (c, v) => { data = data.filter(r => String(r[c]) === String(v)); return api; },
      lt: (c, v) => { data = data.filter(r => String(r[c]) < String(v)); return api; },
      order: (c, o) => { const d = (o && o.ascending) ? 1 : -1;
        data.sort((a, b) => (a[c] < b[c] ? -d : a[c] > b[c] ? d : 0)); return api; },
      limit: (n) => { data = data.slice(0, n); return api; },
      then: (res) => res({ data, count: data.length, error: null }),
    };
    return api;
  }});
}
const mkPayload = (rows, region, date) => rows.map(r => ({
  asin: r.asin, region, snapshot_date: date,
  afn_fulfillable_quantity: r.afn_fulfillable_quantity }));
const infoOf = (cs) => cs.filter(c => c.level === 'info').map(c => c.text);

(async () => {
  const out = {};
  const at1103 = ALL.filter(r => r.snapshot_date === '2026-11-03').map(r => ({ ...r, region: 'CA' }));
  const kkz = at1103.filter(r => r.uploaded_at === '2026-11-03 17:29:35');
  const meo = at1103.filter(r => r.uploaded_at === '2026-11-03 17:28:49');

  // A SECOND BRAND on a day that already holds another brand. The conflict
  // key cannot touch the first one, and the message must not say it can.
  globalThis.getSB = makeSB(kkz);
  out.secondBrand = infoOf(await uploadGuardCheck('fba_inventory',
    mkPayload(meo, 'CA', '2026-11-03')));

  // A real re-upload of the same file: every key collides.
  globalThis.getSB = makeSB(meo);
  out.reupload = infoOf(await uploadGuardCheck('fba_inventory',
    mkPayload(meo, 'CA', '2026-11-03')));

  // A partial overlap.
  globalThis.getSB = makeSB(meo.slice(0, 9));
  out.partial = infoOf(await uploadGuardCheck('fba_inventory',
    mkPayload(meo, 'CA', '2026-11-03')));

  // Nothing loaded for that cell at all.
  globalThis.getSB = makeSB([]);
  out.fresh = infoOf(await uploadGuardCheck('fba_inventory',
    mkPayload(meo, 'CA', '2026-11-03')));
  console.log(JSON.stringify(out));
})();
""")

ok(any("none of them in this file. Nothing is replaced." in t for t in D["secondBrand"]),
   "D1  a second brand on the same day is told nothing is replaced",
   D["secondBrand"])
ok(any(t.startswith("21 ASINs are already loaded for CA on 2026-11-03") for t in D["secondBrand"]),
   "D2  ... and how many rows are sitting there untouched", D["secondBrand"])
ok(any("22 of this file's 22 ASINs are already loaded" in t for t in D["reupload"]),
   "D3  a true re-upload says every row is replaced", D["reupload"])
ok(any("9 of this file's 22 ASINs are already loaded" in t for t in D["partial"]),
   "D4  a partial overlap names the exact count", D["partial"])
eq("D5  an empty cell raises no replacement concern at all", D["fresh"], [])

# ---------------------------------------------------------------------------
print("\nE. static")
# ---------------------------------------------------------------------------
_chk = nocomment(fn("uploadGuardCheck"))
ok("uploadGuardBaseline(prevRows, mine, rule)" in _chk,
   "E1  the size check resolves its baseline through the one helper")
ok("prevRows[0][rule.periodCol]" not in _chk,
   "E2  the retired 'newest earlier period' rule is GONE from live code")
ok("the region's most recent earlier" in js or "most recent EARLIER" in js,
   "E3  ... and the explanation survives in a comment, so grepping it lands "
   "on why")
ok("count: 'exact'" not in _chk,
   "E4  the head-count that counted the whole day is gone")
ok(_chk.count("existingKeys") >= 3,
   "E5  the replacement count is an intersection with THIS file's keys")

_reg = const_obj("UPLOAD_GUARD_RULES")
ok("sessionCol: 'uploaded_at'" in _reg,
   "E6  the FBA rule declares what separates one upload from another")

_base = nocomment(fn("uploadGuardBaseline"))
ok("rule.sessionCol ?" in _base,
   "E7  a source with no session column falls back to the period")
ok("UPLOAD_GUARD_OVERLAP_PCT" in _base,
   "E8  and an unrelated predecessor is refused rather than measured against")

# The coverage grid's dead end.
_render = nocomment(fn("renderUploadCoverage"))
ok("uploadCoverageFetchRetry(src.table, src.filter)" in _render,
   "E9  the coverage render reads through the retrying fetch")
ok("await uploadCoverageFetch(" not in _render,
   "E10 ... and never the bare one, which had no way back", _render)
ok("uploadCoverageRetryHtml(dzId)" in _render,
   "E11 a failed read renders a retry control")
_retry = nocomment(fn("uploadCoverageRetryHtml"))
ok("onclick" in _retry and "renderUploadCoverage(" in _retry,
   "E12 ... which calls the render again")
ok("title=" not in _retry,
   "E13 the affordance is a control, not prose in a title (rule 1a)", _retry)
_fetchr = nocomment(fn("uploadCoverageFetchRetry", kw="async function"))
eq("E14 exactly two attempts, never a loop", _fetchr.count("uploadCoverageFetch("), 2)
ok("second.err ? first : second" in _fetchr,
   "E15 and the FIRST error is what gets reported, not the retry's")

# v11.63: the chip and CLAUDE.md's current-version line must AGREE.
doc = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", newline="").read()
chip = re.findall(r">v(\d+\.\d+) " + chr(0x00b7) + r" ([\d-]+)<", s)
eq("E16 exactly one version chip", len(chip), 1)
docv = re.search(r"current version \*\*v(\d+\.\d+)\*\*", doc)
eq("E17 the chip agrees with CLAUDE.md", chip[0][0], docv.group(1) if docv else None)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
