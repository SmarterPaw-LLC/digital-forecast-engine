# Pre-flight. Read this before writing UI, and again before saying "shipped".

The long reasoning lives in CLAUDE.md. This is the checklist, because a rule
I have to remember to look up is a rule I skip.

## Before I write any user-facing text

1. **NEVER print prose in a UI.** A subtitle, a sub-line, a card caption is a
   NUMBER, its UNIT, and its WINDOW. Everything else is a `title=` tooltip.
   Flagged 6+ times. Budget: **a visible line stays under ~110 characters and
   never wraps to a third row.**
2. **One warning on the line, four words max** (`⚠ excludes 12,958 units`).
   The full sentence goes on the tooltip. Two lengths of ONE derivation,
   never two counts.
3. **A tooltip says how a value is DERIVED**, not why the column exists. Cut
   "rather than", "instead of", any cross-channel justification.
4. **Collapsing prose must not swallow an affordance.** List what was
   interactive in the block (links, buttons, inputs) and re-attach each one
   beside the tooltip. `test_v1087` fails on a link label inside a `title=`.
5. **No comments in paste-ready snippets.** One snippet per file.

## Before I add any control, card, column or panel

6. **Grep for the existing implementation and call it.** A second copy IS the
   bug. A consolidation that leaves copies behind is not a consolidation.
7. **One concept, one glyph. One glyph, one concept.**
8. **One label, one measure.** Grep the label across every sibling tab first.
   A different SCOPE is a different measure and needs the scope in its name.
9. **Reuse the app's existing vocabulary** before coining a word.
10. **A live-looking control that does nothing is worse than none.** Render it
    disabled WITH the reason, and strip the handler.
11. **A bucket with no denominator is a GAP, never a zero.**
12. **Every new data-bearing view is CSV-exportable before it ships.**

## Before I touch data or claim anything

13. **Run `Get-Date` first.** Never infer the date from context.
14. **Measure it against the live database before saying it.** If I have not
    measured the cause, say so instead of naming one.
15. **Every figure carries its explicit date range.** MTD is not 30d rolling.
16. **Jason's business data is never committed** — this repo is served
    publicly.

## Before I say "shipped"

17. **Run the FULL suite**, not just the new file. A census going red is the
    suite working.
18. **Load the live URL in the browser pane and read the console.** A blank
    read is NOT a pass. Check the version chip renders as real characters.
19. **Commit AND push.** If the push is blocked, that is the first line of my
    reply.
20. **Lead with blockers.** Then 3 to 6 lines. Detail goes in CLAUDE.md.

## Mechanics that have bitten me repeatedly

21. **index.html holds REAL characters in markup and `\uXXXX` escapes only
    inside JS string literals.** Build non-ASCII with `chr()`. Never paste it,
    never type the escape into markup. (v12.42 shipped `v12.42 ·` as
    literal text.)
22. **Heredocs eat escapes.** Anything carrying a `\` goes through the Write
    tool — and the Write tool interprets `\uXXXX` too, so build those with
    `chr()` as well.
23. **A patch script that exits mid-way writes nothing.** Assert every anchor
    before the single write at the end.
24. **`node --check` passes a cross-function reference that throws at
    runtime.** Scope is not syntax. Drive the real function.
25. **`git add -A` is unsafe here** — another session shares the working copy.
    Stage explicit paths.
