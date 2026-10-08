# Regression suites

Behaviour tests for `index.html`. Each `test_vNNN.py` slices the **real**
functions out of the shipped file, drops them into a Node harness with stubbed
DOM / Supabase, and asserts against them — so a test cannot drift away from what
actually ships. Most also carry static assertions against the source text, and a
**regression guard** that reproduces the pre-fix behaviour and asserts it really
was broken, so a bug cannot quietly return.

## Running

```bash
cd tests && for f in test_v*.py; do python "$f"; done
```

Each exits non-zero on failure. Needs `python` and `node` on PATH; no packages.

To run one suite:

```bash
python tests/test_v1010.py
```

## Why these live in the repo (v10.10)

They used to be written to the session scratchpad under `%TEMP%`. On
2026-10-08, **8 of 20 suites vanished between turns** when that directory was
cleaned — including the three guarding the FBA reorder-point math
(`test_v984` partition property, `test_v995` seasonal reorder point,
`test_v996` in-transit double-count). The generated `.js` harnesses survived,
but those embed a snapshot of the source from when they were generated, so
re-running them proves nothing about the current file.

A regression net that evaporates is not a regression net. They live here now.

**The 8 lost suites have not been rewritten.** What they covered:

| suite | guarded |
|---|---|
| `test_v982`, `v983`, `v985` | per-user tab access, RLS fail-open, deprecated-row styling |
| `test_v984` | `inventoryNeedBreakdown` channel filter + the partition property (`total == base + reorder + events`) |
| `test_v991` | chart hatching for lagging channels |
| `test_v992` | Excel export filename extension |
| `test_v994` | `amzVel` ASIN gate + the five all-zero diagnosis branches |
| `test_v995` | `fbaSeasonalReorderPoint` / `seaDailySeries` + the flat-curve equivalence proof |
| `test_v996` | `ipEffectiveInbound` `max()` vs the old double-counting sum |

Worth rewriting `v984`, `v995` and `v996` first — they cover the Amazon reorder
math, which is the most-edited and least-obvious part of the model.

## Conventions

- **Slice, don't reimplement.** Pull the function text out of `index.html` by
  brace balance (`fn()` helper) so the test breaks when the real code changes.
- **Name the bug.** A fix gets a test that fails against the old behaviour,
  usually by reproducing the old expression verbatim next to the new one.
- **Assert the site count**, not just that a thing exists — e.g. "`catVisPass`
  appears at exactly 4 Inventory Planning filter sites". A predicate silently
  dropped during a refactor is the failure mode that static checks catch and
  behaviour tests do not.
- **Escapes:** the harness is a Python raw string, so `\uXXXX` reaches JS
  verbatim (valid) but `\U0001FXXX` does not — JS wants `\u{1FXXX}`. Simplest is
  to paste the real character.
