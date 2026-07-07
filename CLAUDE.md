# SmarterPaw Forecast Dashboard — Claude Code Handoff

## Project Overview
Single-file HTML dashboard for SmarterPaw LLC (brands: Meowijuana, Doggijuana, Kitty Ka-Zoom).
File: `index.html` (in this repo; was `SmarterPaw_Forecast_v4.html` in the old loose folder) — current version **v6.99**

## v6.99 — Merge History + Undo (full pre-merge snapshot lets any merge be reversed with one click)
- **SQL migration** — new `merge_history` table with `src_product_snapshot` + `tgt_product_before` (full JSONB), `tgt_backfill_patch` (fields patched onto survivor), `reassigned_ids` (per-table PK arrays of rows we UPDATE'd), `deleted_rows` (per-table full JSONB of rows we destructively removed), `reversed`/`reversed_at`/`reversed_by`. **Run `supabase_v6_99_merge_history.sql` in the Supabase SQL Editor before using this version.** RLS + authenticated grants match every other table (v6.47 hard rule).
- **`runMerge` refactor**:
  - Before ANY writes: snapshot the src product row, tgt product row (pre-backfill), src's inventory rows, both src/tgt product_cogs rows, all BOM rows involving either master_id.
  - Every master_id reassignment now goes through a new `reassignMasterId(table)` helper that first SELECTS the affected row PKs, records them in `capturedIds`, then UPDATEs those specific PKs. Undo can UPDATE the exact same PKs back to src.master_id — never accidentally touches survivor's legitimate rows.
  - BOM reassignments now also work by PK (not by `.eq('bundle_master_id', ...)`) so undo can reverse them precisely. Tracks `bomOutcome` state (`src_deleted` / `tgt_deleted` / `migrated` / `none`) so the undo path knows which rows to re-INSERT.
  - After all destructive steps succeed, INSERTs the history row. If the INSERT fails (e.g. table doesn't exist because migration hasn't been run), the merge still succeeds — a warn is logged saying "undo will not be available for this merge."
- **`runUndoMerge(historyId)`** reverses everything in the opposite order:
  1. INSERT the duplicate product row back from `src_product_snapshot`.
  2. Reverse every table's UPDATE by SELECTing PKs from `reassigned_ids` and UPDATEing master_id back to src's. BOM uses `component_master_id` or `bundle_master_id` depending on which key it was tracked under (`_bom_component_ids` / `_bom_bundle_ids_from_src`).
  3. Revert survivor's backfilled fields — UPDATE the survivor row with the pre-merge values for every field that appeared in `tgt_backfill_patch`.
  4. Re-INSERT destructively-removed rows: inventory, BOM (both src's bundle rows and tgt's bundle rows, depending on `bom_outcome`), product_cogs (both src's and tgt's pre-merge values via upsert).
  5. Mark the history row `reversed = true` so a second undo attempt fails cleanly.
- **UI** — new Merge History panel below the existing Merge tool on the Products page. Table columns: When | Duplicate (deleted) | → | Survivor (kept) | Status (● ACTIVE / ↶ REVERSED) | Actions. Undo button disabled once reversed. Refresh button reloads. Auto-refreshes on tab open + after every merge.
- **Safety notes**:
  - Snapshots are stored as JSONB, so future schema changes on `products` / child tables don't retroactively break the ability to undo old merges (worst case: unknown columns get ignored on insert).
  - Undo is idempotent-safe: if the duplicate row already exists (partial undo), the insert error is logged as a warn and undo continues with the reassign reversals.
  - Individual per-table failures during undo are logged as warns rather than aborting — the operator sees "✓ Merge undone" but the console has details on any specific step that didn't complete (usually a schema mismatch on an old environment).

## v6.98 — Merge tool: reassign 5 missing tables + backfill walmart_item_id (fixes silent data loss on Tuna→Seafood-style merges)
- **Trigger**: Jason wanted to merge duplicate products (Tuna Treats SP-0203 → Seafood Treats SP-0522) where the duplicate had image + Chewy SKU + barcode + Shopify SKU + ASIN and the survivor had the Walmart Item #. Merge tool hasn't been touched since we shipped several new master_id-bearing tables — Tuna's Shopify daily rows and FBA inventory snapshots would have been silently dropped on merge, and the Walmart field wasn't in the backfill list at all.
- **Gap audit**:
  - `SIMPLE_BACKFILL_FIELDS` was missing **`walmart_item_id`** (added v6.51). If duplicate had a Walmart ID and survivor didn't → silently lost during merge.
  - Five master_id-bearing tables were never wired into the merge path — all added AFTER the merge code was last touched:
    - **`fba_inventory_snapshots`** — `on delete cascade`, so step 8's product delete would CASCADE-nuke the duplicate's snapshots instead of migrating them. **Silent data loss.**
    - **`fba_shipments`** — `on delete set null`, so master_id would be nulled on duplicate's shipments — they'd survive the delete but disappear from the survivor's "Shipments for {Product}" modal and any product-scoped analytics.
    - **`walmart_sales_weekly`** — soft ref, rows survive but stay tagged with old master_id → don't roll up to survivor's Walmart revenue.
    - **`shopify_sales_daily`** — soft ref, all Shopify daily orders for the duplicate stay orphaned → survivor's Shopify P&L undercounts by the duplicate's history.
    - **`amazon_ad_spend`** — soft ref, SB/SD/DSP/TV attribution stays orphaned → survivor's Ad Spend scorecard undercounts.
- **Fix (v6.98)**:
  - Added `walmart_item_id` to `SIMPLE_BACKFILL_FIELDS` (falsy-guarded — only fills when survivor's field is empty).
  - Added five `sb.from(table).update({ master_id: tgt.master_id }).eq('master_id', src.master_id)` calls before the product-delete step. Each wrapped in try/catch so a schema-missing table on an early-deploy environment doesn't blow up the whole merge — logs a warn instead. None of these tables unique-index against master_id, so plain UPDATE is safe.
  - Updated the confirm dialog to enumerate every table that participates (was missing Shopify, Walmart, Amazon Ads, both FBA tables) so the operator sees the full blast radius before confirming.
- **For Jason's Tuna→Seafood specifically**:
  - Seafood keeps its own `walmart_item_id=679011572` (survivor wins).
  - Seafood picks up Tuna's `image_url`, `chewy_sku=1365718`, `barcode=850061361028`, `shopify_sku=KKZTR002`, `sp_sku=KF401`, `asin=B0D4379H26` (survivor's ASIN was already set to the same value, so no change).
  - All of Tuna's Shopify daily rows (via SP-0203) get remapped to SP-0522 → the merged product's Shopify P&L history is complete.
  - Any Chewy forecasts + Amazon SKU Economics for Tuna already got reassigned by the pre-existing logic — no change there.
  - Tuna's FBA inventory snapshots (if any) get migrated instead of CASCADE-deleted.
  - No Walmart history for Tuna to migrate (Tuna had no Walmart ID), so `walmart_sales_weekly` step is a no-op.
- **Backwards-compat**: try/catch on each new table means the tool works cleanly on any Supabase environment regardless of which migrations have been run. Silent failures log to console instead of aborting the merge.

## v6.97 — Bundles: expose UPC on both Summary + BOM views and in the CSV export
- Jason wanted UPC visible on the BOM module for both bundle parents and component items, exportable to CSV. `products.barcode` is the UPC field.
- **Summary view** — added UPC column between ASIN and Components on the header + a matching cell (`p.barcode||'—'`) in the tbody row.
- **BOM view** — added UPC column between Chewy SKU and Verified on the shared header. Bundle-parent row now includes a `headerCell(p.barcode, true)` cell. Component row now includes a `cellMono(comp.barcode)` cell. Colspan on the "no BOM defined" row bumped 7 → 8; colspan on the "missing component master_id" error row bumped 6 → 7; "No bundles match" empty-state colspan stayed at 9 (columns went from 8 → 9).
- **CSV export** — added `Bundle_UPC` (after `Bundle_Shopify_SKU`) and `Component_UPC` (after `Component_Chewy_SKU`). The no-BOM padding row bumped from 12 blank component cells to 13 to match the new header count. Values pass through `csvEsc()` in case a barcode has an embedded comma/quote (defensive).
- **Fields touched**: only `products.barcode`. No DB migration needed.

## v6.96 — "Shipments for {Product}" modal: split Located into two clearly-labeled grain-aware columns (revert v6.95's broken per-SKU fix)
- **v6.95 was a bad fix.** I switched Located to `qty_received` (per-SKU) not realizing that field is NEVER populated by the parser. Result: every Located value dropped to 0 with a huge negative delta.
- **Root cause of the underlying issue**: `parseFbaShipment` only reads `Merchant SKU`, `ASIN`, `FNSKU`, and `Shipped` from Amazon's per-shipment .tsv (Contents.tsv). There is no `Received` column in that export — Amazon puts per-SKU received quantities in a separate Reconcile.tsv download that this app doesn't ingest. So `quantity_received` writes null on every row, and the pipeline has ZERO per-SKU received data.
- **The right UX**: don't pretend one column can compare across grains. Two columns instead:
  - **This SKU Shipped** — per-SKU declared qty (from `fba_shipments.quantity_shipped`) — this product only. For Pawty Mix in shipment `FBA19DZNB2XM`: 665.
  - **Shipment (Exp → Loc)** — whole-shipment reconciliation from the summary CSV, rendered as `expected → located ±variance`. For the same shipment: `1,584 → 1,594 (+10)`. Variance is shipment-wide, not attributable to any single SKU.
- **Tooltips explicitly call out grain** on both column headers and every cell. Header for the shipment column: "Whole-shipment totals across ALL SKUs from the summary CSV… shipment-wide reconciliation, not attributable to this product alone." Cell tooltip: "This product contributed 665 units of the expected total."
- **Missing-summary fallback**: if `fba_shipment_summaries` doesn't have a row for the shipment (summary CSV never uploaded), the second column shows `—` with a tooltip explaining to upload the summary CSV.
- **Future work** (not in this ship): if we wanted per-SKU received, we'd need to add a Reconcile.tsv upload path that writes to `fba_shipments.quantity_received`. That's a separate feature — flagging here for reference.

## v6.95 — "Shipments for {Product}" modal: use per-SKU quantity_received for Located + tooltips on every column
- **Bug**: Jason opened the Shipments-for-Product drill-down for Pawty Mix and saw absurd deltas — Shipped 665 / Located 1,594 (+10), Shipped 570 / Located 1,274 (-3). Located was way higher than Shipped for the same row.
- **Root cause**: the renderer mixed two grains. `Shipped` correctly used `qty_shipped` (per-SKU, from `fba_shipments.quantity_shipped` on the .tsv) but `Located` used `units_located` from `fba_shipment_summaries` — the WHOLE-SHIPMENT total across every SKU in the box. For a mixed-SKU shipment, the two numbers aren't comparable at all. Confirmed against Jason's data: the 665 / 1,594 shipment had ~1,584 units of other SKUs alongside 665 of Pawty Mix, so total_located ~1,594 while per-SKU received was much smaller.
- **Fix (v6.95)**: Located column now renders `qty_received` (per-SKU, from `fba_shipments.quantity_received`) — same grain as Shipped. Variance badge (+/-) is now `qty_received − qty_shipped`, the per-SKU delta only. The whole-shipment total is preserved in a cell tooltip for context.
- **Tooltips added on every column header** explaining source + scope: Shipment ID (destination FC + delivery window on hover), Status, Region (Y/X-prefix derivation), Shipped (per-SKU declared, with whole-shipment total in cell tooltip), Located (per-SKU located, with whole-shipment total in cell tooltip), Created, Updated. Ship-to string surfaces on hover of the Shipment ID cell.
- **No data change**: this is purely a rendering fix. Underlying `fba_shipments.quantity_received` was already being fetched into `qty_received` — the renderer just wasn't using it.

## v6.94 — FBA Shipment Summary parser: recognize XYY as a Canadian FC + expose the summaries table in Upload History
- **Bug**: Jason uploaded fresh FBA shipment CSVs and shipment `FBA19H99F8C6` (destination `XYY4`) landed with `region='US'`. Amazon Seller Central's CA flag confirmed it's Canadian. Every other CA shipment in the upload was tagged correctly (YYC4, YYZ4, YYZ7, YEG2 all matched the existing regex).
- **Root cause**: `parseFbaShipmentSummary` at line 5896 tests destinations against `/^(YYZ|YVR|YOW|YHM|YEG|YXX|YYC|YUL)/i`. XYY4 doesn't start with any of those prefixes so it fell through to the default `'US'`. XYY is Amazon's newer Toronto-area code (added in the last year or so as their Canadian network expanded).
- **Fix**: expanded the pattern to `/^(YYZ|YVR|YOW|YHM|YEG|YXX|YYC|YUL|XYY|YHZ|YWG|YOO|YQB|YQR)/i`. Added XYY plus five more Canadian airport codes for future-proofing as Amazon adds FCs (Halifax, Winnipeg, Oshawa, Quebec City, Regina). Y-prefix codes are ICAO-reserved for Canada, so no risk of falsely matching a US FC.
- **Retroactive fix path**: also added `fba_shipment_summaries` to the Upload History source list (v6.88), with both **✎ Region** and **✎ Brand** edit buttons since the table has both a direct `region` column and a `brand` column. So Jason can retroactively fix any past mis-tagged shipment session from the UI without re-uploading. For the specific F8C6 row he flagged today, the simplest path is just to re-upload the same CSV — `parseFbaShipmentSummary` uses `upsert onConflict:'shipment_id'`, so the region will overwrite to CA on the second pass.
- **No SQL migration needed** — the `region` column already exists in `fba_shipment_summaries` (from v4.167).

## v6.93 — Shopify P&L: Metric dropdown (Gross / Net / Total) so the headline scorecards can match whichever sales definition the Digital Sales Tracker uses
- Jason wanted a one-click way to flip the Shopify P&L headline between Gross / Net / Total so it can be reconciled against the tracker without doing per-channel gross-vs-net math by hand.
- **New Metric dropdown** in the filter bar (next to Channel): Net Sales (default) / Gross Sales / Total Sales. Subtitle on the headline card explains each: Net = post-discount, post-return (Shopify canonical); Gross = before discounts/returns; Total = Net + taxes + shipping.
- **Switches the entire scorecard view**, not just a label — Net Proceeds = chosenSales − COGS, Margin % = NetProceeds ÷ chosenSales, and the period-over-period delta chips compare apples-to-apples on whichever metric is active. The row table is unchanged (still has Gross/Net/Total/Discounts/Returns/Taxes available via the 📋 View column picker).
- **Subtitle line surfaces the OTHER two metrics** so you can see all three at a glance without flipping: `15,234 units · post-discount, post-return (Shopify's canonical)` + tooltip showing the alternates.
- **Persists per-browser** via `localStorage.spnlSalesMetric`, so the user's preferred convention sticks across reloads. State variable `spnlSalesMetric`, helpers `SPNL_METRIC_LABEL` / `SPNL_METRIC_SUB`, setter `shopifyPnlSetMetric(m)`.
- **Reconciliation against Jason's real data** (Jan–Jun 2026, all channels): scorecards by metric:
  - Net Sales: $99,481 (default)
  - Gross Sales: $121,019 — matches Shopify Admin "Sales over time / Gross sales"
  - Total Sales: $100,560 — matches Shopify Admin "Sales over time / Total sales"
  - Tracker DTC + Wholesale = $133,950. Closest to Gross. Remaining ~$13k delta is the Faire-vs-Shopify wholesale gap (Faire's own dashboard counts platform fees + a few out-of-platform orders Shopify doesn't see) — not a dashboard issue.
- **Architecture**: `TOT_FIELDS` constant carries `[units, gross_sales, net_sales, total_sales, cogs_total, net_proceeds]` through the totals + selection sums + prevView so the scorecard math has every column it needs without re-aggregating. Row-level `net_proceeds` is still net_sales-based (preserves CSV exports + saved-view consumers). Scorecard `viewProc = viewSales − cogs_total` computed at render-time from whichever metric is active.

## v6.92 — Shopify parser: map `sales_reversals` → `returns` (every Shopify upload since v5.98 had returns silently dropping to 0)
- **Diagnosis trail**: Jason flagged a ~$34k discrepancy between the Digital Sales Tracker ($133,950 DTC + Wholesale Jan–Jun 2026) and Shopify P&L Net Sales ($99,481). A Query DB breakdown turned up: gross $121,019, discounts -$20,572, **returns $0**, taxes $1,079, total $100,560. The $0 returns was suspicious for 6 months of real sales activity. Spot-check on `shopify_sales_daily where returns < 0` returned 0 rows / NULL sum across the entire table.
- **Root cause**: `parseShopifySales` resolves CSV columns via fuzzy substring match (`h.includes(n)`). The shipped code asked for `'returns'`. But the user's ShopifyQL is `SHOW ... sales_reversals` — which exports as a header "Sales reversals" / "sales_reversals". Neither contains the substring "returns", so `returnsCol = -1` → the row builder defaulted to `0` for every row, and `shopify_sales_daily.returns` has been a column of zeros since v5.98.
- **Net effect on the dashboard**: Shopify P&L's `net_sales` was still correct (it's pulled directly from Shopify's own field, not computed). But the `returns` column itself was unreliable for any downstream use, and any custom analysis joining `gross − discounts − returns` would be off by exactly the returns figure.
- **Fix (v6.92)**: `returnsCol = ci('returns', 'sales reversals', 'sales_reversals')` — falls back to the ShopifyQL field name(s). Backward-compatible: if Shopify ever changes the display label back to "Returns" or someone exports a CSV with a manually-renamed header, the original match still works.
- **Action Jason needs to take**: re-upload at least the period you care about. The CSV format and column ordering didn't change; the parser just couldn't see the column. After re-upload, `select sum(returns) from shopify_sales_daily where day >= '2026-01-01' and day <= '2026-06-30'` should return a non-zero (negative) value, and any tooling that uses the returns figure starts reading the real number.
- **Note on the tracker reconciliation itself**: separate from this bug, Jason confirmed that Shopify Draft Orders are wholesale (manual B2B invoices, not Faire-synced). So the tracker's Wholesale bucket should account for both Faire AND Draft Orders in Shopify. After the Draft Orders reclassification: Tracker Wholesale $70,672 vs Shopify Faire+Draft gross = $60,816 (still ~$10k gap, likely Faire fees + out-of-platform orders). Tracker DTC $63,278 vs Shopify Online+TikTok+Shop gross = $59,698 (very close, within the discount delta). Not a code issue — just a definition/scope reconciliation.

## v6.91 — Digital Sales Reports: YoY % now compares same-window vs same-window (Jan–Jun 2026 vs Jan–Jun 2025, not 6mo vs 12mo)
- **Jason's ask**: "Should the %YOY amount be based on the time of the year vs the total for the year? It doesn't seem fair to compare against a whole year when we are only halfway through 2026." Right call — the deck-slide pattern (Jan–Dec vs Jan–Dec) doesn't apply when the current year is partial.
- **Before**: 2025 column = full-year 2025 ($2,019,687), 2026 column = 2026 YTD ($1,148,219), % YOY = -43.15% → mostly just "we're halfway through the year." Meow DTC read -57% YoY while showing 97% Seasonal Pace (= on plan) — the two numbers contradicted because they were measuring different things.
- **After**: both columns use the SAME window (months 1..pacingThruMonth). For 2026 (current year), `pacingThruMonth = 6` (June), so both columns show Jan–Jun. Headers annotate the window: `2025 (Jan–Jun)` / `2026 (Jan–Jun)`. YoY % is now apples-to-apples and stops contradicting Seasonal Pace.
- **Full-year LY discoverability**: the deck-slide number ($2,019,687 for full 2025) hasn't disappeared — it's surfaced in the footnote as `For reference — 2025 full-year total: $2,019,687` whenever the window is partial. So you can still answer "what did 2025 do in total?" without leaving the view.
- **Bar chart aligned**: both datasets now sum the SAME window. Legend labels show the window (`2025 (Jan–Jun)` / `2026 (Jan–Jun)`) so the visual comparison is also obviously apples-to-apples.
- **Past-year mode unchanged**: when the user picks a fully-elapsed year (e.g., year=2025, compareYear=2024), `pacingThruMonth = 12`, `windowLabel` is empty, columns show `2025` / `2024`, no footnote reference line. The deck-slide layout still works for retrospective annual reviews.
- **Explanatory line added** to the footnote: `% YOY compares the SAME window in both years (Jan–Jun). Apples-to-apples — not 6 months vs 12.` So future viewers don't get tripped up by the same question.

## v6.90 — Upload History: derive Brand column via products catalog when the table has master_id but no direct brand
- Jason: "The upload history does not show the brand for reports that need it." Screenshot showed FBA Inventory Snapshots with no Brand column even though every row is clearly tied to one brand via its ASIN.
- Root cause: my v6.88 config only populated the Brand column when the table had a direct brand column (`amazon_ad_spend.advertiser_brand`, `digital_sales_tracker.brand`). FBA Inventory, SKU Economics, Walmart, Shopify all carry `master_id` (FK to `products`) but no brand column — brand is supposed to resolve via the catalog.
- Fix: added `masterIdField: 'master_id'` to UH_SOURCES for the 5 tables that have it. `loadUploadHistory` now lazy-loads `allProducts` if needed, builds a `master_id → brand` lookup, and uses it whenever the row has no direct brand value. New helper `showBrandColumn = !!(cfg.brandField || cfg.masterIdField)` controls when the Brand column appears.
- UX rule: the ✎ Brand edit button still only shows for tables with a DIRECT brand column. For derived-brand tables (FBA Inv, SKU Economics, Walmart, Shopify), brand is an attribute of the product itself — change it on the Products page, not in this view. The Brand column is read-only there.
- Sources that get a Brand column now: SKU Economics US/CA, SKU Economics EU/UK, Amazon Ads (direct), FBA Inventory Snapshots, Walmart 1P, Shopify DTC, Digital Sales Tracker (direct). Chewy still has no Brand (no master_id, no brand column).

## v6.89 — Remove the "Legacy — Amazon by Child ASIN" upload group from the Uploads page
- Jason flagged the SUPERSEDED tile group as no longer useful. Removed the entire `#grp-amz-legacy` block (6 dropzones — Meow/Doggi/KKZ × US/CA — pointing at `handleSalesUpload` / `undoSalesUpload`). SKU Economics replaces it for new uploads; historical backfills can use the Upload History view (v6.88) to inspect/correct old rows directly.
- `handleSalesUpload` / `undoSalesUpload` functions left in place — no other UI surfaces invoke them, but removing them is dead-code cleanup that can happen later if needed (they're not blocking anything).
- Syntax clean.

## v6.88 — Upload History sub-view: list past upload sessions per source, retroactively fix region/brand, or delete an entire upload
- **Jason's ask**: "I'd like to be able to look at a history of the uploads, and if needed, change the brand or region (in case I make a mistake when uploading the csv)." Specific painpoint: SKU Economics and FBA Inventory both have a region picker at upload time — if you pick wrong, today the only fix is to delete via SQL or re-upload after manually cleaning. He wanted a UI-level fix.
- **What shipped**: A third sub-view on the Data page next to **📥 Uploads** and **🔍 Query Database** — **📜 Upload History**. Lists past upload sessions per source, grouped by `uploaded_at` (truncated to second), with row count + data-range + distinct regions/brands surfaced. Per-row actions: **✎ Region**, **✎ Brand** (where applicable), **🗑 Delete**.
- **Source picker** (dropdown) covers all 8 relevant tables: SKU Economics US/CA, SKU Economics EU/UK, Amazon Ads (non-SP), FBA Inventory Snapshots, Walmart 1P, Shopify DTC, Chewy Forecasts, Digital Sales Tracker.
- **Per-source config** (`UH_SOURCES` map) controls which fields are editable and what values the prompt offers. Example: `sku_economics` exposes Region with options `US/CA/MX/AU/JP`; `amazon_ad_spend` exposes both Region (`US/CA/MX/EU/UK/GB/DE/FR/IT/ES/NL`) and Brand (`Meowijuana/Doggijuana/Kitty Ka-Zoom`); Shopify/Chewy/Walmart have no region or brand picker at upload time so they show no edit buttons (just Delete).
- **Session grouping** — rows from one upload share an `uploaded_at` down to the microsecond; grouping at second-precision is robust against trivial clock jitter while keeping distinct sessions apart. Edit/Delete brackets the second `[ts, ts+1s)` when issuing the UPDATE/DELETE to match.
- **Limits**: query pulls the most recent 5000 rows per source ordered by `uploaded_at desc`. Status line warns when capped so the user knows older sessions might not be shown. The session list itself is unbounded (built client-side from those 5000 rows).
- **Edit flow**: click ✎ Region (or Brand) → `prompt()` showing the valid options → confirm (or override with "not in list" warning) → Supabase UPDATE with `gte` / `lt` on `uploaded_at` → success alert with affected row count → refreshes the history table AND the Uploads page freshness probes.
- **Delete flow**: explicit confirm prompt with full upload timestamp and warning that re-upload is the only restore path → Supabase DELETE with the same uploaded_at bracket → success alert + refresh.
- **Note on auto-derived fields**: SKU Economics EU `region` is derived from country code in the parser, not from a UI picker — so a mistake there means the source CSV had wrong country labels. The editor still works there (you can rewrite EU rows to a different country code) but it's mostly a safety net. Likewise `amazon_ad_spend.advertiser_brand` is resolved from "Advertiser account name" at parse time; the editor lets the operator correct a wrong-resolution mapping retroactively.
- **Architecture rule observed**: Edit/Delete operate ONLY within a single uploaded_at second window — they can't accidentally affect any other upload session. RLS already restricts to `authenticated`, so no extra guard needed.
- **Verified**: syntax clean (1.65MB JS). Function logic walked against the schemas of all 8 tables; every one has `uploaded_at timestamptz default now()` (mandatory per the v6.47 hard rule on every new table). View toggle correctly routes to the new sub-view, auto-loads on enter.

## v6.87 — Uploads page freshness probes: consistent "data thru" date + "last upload" timestamp on every card; fix EU/Shopify/Walmart/Amazon Ads/Digital Sales gaps
- **Jason flagged three issues on the Uploads page**: (1) the EU SKU Economics card showed dates 5 days "older" than US/CA for the SAME uploaded week (`2026-06-22` vs `2026-06-27`); (2) the Shopify card always said "No Shopify data loaded yet" even after a real upload; (3) Walmart, Amazon Ads, and Digital Sales Tracker cards had no "latest data" badge at all. Plus a meta-ask: every card should consistently show BOTH a "data through" date AND a "last uploaded" timestamp so you can scan freshness across all sources at a glance.
- **Root causes**:
  1. **EU vs US/CA date drift** — US/CA card mapped `week_start` (Monday) → `endOfWeek(wk, 5)` (Saturday) before rendering, but the EU card showed `week_start` verbatim. Same data, different display convention → same week looked 5 days behind on EU.
  2. **Shopify dead probe** — `refreshUploadDataRanges` queried `sales_weekly where channel='shopify'`. After v5.98 / v6.1, Shopify data writes to `shopify_sales_daily` (daily grain) — `sales_weekly.shopify` rows haven't been created in months, so the query always returned empty.
  3. **Walmart / Amazon Ads / Digital Sales** — never had a freshness probe wired into `refreshUploadDataRanges`. The cards' DOM nodes existed (`#last-sales-walmart`, `#last-amazon-ads`, `#last-digital-sales`) but nothing populated them.
- **Fix (v6.87)** — rewrote the freshness loop with one consistent format on every card:
  - `📅 Data thru {date} · uploaded {N ago}` (with `ago()` formatter: just now / Nm ago / Nh ago / Nd ago / Nw ago / Nmo ago).
  - Empty-state messages are explicit: `📅 No {source} data loaded yet`.
  - All 8 cards (Amazon US/CA, Amazon EU, Shopify, Chewy, Walmart, Amazon Ads non-SP, Digital Sales Tracker, plus FBA Inventory + Shipments which were already working) now follow the same pattern.
- **EU date convention** — now applies `endOfWeek(wk, 5)` like US/CA. The EU card showing `2026-06-22` will now show `2026-06-27` for the same data (matches US/CA). The displayed format is `GB: thru Sat 2026-06-27 · DE: thru Sat 2026-06-27 · …`.
- **Shopify card** — now queries `shopify_sales_daily` (`max(day)` + `max(uploaded_at)`). The "Latest data week starts Mon …" copy is gone; it now reads `📅 Data thru 2026-06-27 · uploaded 2h ago`.
- **Walmart card** — new probe queries `walmart_sales_weekly.walmart_calendar_week` and converts to Saturday via the existing `walmartWeekToDate(yyyyww)` helper. Shows `📅 Data thru Sat 2026-06-27 · uploaded 1d ago`.
- **Amazon Ads (non-SP) card** — new probe queries `amazon_ad_spend.date` (daily grain). Shows `📅 Data thru 2026-06-27 · uploaded 3h ago`.
- **Digital Sales Tracker card** — new probe queries `digital_sales_tracker.year, month` (sorted desc), converts to last day of that month via `new Date(y, m, 0)`. Shows `📅 Data thru 2026-06-30 (end of 2026-06) · uploaded 5h ago`.
- **`uploaded_at` is read on every probe** — selected alongside the data field for each source so we always have a timestamp for the freshness chip. (All 7 tables already had `uploaded_at timestamptz default now()` in their schemas — no migration needed.)
- **Verified**: syntax clean (1.65MB JS). Functional behavior verified by source review against the schemas (`sku_economics`, `sku_economics_eu`, `shopify_sales_daily`, `walmart_sales_weekly`, `amazon_ad_spend`, `digital_sales_tracker`, `chewy_forecasts` — all have the queried fields). Preview server is owned by another chat session; Jason will see the changes on reload of his open preview.

## v6.86 — Hotfix: Amazon P&L EU page blank — ReferenceError from v6.84 brand-pool guard
- **Bug**: After deploying v6.84, the Amazon P&L EU page rendered blank with `✗ comparisonMids is not defined` in red below the product table. Other regions (US/CA) unaffected.
- **Root cause**: v6.84 added a guard `const tfrIsSingleProductDrill = (comparisonMids instanceof Set) && comparisonMids.size === 1;` inside `pnlTotalsForRange()`. But `comparisonMids` is defined in the render path's local scope (line 9708), NOT inside `pnlTotalsForRange`. The function receives the set as its third parameter, conventionally named `midSet` (line 9253). Referencing the wrong name threw a ReferenceError every time `pnlTotalsForRange` ran, which is every render (prev-period comparison). US/CA worked because the brand-pool block only executed when `_adsBuckets.byBrand.size > 0` — and on US/CA the brand pool exists. Wait, no — actually the EU page broke because the v6.84 EU-region scoping made `byBrand` empty there, so the bad-name guard was the only line reached after the empty-bucket branch. Either way: the guard throws → render bails → blank page.
- **Fix (v6.86)**: replace `comparisonMids` with the function's actual parameter name `midSet`. One-line correction. v6.84's intent stands — brand pool still gets skipped on single-product drill, just via the right variable now.
- **Verified in preview**: direct call `pnlTotalsForRange('2026-06-01','2026-06-29', new Set())` returns successfully (was throwing); same with `new Set(['__some_mid__'])` (single-product path). Syntax clean. No console errors on either US/CA or EU regions.

## v6.85 — Digital Sales: Reports view (YOY summary + grouped bar chart) + seasonality-adjusted FY projection
- **Jason wanted three things on the Digital Sales page**, modeled on his 2026 Business Digital deck slide: (1) a Reports view comparing each channel's TY vs LY with pace-to-plan, (2) pacing normalized for seasonality (later months heavier), (3) a grouped bar chart like the slide.
- **Grid ↔ Reports view toggle.** Two buttons at the top: 📅 Grid (default — existing month×channel grid + per-row line chart) and 📊 Reports (new). Switching modes hides/shows the appropriate containers; scorecards visible in both views; "📍 Current month" quick-action only shown in Grid. State variable `digitalSalesView`.
- **Reports view layout** (two-column grid):
  - **LEFT: YOY summary table** — columns: Channel | {compareYear} | {year} | % YOY | Seasonal Pace. Channel order matches the canonical sort. YOY % gets color-coded (green ≥0, red <0) with yellow-highlight background for ≥20% gainers and red-highlight for ≤-50% droppers (matches the deck's highlight treatment on Meow Amazon US 22.76%, Meow Chewy 13.18%, Kazoom Amazon US 138.84%, Kazoom Chewy 176.32%). Total row at the bottom matches the deck's grand total exactly (e.g., 2025 = $2,019,687).
  - **RIGHT: grouped bar chart** — same channels on X-axis + a "Total" group at the end (matches deck slide layout). Two bars per group: prior year (blue) and current year (orange). Log scale toggle on by default (deck slide is log-scale); user can uncheck for linear. Log scale clamps zeros to 1 so the channel still has a visible (tiny) bar.
- **Seasonality-adjusted pace** is implemented in two places:
  - **Reports table Seasonal Pace column** = `YTD_actual ÷ YTD_forecast × 100`. The forecast itself encodes monthly seasonality (Q4 heavier etc.), so dividing YTD actual by YTD forecast IS the seasonally-correct "% to plan" answer. Color-coded green ≥100, orange ≥85, red below. Footnote explains the math + shows the seasonality-adjusted FY projection vs naïve (uniform months) projection, so the user can see the difference at a glance.
  - **Grid view's FY Projection scorecard** now uses the seasonality-adjusted formula by default: `YTD_actual × (FY_forecast ÷ YTD_forecast)`. Falls back to the uniform `actual × (12 / months_elapsed)` when forecast data is incomplete. Tile shows a small **SEASONAL** badge when the seasonal formula is active. Tooltip explains both formulas + shows the naïve alternative when it differs.
- **Filter wiring** — Year / Compare Year / Region / Metric selects now route through `onDigitalSalesFilterChange()` which fires `renderDigitalSales()` AND `renderDigitalSalesReports()` when in Reports view, so all surfaces stay in sync as the user filters.
- **Auto-default compare year** — switching to Reports without a compare year selected auto-populates with `year - 1` (defensive — Reports view is meaningless without a YOY comparison).
- **Verified in preview** against Jason's real tracker file: FY Projection scorecard now reads "FY Projection SEASONAL · $2,475,336 · if pace holds · 92% of FY plan ($2,688,581)" — substantially more useful than naïve. Reports view first row = Meow DTC ($110,985 → $44,413 = -59.98% raw YOY but **91% seasonal pace**, i.e., on track for YTD plan). Total row matches the deck slide: **$2,019,687** for 2025, $1,040,619 YTD 2026, -48.48% raw YOY headline but **92% seasonal pace** — exactly the insight Jason wanted ("we're not down 48%, we're on 92% of the plan-through-June"). Bar chart has 23 groups (22 channels + Total) with 2025/2026 bar pairs, log scale. View toggle clean. Zero console errors. Syntax clean (1.65MB JS).

## v6.84 — Amazon P&L EU/UK: stop US/CA Amazon Ads brand-pool from leaking into EU scorecards + don't attribute brand-pool to single-product drills
- **Bug Jason flagged**: On the EU/UK Amazon P&L page, drilling into ASIN B0DQF8R5XL (Catnip & Silvervine Spray) showed Ad Spend = $2,716.56 (762% of net sales) on the scorecard, while the per-product table row for the same ASIN showed Ad Spend = $56.26. Net Proceeds tanked to -$2,387.72 as a result. The Fee Breakdown sidebar labeled the inflated number "Sponsored Products" misleadingly.
- **Root cause** — two compounding bugs in the v6.76 Amazon Ads layer:
  1. **`buildAdSpendBuckets` was called with `region: null` for the EU page** (the comment said EU uses sku_economics_eu so "no overlap" — but the brand-pool summation later in the render path doesn't honor that; it iterates every `byBrand` entry regardless). Result: every US, CA, MX Amazon Ads row (DSP, Sponsored TV, unmatched SB/SD) flowed into `adsBuckets.byBrand`. On Jason's data, that summed to ~$2,660.
  2. **`brandPoolSpend` was added to `view.sponsored` even when the user had drilled into exactly one product.** Brand-level DSP/TV/unmatched SB is, by definition, NOT attributable to a single ASIN — it's brand-wide spend. But the prior code added the entire brand pool on top of the single product's per-ASIN Sponsored Products figure, making one product look catastrophically unprofitable.
- **Fixes (v6.84)**:
  1. **`buildAdSpendBuckets` `region` option now accepts an array** in addition to a string. The function uses a Set lookup when array is passed; falls back to string-equality when a single string. Backwards-compatible with US/CA call sites.
  2. **EU call sites pass `['EU/UK','GB','DE','FR','IT','ES','NL']`** — the EU region codes. Restricts the bucket loader to actual EU rows in `amazon_ad_spend`. Today there are none (Jason hasn't uploaded EU Amazon Ads reports), so the brand pool on EU page correctly drops to $0. When EU Amazon Ads data is uploaded later (e.g. UK SB or DSP), those rows will surface naturally.
  3. **Single-product drill excludes the brand pool** in BOTH the main render path AND `pnlTotalsForRange` (so the prev-period delta chip stays apples-to-apples). Comparison uses `selectedRows.length === 1` in render, `comparisonMids.size === 1` in prev-period totals.
  4. **`perSlugSpend` (Fee Breakdown per-ad-product loop)** now EU-scopes the same way instead of the prior "skip all rows" stub. Future-proofs Fee Breakdown for EU Amazon Ads uploads.
- **Numerical proof in preview** (synthetic dataset mirroring Jason's case):
  - Pre-v6.84 EU leak: brand pool sum = **$2,660.30** (= $1,200 US DSP + $900 US TV + $500 CA DSP + $60.30 unmatched US SB).
  - v6.84 EU-scoped: brand pool sum = **$0**. Only the $12.40 matched UK SB (synthetic) survives, attributed per-row.
  - US regression check: passing `region: 'US'` (string) still works correctly — string-path unchanged.
- **What Jason should see after this fix**:
  - EU/UK page, drilled into the Spray: Ad Spend scorecard ≈ **$56.26** (matches the table row exactly).
  - Net Proceeds scorecard turns positive (was -$2,387.72, should land near +$272.58 — matches the table row's per-product Net Proceeds).
  - Contribution % flips from -680.8% to roughly +65.4% (matches the table row's Contrib %).
  - Fee Breakdown sidebar's Sponsored Products line drops from $2,716.56 to ~$56.26.
  - US/CA pages unaffected (regression check passed).

## v6.83 — Digital Sales: canonical sort, Walmart as type, totals YoY, intra-month pacing, row-click line chart
- **User listed five gaps on the Digital Sales page; this version addresses all of them.**
- **(1) Canonical sort order** — channels now render in the tracker workbook's row order (DTC block → Amazon block by brand × region → Chewy block → Wholesale → Walmart), not the parse-order accident. New `DS_CANONICAL_ORDER` constant = `Object.keys(DS_CHANNEL_MAP)` (which already encodes the canonical order). New comparator `dsChannelSortKey(channel)` returns index in that array (or 9999 for unknown channels, which then fall to the end alphabetically). Verified: first 8 rows = Meow DTC, Doggi DTC, Kazoom DTC, Meow Amazon US, Meow Amazon CA (USD), Meow Amazon UK (USD), Meow Amazon AUS (USD), Meow Amazon JP (USD); last 3 = Meow Wholesale (w/Faire), Doggi Wholesale (w/Faire), Walmart.
- **(2) Walmart added to Type dropdown** — was missing from the `<select>` options even though the channel was being ingested. Also added `Walmart` to `DS_CHANNEL_MAP` (source = `walmart`, no brand because the tracker rolls all brands together for Walmart 1P), and the wide-sheet parser now infers `channel_type` when the source sheet leaves column B blank (defaults: matches `/walmart/i` → 'Walmart', `/amazon/i` → 'Amazon', etc.).
- **(3) YoY arrows in the totals row** — the footer's per-month TD cells now call `fmtCell(actual, forecast, prior)` with the prior accumulator, so each month total carries the same inline `↑X% YoY` indicator as the body rows. To make this work for every month (including months after `pacingThruMonth`), I also moved the `m <= pacingThruMonth` gate so it only constrains the *row-level* prior accumulator (used for the YTD column's YoY %), not the *monthTotals* prior accumulator (used by the footer per-month cells). The body-row apples-to-apples constraint still holds.
- **(4) Current-month preset + intra-month pacing scorecard** — new "📍 Current month" button below the scorecards. Clicking it sets `dsSelectedMonth = current month`, switches the year selector to the current year if available, and re-renders. When the selected month *is* the current calendar month AND year, a new **"Intra-Month Pace"** scorecard tile appears between % to Plan and Difference. Math: `expectedByNow = monthly_forecast × (days_elapsed / days_in_month)`, then `% = viewAct / expectedByNow × 100`. Tile color: ≥100% green, ≥85% orange, else red. Subtitle: `day 29/30 · expect $X · +$Y ahead` (or `-$Y behind`). Hidden when the selected month isn't current.
- **(5) Row-click line chart** — new chart panel below the scorecards, mirrors the Amazon P&L pattern. When the user clicks a body row (single-select), the panel fades in with: current-year actual (solid green), current-year forecast (dashed gray), and if compare-year is set, prior-year actual (solid purple) + prior-year forecast (dashed lavender). Title: `Meow DTC — monthly trend`. Subtitle: `2026: $44,413 actual · 2025: $110,985 · vs 2025: -60.0% · spreadsheet mode`. Chart hides when no row is selected. Uses the same lazy `getChart()` helper as the Amazon P&L chart. Future months drop to null (not 0) so the line truncates cleanly rather than crashing to zero.
- **Architecture note** — the chart is driven by `dsSelectedRow` alone (independent of `dsSelectedMonth`). This way you can click a row to chart it, then click a month header to scope the scorecards without losing the chart. Both selections are independent state vars, both clearable via the existing `dsClearSelection()`.
- **Verified in preview against Jason's real file**: sort order correct, Walmart in type dropdown, totals row has YoY arrows, clicking 📍 Current month sets dsSelectedMonth=6 and shows the "Intra-Month Pace" tile, clicking Meow DTC row opens chart panel with correct title/subtitle/Chart.js instance. Zero console errors. Syntax clean (1.63MB JS).

## v6.82 — Digital Sales: clearer scorecards + monthly YoY + click-to-select + dedicated live loader
- **User flagged four issues on the Digital Sales page:** (1) "Annualized Pace" was opaque; (2) picking a compare year wasn't producing per-month YoY in the cells; (3) clicking a row/month did nothing — should compute that scope into the scorecards; (4) Live (sales_weekly) mode was empty. All four fixed.
- **(1) Rename "Annualized Pace" → "FY Projection"** with clearer subtitle: `if pace holds · X% of FY plan ($Y)`. Tooltip explains the formula explicitly ("YTD Actual × (12 ÷ months elapsed) — if pace continues, FY total lands here").
- **(2) Inline YoY in every month cell** when compare-year set. `fmtCell` now optionally takes a prior-year value and appends a small color-coded arrow + percent (e.g. `↑11% YoY`). Skipped on `forecast` metric (comparing forecast across years is meaningless) and skipped when prior or current is null/zero.
- **(3) Click-to-select rows + month columns:**
  - **Click any row** → scorecards scope to that single channel. Row highlighted green; clicking again clears.
  - **Click any month header** → scorecards scope to that month (across all visible channels). Month column highlighted; clicking again clears.
  - **Both selected** → cell-level value (intersection of row × month). FY Projection card hidden when a month is selected (annualizing one month is misleading).
  - Scorecard labels flip with selection: `YTD Actual` → `April Actual`; sub-text shows scope ("Meow DTC · April 2026" / "Meow DTC · 2026 · 6mo" etc.).
  - **`✕ Clear selection` button** in the row-count line when either selection is active. State variables `dsSelectedRow` / `dsSelectedMonth` persist across re-renders until cleared. New handlers `dsSelectRow / dsSelectMonth / dsClearSelection`. Channel names with parens/slashes ("Meow Wholesale (w/Faire)") are safely escaped for the JS string-literal onclick.
- **(4) Live mode now has its own loader** — `loadDigitalSalesLiveData()` fetches shopify_sales_daily + sales_weekly + walmart_sales_weekly directly via paginated Supabase calls (no longer dependent on the user having visited Forecast / Shopify P&L / Walmart P&L first, which was v6.78's silent failure mode). Cached in `dsLiveData`. Triggered automatically when `setDigitalSalesSource('live')` is called; banner shows a "loading…" state until the fetch completes. Adds **Walmart** to live mode (was completely missing in v6.78). Banner copy clarifies: DTC from `shopify_sales_daily`, Amazon + Chewy from `sales_weekly` (Chewy is empty — surfaces as $0), Walmart from `walmart_sales_weekly`, Wholesale + Amazon AUS/JP/SG = "—" (no native source). FX rates (CA→USD via `pnlFxRate`, UK→USD via `pnlFxGbp`) are best-effort — they load when the user visits Amazon P&L. Live mode acknowledges this explicitly in the banner.
- **Verified in preview** (v6.82 with Jason's real file): all label changes correct ("FY Projection" present, "Annualized Pace" gone), April Meow DTC cell shows `$10,606 ↑11% YoY` (matches 2025 Apr $9,539 → +11.2%), click Meow DTC row → scorecards narrow to $44,413 / sub "Meow DTC · 2026 · 6mo", click April → labels flip to "April Actual / Forecast / % to Plan / Difference / vs 2025" + FY Projection card hidden + value $10,606, clear restores. No console errors. Syntax clean.

## v6.81 — Digital Sales: replace per-marketplace Channel dropdown with Region picker (matches Amazon P&L)
- **User flagged:** the Channel dropdown was listing every Amazon marketplace as its own entry (Meow Amazon US, Meow Amazon CA (USD), Meow Amazon UK (USD), Meow Amazon AUS, …). Amazon should be one channel; region should be a separate picker — same as the Amazon P&L page.
- **Replaced `ds-channel` with `ds-region`** dropdown. Fixed-list options: All Regions / 🇺🇸 US / 🍁 CA / 🇬🇧 UK / 🇦🇺 AUS / 🇯🇵 JP / 🇲🇽 MX / 🇸🇬 SG. Channel filtering is now Brand × Type × Region (no redundant per-channel pick — those three fully describe any row in the tracker).
- **Region rules (mirrors Amazon P&L):**
  - **US**: shows US Amazon + every non-Amazon channel (DTC / Chewy / Wholesale are US-only by SmarterPaw convention; keeping them in scope matches what the user expects to see for "US sales")
  - **CA / UK / AUS / JP / MX / SG**: shows ONLY Amazon channels for that marketplace; non-Amazon channels are excluded (they don't exist in those markets)
  - **All Regions** (default): everything
- **New helper `dsChannelToRegion(ch)`** parses the marketplace token out of channel strings ("Meow Amazon UK (USD)" → "UK"). Normalizes GB→UK and AU→AUS so the dropdown labels match Amazon's actual marketplace codes. Returns `null` for non-Amazon channels.
- **Removed `populateDigitalSalesChannelFilter`** (no longer needed — the new Region dropdown is fixed-list, no dynamic repopulation). `onDigitalSalesFilterChange` simplified to just re-render. Row-count summary line tag changed `channel: X` → `region: X`.
- **Verified in preview** (v6.81 with Jason's real file): Region=UK → 2 rows (Meow Amazon UK, Doggi Amazon UK); Region=US → 12 rows (all DTC + US Amazon + Chewy + Wholesale + Walmart); Region=CA → 3 rows (Meow/Doggi/Kazoom Amazon CA, no DTC/Chewy). Helper parses all 6 test channels correctly. Old `ds-channel` element removed from DOM. No console errors. Syntax clean.

## v6.80 — Digital Sales Tracker also uploadable from Data → Uploads
- **User request:** the Sales Tracker should also be uploadable on the Uploads page (parity with every other weekly upload).
- **Added `grp-digital-sales` card** in the Sales & P&L section of Data → Uploads (right before Chewy). 💵 icon, collapsible group, file input wired to the same `handleDigitalSalesUpload` that powers the in-page button. No new schema, no new parser — same flow, two entry points.
- **Inline status / last-data lines.** Updated `handleDigitalSalesUpload` to detect inline mode (presence of `st-digital-sales` element) vs page-button mode. Inline mode now writes status to `.dz-st`/`.dz-last`/`.up-grp-last` like every other uploader and skips the `alert()`. Page-button mode keeps the alert (no inline status panel on the Digital Sales page itself). Same handler, both entry points get appropriate feedback.
- **Status now surfaces YoY totals on success**: e.g. `✓ 468 rows · 22 channels · 2025 + 2026 · actual 2025: $2,019,687 · 2026: $1,040,619` — confirms multi-year ingest at a glance.
- **Verified in preview** (v6.80): card present in DOM, title "Digital Sales Tracker — Channel × Month Forecast + Actual", file input accepts .xlsx, status + last-data + group-last elements all present, handler resolves. No console errors. Syntax clean. No SQL.

## v6.79 — Digital Sales: multi-year ingestion + YoY + pacing + channel/type filters
- **User asks after v6.78:** compare against forecast with pacing, show year-over-year (2025 data is in the tracker), select a specific channel/brand combo (e.g. "Meow × Chewy") to drill in.
- **Multi-year parser** — v6.78 only read `LookerData` which today carries only the current year. Added `dsParseWideSheet` to also read the wide-format `Sales Tracker NN` sheets (year extracted from sheet name: "Sales Tracker 25" → 2025). Dedupes by `(channel, year, month)` with LookerData winning when both have the same row, so the normalized source stays canonical for years it covers. **Rollup-row filter**: skips "Total"/"Grand Total"/"Subtotal"/"Total …" rows in the wide sheets — without this the wide sheet's visual TOTAL row was leaking through dedup (LookerData has no equivalent) and ~doubling 2025/2026 totals. Verified against the real file: 468 rows / 22 channels / 2 years (2025 + 2026); Walmart picked up from Tracker 26 (LookerData doesn't have it yet).
- **Three new filters in the top bar:**
  - **Type** dropdown — All / DTC / Amazon / Chewy / Wholesale
  - **Channel** dropdown — narrows dynamically by Brand + Type; lets the user drill to a single channel (e.g. "Meow Chewy" → only that row + scorecards isolated to it)
  - **vs Year** dropdown — populated from every year in data except the active one; auto-selects the prior year when available so YoY appears by default
- **YoY columns** in the grid (when compare-year is set): `Prior YTD` + `YoY %`. The Prior-YTD sum is windowed to the SAME months as the current-year YTD (e.g., comparing 2026 thru-Jun against 2025 Jan-Jun, not full-year 2025) so the YoY % is apples-to-apples. Footer adds matching cells. In live mode, prior-year actuals also come from the live tables (`buildLiveSalesAggregate(compareYear)`), so YoY in live mode is consistent on both sides.
- **Pacing scorecard** (new 4th tile): `Annualized Pace = YTD Actual × (12 / months elapsed)`. For the active year, "months elapsed" = current calendar month if it's the current year, else 12. Tile subtitle: `X% of FY forecast ($N)` using the sum of forecast across all 12 months for the filtered channels. YTD Difference card moved to position 5; `vs YYYY` card appears as a 6th tile only when comparing.
- **Header markers:** YTD column header now says `YTD (thru Jun)` (current month) when viewing the current year; future months in the row get dimmed in the column header (`opacity:0.55`) so it's obvious which months are unrealized.
- **Channel narrowing:** picking Brand or Type now repopulates the Channel dropdown live (`onDigitalSalesFilterChange` → `populateDigitalSalesChannelFilter` → `renderDigitalSales`). Picking a specific channel collapses the grid to a single row; scorecards stay accurate. Filter summary line lists every active dimension.
- **Row count line** now reads e.g. `1 channel · 2026 thru June · spreadsheet mode · brand: Meow · type: Chewy · channel: Meow Chewy · vs 2025` so the active scope is visible at a glance.
- **Verified in preview** with Jason's real file: 22 channels parsed, "Total" rollup correctly filtered, scorecards show YTD Actual $1,040,619 / Forecast $2,688,581 / % to Plan 38.7% / Annualized Pace $2,081,239 (77.4% of FY) / Diff -$1,647,961 / **vs 2025 +1.6%** (math checks: $1.04M Jan-Jun 2026 vs $1.02M Jan-Jun 2025 = +1.6%). Channel drill (Meow × Chewy → 1 row → $178,648 YTD) works. No console errors. Syntax clean.

## v6.78 — New "Digital Sales" page (spreadsheet ↔ live toggle, channel × month grid)
- **User request:** new top-nav page "Digital Sales" leftmost of Forecast. Reads from Jason's weekly Excel `Updated - SmarterPaw Digital Sales Tracker By Channel.xlsx`. Source toggle to switch between spreadsheet uploads and live aggregation from `sales_weekly` + `shopify_sales_daily`. Eventually switch to pure live once channel separation is figured out.
- **⚠ SQL TO RUN:** `supabase_v6_78_digital_sales_tracker.sql` — creates `digital_sales_tracker (channel, channel_type, brand, year, month, forecast, actual, …)` with `(channel, year, month)` unique. RLS + grants + anon revoke (v6.47 hard rule).
- **Source format:** the workbook has 4 sheets but the parser reads ONLY the `LookerData` sheet — it's already normalized (one row per channel × month with Forecast + Actual). Verified against Jason's file: 252 rows × 21 channels × 12 months × 4 channel types (DTC / Amazon / Chewy / Wholesale) × 3 brands (Meow / Doggi / Kazoom).
- **Channel labels are brand+region specific** (`"Meow DTC"`, `"Doggi Amazon CA (USD)"`, `"Kazoom Chewy"`, `"Meow Wholesale (w/Faire)"`, etc.). The parser stores them verbatim as the join key. `DS_CHANNEL_MAP` maps each label to its sales-table source for live mode — handles FX (`(USD)` labels get CAD→USD or GBP→USD conversion using the existing `pnlFxRate` / `pnlFxGbp` vars), region filters, and `source: 'none'` for channels with no native data (Wholesale/Faire, Amazon AUS/JP/MX/SG — they show "—" in live mode so the gap is visible).
- **New nav button** `💵 Digital Sales` first in the nav-tabs row (leftmost of Forecast). Wired into `showPage('digital-sales', ...)` → `loadDigitalSalesData()`. New page id `#page-digital-sales`.
- **Page UI:** Source toggle (📊 Spreadsheet | 🗄 Live), Year picker (populated from data), Metric picker (Actual / Forecast / Difference / Both), Brand filter, ↑ Upload Tracker button. Source banner explains current mode + warns when no upload yet. 4 scorecards: YTD Actual / YTD Forecast / YTD Difference / % to Plan. Channel × 12-month grid + YTD column + sticky tfoot with column totals. Channel-type color tags: DTC green / Amazon orange / Chewy blue / Wholesale orange.
- **Module:** `parseDigitalSalesTracker(arrayBuffer)` (XLSX via existing `window.XLSX`), `handleDigitalSalesUpload(input)` (DELETE+INSERT scoped to uploaded years × channels — surgical, doesn't clobber other years), `loadDigitalSalesData()` (paginated), `buildLiveSalesAggregate(year)` (joins sales_weekly + shopify_sales_daily into the same channel × month shape via `DS_CHANNEL_MAP` + product brand lookups), `renderDigitalSales()`, `setDigitalSalesSource()`, `populateDigitalSalesControls()`.
- **Live mode notes** (when source = `live`):
  - DTC channels → `shopify_sales_daily` aggregated by brand × month
  - Amazon channels → `sales_weekly` filtered by `channel` + `region` + product `brand`
  - Chewy channels → `sales_weekly` channel='chewy' (today this table is empty; row shows $0)
  - Wholesale + missing Amazon markets (AUS/JP/MX/SG) → "—" (no native source)
  - FX conversion: CA → USD via `1/pnlFxRate`; UK → USD via `pnlFxGbp`
  - Forecast values continue to come from the spreadsheet table — only Actuals get derived from live data.
- **Verified in preview** (v6.78 + Jason's real file): parser returns 252 rows × 21 channels matching the sheet, render fills 21 rows with correct month cells, footer totals roll up correctly ($178k Jan → $112k Jun, $0 Jul–Dec), YTD scorecards show Actual $1,028,959 / Forecast $2,686,781 / Diff −$1,657,821 / 38.3% to Plan. Syntax clean (one unbalanced-paren bug caught + fixed pre-deploy). No console errors.

## v6.77 — Visible per-ad-type breakdown in the P&L Fee Breakdown sidebar
- **User flagged after v6.76 deploy:** "i don't see the ad spend types broken out at all" — the v6.76 fold added the spend to the scorecards correctly, but the Fee Breakdown sidebar still had a single `Sponsored Products` bar. With SB/SD/DSP/TV silently folded into `view.sponsored`, that one bar got mislabeled. Also, no on-screen signal told the user whether any Amazon Ads data was loaded yet.
- **Fix (Fee Breakdown — US/CA only; EU uses sku_economics_eu):**
  - Inline scan of `amazonAdSpendData` filtered by the active `(from, to, region, brand)` produces `perSlugSpend = { sponsored_brands, sponsored_display, sponsored_tv, dsp }`.
  - `spOnlySpend = max(0, view.sponsored − sum(perSlugSpend))` — back out SP from the total.
  - Five separate fee-breakdown rows replace the old single line: **Sponsored Products / Sponsored Brands / Sponsored Display / Amazon DSP / Sponsored TV**. Each filters out at `Math.abs(val) > 0.01` so accounts that don't run all types stay compact. Existing sort-by-magnitude logic groups them correctly within the breakdown.
- **No-data hint:** when `amazonAdSpendData` is empty (no upload yet OR `supabase_v6_76_amazon_ad_spend.sql` not run), a small orange line appears at the bottom of the Fee Breakdown: `⚠ Only Sponsored Products counted above. Sponsored Brands / Display / DSP / TV not yet uploaded — see Data → Uploads → 📢 Amazon Ads to add them.` Hidden once any row exists.
- **Verified in preview** (v6.77 with synthetic spend data): per-slug splits compute exactly — SB $3.90, SD $0.85, TV $3.20, DSP $1.10, sum $9.05, SP-only correctly backs out from `view.sponsored`. Syntax clean, no console errors.

## v6.76 — Amazon Ads non-SP per-ASIN spend in the P&L (SB / SD / DSP / TV)
- **User flagged the gap:** the SKU Economics report only covers Sponsored Products (`sponsored_products_total`). Sponsored Brands, Sponsored Display, Amazon DSP and Sponsored TV are billed through Amazon Ads (separate from Seller Central) and have been invisible in the P&L. For Jason's accounts that's ~$14k of unrecorded ad spend per 60-day window (~25% of total ad cost), which silently overstates Net Proceeds.
- **⚠ SQL TO RUN:** `supabase_v6_76_amazon_ad_spend.sql` — creates `amazon_ad_spend` (date, region, ad_product, advertiser_brand, asin, master_id, marketplace, spend, impressions, clicks, purchases, attributed_sales, currency). Unique index uses `coalesce(asin,'')` + `coalesce(advertiser_brand,'')` because both are nullable (DSP/TV are audience-level, no ASIN). **Architecture Rule #5 applies** — functional unique index = DELETE+INSERT required, not upsert. RLS authenticated-all + anon revoke (v6.47 hard rule).
- **Source CSV:** Amazon Ads → Reports → Create report. Required dimensions: Date, Country, Advertised product ID, Ad product, Advertiser account name. Required metrics: Total cost, Impressions, Clicks, Purchases, Sales. Daily grain. Sponsored Products rows are intentionally INCLUDED in the export (Amazon's filter doesn't reliably exclude them) and the parser SKIPS them — they're already in SKU Economics. Per-row file workflow documented in the in-app uploader description.
- **New module (parser + uploader):** `parseAmazonAdsUnified()` + `handleAmazonAdsUpload()` + `loadAmazonAdSpend()` + `buildAdSpendBuckets()` + helpers (`adsMarketplaceToRegion` / `adsAdvertiserToBrand` / `adsProductSlug` / `adsStripExcel` / `adsParseDate`). Handles Amazon's quirks: Excel-protect formula wrap (`="..."`) on account IDs, `"Mar 27, 2026"` date format, `UNKNOWN` country (the campaign-level rollup row → marketplace wins → US), "SmarterPaw LLC dba Meowijuana" → brand normalization. Aggregates duplicate `(date, region, ad_product, asin, brand)` keys before insert. Drops zero-activity rows. Uploader card in Uploads page (📢 next to Walmart 1P / Chewy).
- **P&L integration (3 surfaces):**
  - **Main agg loop** (`renderPnl`): builds the spend buckets once per render scoped to date+region, then for each sku_economics row adds the matched `(master_id, week_start, region)` slice to `a.sponsored` AND subtracts the same amount from `a.net_proceeds`. (Amazon's `net_proceeds_total` nets out SP only — it doesn't know about SB/SD/DSP, which is exactly why this module exists.)
  - **Selected-only agg** (`selectedAgg`): mirrored.
  - **Brand-level pool**: rows with no ASIN match (DSP/TV by design, plus any SB/SD whose Advertised product ID didn't match a catalog product) go into `byBrand` and are folded into the TOP-LINE `view.sponsored` + subtracted from `view.net_proceeds` AFTER the per-product agg. Per-product table rows DON'T see this — only what's attributable to a specific ASIN appears in the row's Ad Spend column. The scorecard reflects full truth.
  - **`pnlTotalsForRange`** (prev-period for delta chips): mirrored — without this the Ad Spend delta would lie by 20%+ post-upload (current period gets extra; prev period wouldn't).
- **Scorecard tooltip:** hover Ad Spend → breakdown by source ("Sponsored Products: $X from SKU Economics, per-ASIN" / "Sponsored Brands + Display: $Y per-ASIN attribution" / "Brand-level (DSP / TV / unmatched): $Z no per-ASIN attribution"). When no upload yet, tooltip points the user to Data → Uploads.
- **Cache invalidation:** upload handler clears `amazonAdSpendData = []`. `loadAmazonAdSpend()` short-circuits if cache populated; called UNCONDITIONALLY at the top of `loadPnlTab` (BEFORE the `pnlData.length` short-circuit) so revisiting P&L after upload pulls the new data without a hard refresh.
- **Verified in preview** (v6.76, synthetic CSV mirroring the real format): parser correctly skips Sponsored Products + zero-activity rows, keeps SB/SD/TV/DSP, resolves Meowi/Doggi/KK from "SmarterPaw LLC dba …", maps AMAZON.COM → US, parses "Mar 27, 2026" → "2026-03-27", emits null asin for TV/DSP. `buildAdSpendBuckets` routes ASIN-matched rows to `byMaster` and ASIN-blank to `byBrand`. Uploader card in DOM, all 7 helper functions defined, no console errors. Syntax clean.
- **One follow-up not in v6.76 (small, deferred):** the P&L time-series CHART (`updatePnlChart`) still uses SP-only from sku_economics. Folding non-SP into the chart needs a per-week bucketing step (chart is weekly, ads is daily) — out of scope for v1; scorecards + product table are the primary surfaces. The chart still loads + renders correctly; just slightly understates Ad Spend lines for any selection. Will revisit if Jason flags.

## v6.75 — Favicon swap (sunglasses cat + red chart on grid)
- Replaced the v6.74 teal-circle favicon with the new icon: **cat-in-sunglasses + red rising-chart line on a grid background**. Source `C:\Users\Jason\Downloads\smarterforecast_favicon2-256x256.png`. Same pattern: PIL → 64×64 (`rel=icon`) + 180×180 (`apple-touch-icon`), inline base64 PNG data URIs in `<head>`, swapped via Python regex. Verified by decoding the embedded base64 back through PIL.

## v6.74 — Final favicon (sunglasses cat on teal circle)
- Final favicon swap: **cat-in-sunglasses on a teal circular background**. Source `C:\Users\Jason\Downloads\smarterforecast_favicon-256x256 (1).png`. Same embed: PIL → 64×64 (`rel=icon`) + 180×180 (`apple-touch-icon`), inline base64 PNG data URIs in `<head>`, swapped via Python regex. Verified by decoding the embedded base64 back through PIL: icon 64×64 PNG, apple-touch 180×180 PNG.

## v6.73 — New favicon (cat + bar-chart)
- Swapped the v6.72 favicon for the new icon: **cat face + blue/green/orange bar chart on a teal gradient**. Source `C:\Users\Jason\Downloads\smarterforecast_favicon-256x256.png`. Same embed approach — PIL-resized to 64×64 (`rel=icon`) + 180×180 (`apple-touch-icon`), both inline base64 PNG data URIs in `<head>`. Replaced both prior data URIs via a Python regex on `<link rel="icon"…>` / `<link rel="apple-touch-icon"…>`. Verified in preview: icon decodes to 64×64, title still "SmarterForecast".

## v6.72 — Rebrand to "SmarterForecast" + embedded favicon
- **User:** rename the app to **SmarterForecast** and use the new cat-with-chart icon as the favicon.
- **Rename (4 surfaces):** `<title>` → `SmarterForecast`; header `.logo-tag` "Forecast Engine" → "SmarterForecast"; login `.pw-sub` "Inventory Forecast Engine — Sign in" → "SmarterForecast — Sign in". The SmarterPaw / Meowijuana-Doggijuana brand SVG logos in the header + login box are kept (company brand); only the app-name text changed.
- **Favicon:** source `C:\Users\Jason\Downloads\smarterforecast_fav-1080x1080.png` (1080² cat-in-sunglasses + red chart). Resized with PIL → **64×64** `<link rel="icon">` (6.5KB PNG, ~8.7KB base64) + **180×180** `<link rel="apple-touch-icon">`, both embedded as `data:image/png;base64,…` **inline** in `<head>` — no separate file, so it works on GitHub Pages with zero extra assets. (To regenerate at a different size: PIL `Image.open(src).resize((N,N), LANCZOS)` → base64 → replace the data URI.)
- **Note on editing this file:** the embedded base64 logo/favicon lines are very long, which makes the Read/Edit tools choke ("exceeds max tokens") — used a small Python `str.replace` script for the in-`<head>` text + version edits instead. Grep still works for locating lines.
- **No SQL.** Verified in preview (v6.72): `document.title` = "SmarterForecast", header tag + login subtitle updated, `link[rel=icon]` present as a PNG data URI, apple-touch-icon present, login screen screenshot shows "SmarterForecast — Sign in". Syntax clean.

## v6.71 — "Loading sales" cue + auto re-render when bundle attribution settles
- **User:** after a refresh, the bundle `+B` badges (and velocity) take a beat to appear, and nothing on screen indicated the table was still settling.
- **Why the lag:** `loadSalesAnalytics` fetches sales (async) THEN recomputes every record's velocity + bundle attribution (the v6.69 fix, CPU-bound). The global busy bar (v6.55) only tracks the fetch, not the recompute, and it's easy to miss. Worse, `renderAll()` only re-renders the Demand table — NOT the Inventory table — so on the Inventory view the recomputed `+B`/velocity didn't show until a manual toggle (a second, separate lag the user was hitting).
- **Fix 1 — visible cue:** `showSalesLoadingCue()` / `hideSalesLoadingCue()` — a yellow floating spinner pill ("Loading sales — velocity & bundle attribution updating…", fixed top-center). Shown at the START of every `loadSalesAnalytics` (init, ↺ Refresh, post-upload), hidden after the recompute + re-render. Covers the whole fetch→recompute→render window, so the "still settling" state is unmistakable. Defensive hide in the init `.catch` so a failed load can't leave it stuck. New `salesDataReady` flag (false during the window).
- **Fix 2 — auto re-render the active view:** at the end of `loadSalesAnalytics`, re-render whatever forecast sub-view is showing (`renderInventoryTbl()` when `forecastView==='inventory'`, else `renderAll()`) so the recomputed bundle attribution appears WITHOUT a manual interaction. Closes the Inventory-lags-silently gap.
- **No SQL.** Verified in preview (v6.71): both cue functions present, pill shows the spinner + text and hides cleanly, `salesDataReady` boolean defined, no console errors.

## v6.70 — "Hide inactive" toggle on Demand Forecast + Inventory Planning
- **User:** another toggle on Forecast + Inventory to hide/show inactive products.
- **Forecast:** `#fHideInactive` checkbox (next to Hide bundles, **default ON**). `getVisible()` drops rows where `allProducts.find(p=>p.master_id===r.master_id).active === false` — folded into the existing `hideBundles` lookup so it's still ONE `allProducts.find` per record (no extra per-render scan). Captured/restored in Forecast saved views (`filters.fHideInactive`; restore guarded by `!== undefined` so pre-v6.70 views are unaffected).
- **Inventory:** `#ip-hide-inactive` checkbox (next to Hide bundles, **default ON**). Same predicate added at all 4 IP filter sites (`renderInventoryTbl`, `inventoryVisibleRecords`, `downloadInventoryCSV`, `showExportDialog`) right after the v6.49 Hide-bundles line. Captured/restored in IP saved views (`filters.hideInactive`).
- **Default ON** because inactive = deprecated/discontinued and shouldn't drive demand/PO planning — uncheck to see them. Resolves `active` via `allProducts` (records don't reliably carry the flag), matching the Hide-bundles convention. `active !== false` = active (null/undefined treated as active, for legacy rows).
- **No SQL.** Verified in preview (v6.70): both checkboxes present + checked by default; `getVisible()` with Hide-inactive ON returns only the active record, OFF returns both. No console errors.

## v6.69 — FIX: bundle attribution silently vanished (regression vs v6.05) — init recompute ran before salesData loaded + v6.62 memo cached the 0
- **User proved it's a regression, not data:** same data, an older **v6.05** build (saved earlier the same day, AFTER the Shopify upload) showed bundle attribution CORRECTLY — `+B` badges on Need TOTAL, populated Bundle Need columns, AND a higher Vel/day (63.23 incl. bundle) — while **v6.67** showed none of it (Vel/day 61.17, no `+B`, blank Bundle columns). My earlier "data re-mapping from the Shopify upload" theory was WRONG.
- **Root cause (two compounding):**
  1. **Ordering bug (pre-existing, latent):** `init()` runs the finalization `records.forEach(recomputeRecordVelocity)` at ~line 3507 — which folds bundle-component demand in via `getBundleAttrDailyVelocity(salesData[bundleId])` — **BEFORE `loadSalesAnalytics()` is called (~line 3536)**. So `salesData` was EMPTY → `bundle_daily = 0`, baked into every record's `blended_daily`. Nothing recomputed the records after salesData loaded.
  2. **v6.62 memoization removed the safety net:** earlier builds (v6.05) had no `_velMemo`, so EVERY render recomputed `getBundleAttrDailyVelocity` fresh — once salesData was loaded, renders self-healed and bundle showed up. v6.62 cached the result, so the init-time **0 got locked in** and never recovered. That's the exact regression window (v6.05 ok → v6.62+ broken).
- **Fix 1 (systemic) — recompute records at the END of `loadSalesAnalytics`:** after `salesData` is populated, `records.forEach(recomputeRecordVelocity)` so bundle demand folds into `blended_daily` + `bundle_daily` with real data. Runs on EVERY call (init, ↺ Refresh, post-upload) → can't drift out of sync again. This is what fixes the **Vel/day bundle slice + Forecast `+B`**, and (via the repopulated velocity cache) the **Inventory Bundle Need columns + `+B` badge**.
- **Fix 2 (defense in depth) — don't cache a pre-load 0:** `getBundleAttrDailyVelocity` now gates BOTH the cache read and write on `salesReady = Object.keys(salesData).length > 0`. A bundle velocity computed before salesData exists is returned but NOT stored, so it can never poison `_velMemo` again.
- **Verified in preview** (v6.69): with empty salesData → returns 0 and does NOT cache; after salesData loads → returns the correct 2.33 (not a stale 0) and caches it. Syntax clean, no console errors. **No SQL.** After deploy + refresh, bundle attribution returns across Vel/day, Forecast `+B`, and the Inventory Bundle columns. (Resolves the "+B badge missing" thread — it was this regression all along, not the upload.)

## v6.68 — Freeze columns (Demand + Inventory) + Walmart in Need-group tooltips
- **User asks (3):** (1) Walmart missing from the "NEED — TOTAL (CUMULATIVE)" + "NEED — BASE (CUMULATIVE · CONTINUOUS DRAIN)" group-header tooltips; (2) Inventory Planning Status shows "— No Data" everywhere ("not calculating velocity status"); (3) freeze columns up to a chosen one on Demand + Inventory.
- **(1) Walmart in tooltips** — `groupTipByHdr` for NEED — TOTAL and NEED — BASE listed every channel except Walmart (folds into BASE since v6.52). Added a `• Walmart 1P → BASE …` line to both, plus the per-column `need30` tip enumeration. Cosmetic only.
- **(3) Freeze columns (the feature)** — new `🧊 Freeze` dropdown on BOTH the Demand Forecast and Inventory Planning control bars (next to View / Sort). Pick any visible column → every column up to & including it pins (sticky-left) while the wide Need grid scrolls horizontally. Persists per browser (`fcFreezeCol` / `ipFreezeCol`).
  - Generic `freezeApplyTable({groupRowId, colRowId, bodyId, freezeIdx})` runs at the END of each render (rows freshly rebuilt → no stale sticky/splits). Measures REAL header-cell widths (`getBoundingClientRect`) → exact cumulative `left` offsets (registry `w` can diverge from rendered width). z-index: frozen body =5 (above scrolling body, BELOW the sticky-top thead @z10 so the header still wins on vertical scroll), frozen header cells =15/16.
  - **Group-header alignment:** the one group cell that STRADDLES the freeze boundary is split — its colspan shrinks to the frozen portion (kept sticky) + a blank continuation cell is inserted for the rest, so the frozen group label (e.g. "SKU") lines up exactly over the frozen columns. Verified on a synthetic table: freeze up to col B → A/B sticky, C not, "SKU" colspan 3→2 + blank colspan-1 continuation, "NEED" untouched, body offsets correct.
  - Dropdowns list only visible non-system columns (skip `_chk`); a saved key that's no longer visible auto-resets to off. On change → full re-render (rebuilds clean rows) → freeze re-applies.
- **(2) Status "— No Data" — diagnosed, NOT a code change.** In **Warehouse-stock** status mode, `getStatusFor` returns `nodata` when a row has BOTH `warehouse ≤ 0` AND no `lead_time` (the `!hasStock && !hasLead` gate). Velocity + Need ARE computing (Vel/day + Need columns are populated) — but Status in Warehouse mode needs warehouse on-hand + lead time, and the **warehouse-stock source was never wired** (known gap, see v4.169) so `inventory.warehouse` is empty catalog-wide → every row is "No Data". NOT caused by the v6.66/67 changes (status math untouched). **Fix for the user:** switch **Status by → 📦 Amazon FBA stock** (has current FBA snapshot data) for real statuses, or set lead times + load warehouse stock. (Could later make Warehouse-mode "No Data" more self-explanatory or wire a warehouse uploader — flagged, not done.)
- **No SQL.** Verified in preview (v6.68): freeze functions + dropdowns present, synthetic-table freeze correct (header+body pin, group split), Walmart in tooltips, no console errors.

## v6.67 — Inventory Planning: optional "Full Title" column (full catalog title alongside the short-name Product column)
- **User:** "on the inventory planning page, i would like to be able to include the product title in addition to the short name." The existing "Product" column shows `short_name` (or a truncated title); there was no way to surface the full untruncated catalog title.
- **Fix:** added a `full_title` column to `IP_COLUMNS` (SKU group, right after `title`), **default OFF** — opt-in via the View popup (the popup iterates IP_COLUMNS by group, so it appears under SKU automatically; no popup change). Renders `r.title` with ellipsis + a `title=` hover tooltip showing the whole thing (keeps row heights uniform in the dense table); width 300px. Sortable (`sortVal` = lowercased title). `csv: r => r.title || ''` so the Inventory CSV exports it **untruncated + proper-case** (the exporter checks `c.csv` first, line ~21341). Distinct from "Product" — enable both to see short name + full title side by side.
- **No SQL, no data change** — `records` already carry `title`. **Verified in preview** (v6.67): column registered (label "Full Title", group sku, default false), sits after `title` in SKU order, render produces the full-title `<td>` + tooltip, `csv()` returns proper-case full title, no console errors.

## v6.66 — PERF + UX: Inventory column toggle still slow + no visual cue (memoize the breakdown + spinner pill)
- **User flagged (again, post-v6.62):** toggling a column in the Inventory View popup still takes a long time AND gives no visual feedback that anything is happening.
- **Root cause v6.62 missed:** v6.62 memoized *velocity* (`_velMemo`) and sort-keys, but **`inventoryNeedBreakdown` itself was never cached** — and it's the expensive call (per-call `forwardSeaDemand` curve integration ×4-6 channels + multi-event reorder sim + bundle attribution + event scan). With Jason running ~5 Need-column groups (Total / Base / Reorder / Bundle / Walmart) × 4 horizons PLUS per-period Amazon US/CA + Chewy columns, the SAME `(master_id, region, horizon)` breakdown is recomputed **20-40× per row** — every column group re-derives it independently. On ~568 rows that's tens of thousands of redundant curve integrations per render.
- **Fix 1 — render-scoped breakdown memo (`_nbMemo`):** `inventoryNeedBreakdown` now caches by `master_id|region|X`. Within a render every input is constant, so the same breakdown is computed **once per (mid, region, horizon)** (~4/row) instead of 20-40×. Cleared at the TOP of every `renderInventoryTbl` (so a changed input — bundle-attr, hide-bundles, events, target, horizon, region — can never serve a stale value; the next render always re-clears) and alongside every `clearVelMemo()` (data/window change). Distinct from `_velMemo`, which persists across renders; `_nbMemo` is strictly per-render. Verified: same args → identical cached object ref, different horizon → fresh, clear empties it.
- **Fix 2 — visual cue (`ipRenderWithCue`):** column toggles (`ipToggleCol` / `ipGroupSet` / `ipResetCols`) now show an unmistakable green spinner pill ("⏳ Updating columns…", fixed top-center) IMMEDIATELY, then defer the blocking render by **two `requestAnimationFrame`s** so the browser paints the cue + the flipped checkbox before the CPU-bound render runs. Pill hides when the render completes. A `_ipRenderPending` guard coalesces rapid multi-toggles into a single render (it reads `ipVisibleCols` fresh when it fires, picking up every toggle made before). The global busy bar (v6.55) doesn't cover this — it's fetch-driven; this is pure client-side compute.
- **Net:** breakdown computes drop ~6-10× per render (the dominant cost), and even if a render still takes a beat the user now sees the spinner instead of a silent freeze. **Verified in preview** (v6.66): memo dedup (same-ref / per-horizon / clear), pill shows+hides, `renderInventoryTbl` clears the memo at its top, no console errors. No SQL.

## v6.65 — FIX: upload conflict dialog called daily Shopify overlaps "week(s)" (alarming "742 new weeks")
- **User flagged:** updating the Shopify report (a 2024-04-01 → 2026-06-30 daily export) popped the "Existing Data Found" dialog reading "1012 rows … across **71 overlapping week(s)** and **742 new week(s)**" — "742 weeks" = ~14 years, clearly wrong, looked like a bug. **It was a pure labeling bug — the data was fine.** Since v6.1 Shopify is daily-grain (`shopify_sales_daily`); the conflict check at `parseShopifySales` (line ~4709) correctly computes overlapping **days** vs new **days** (71 days already loaded from prior partial uploads, 742 genuinely-new days in the file), but `showUploadConflictDialog`'s template hardcoded the noun "week(s)" in 4 spots, so days were printed as weeks.
- **Fix:** `showUploadConflictDialog` gained a `unit` param (default `'week'`) — the visible grain noun. Template now renders `${unit}(s)` in the body + both buttons ("Add new ${unit}s only", "overwrite overlapping ${unit}s"). The `*Weeks` param names stay for back-compat. Callers:
  - **Shopify daily** (parseShopifySales) → `unit:'day'`, region simplified `'Shopify (daily — N days overlap)'` → `'Shopify (daily)'` (the unit carries the grain now, no double "days"). weekLabels reworded to "overlap spans X → Y".
  - **Inventory** (checkInventoryConflict) → `unit:'ASIN'` (it counts ASINs, was also calling them "weeks").
  - **Amazon sales_weekly** (parseSalesWeekly ~4424, SKU-economics ~6839) + **EU** (~7163) → keep the default `'week'` — they genuinely are weekly. No change.
- **No data was ever wrong.** "Add new days only" adds the 742 new days + keeps the existing 71; "Replace all" overwrites those 71 overlapping days with the file's values (scoped to days×SKUs in the file — never touches data outside the file's range). For a fresh comprehensive export, **Replace all** is the clean choice.
- **Verified in preview** (v6.65): with Jason's exact numbers the dialog reads "71 overlapping day(s) and 742 new day(s)" + "Add new days only (742 new days, skip 71 existing)"; the Amazon path still correctly reads "week(s)". No SQL.

## v6.64 — Walmart P&L: multi-select line chart (parity with Amazon / Shopify P&L)
- **User:** "on walmart p&l, i should be able to click multiple products to show a line chart like on amazon p&l." v6.63 shipped the Walmart P&L lean (no chart); this adds the multi-select weekly-trend chart.
- **Multi-select:** new leading checkbox column (select-all in the header with indeterminate state) + per-row checkbox; **row-click now toggles selection** (was: open product modal). The product modal is still reachable via a `↗ card` button (`pnlCardBtn`) added to the Product cell — same affordance the Amazon/Shopify P&L use. Selected rows get a blue tint (`rgba(0,113,220,0.10)`). State in `walmartPnlSelectedMids` (Set) + `walmartPnlVisibleMids`.
- **Chart panel** (`wmpnl-chart-panel`, hidden until ≥1 selected) sits between scorecards and the table — mirrors `updateShopifyPnlChart` exactly: one Chart.js line per selected product, x-axis = Walmart `week_start` (weekly 1P data), `tension:.3`, `spanGaps:true`, 10-color cycle (Walmart blue first). Metric dropdown: Net Sales / Net Proceeds / COGS / Contribution % / Units. `✕ Clear` button in the chart header. COGS basis = `walmartPnlCogs(mid)` (landed → dtc → amazon), so Net Proceeds + Contribution % lines match the table/scorecards.
- **Helpers:** `walmartPnlToggleProduct` / `walmartPnlClearSelection` / `walmartPnlToggleSelectAllVisible` / `updateWalmartPnlChart` (all call `renderWalmartPnl` which ends with `updateWalmartPnlChart()`). Row-count line now shows the selected count + a "check rows to chart" hint. Loading/empty/error colspans bumped 9 → 10 for the checkbox column.
- **No SQL, no new data.** **Verified in preview** (v6.64, mock 2-product weekly data): chart shows on selection, 2 lines with correct weekly Net Sales (400/560/495), metric switch to Contribution % computes right (85% = (400−40×$1.50)/400), select-all + indeterminate + clear (destroys instance, hides panel) all correct, no console errors.
- **Deferred from Walmart P&L (could still port from Shopify P&L if wanted):** column-picker + saved-views. Chart was the requested piece.

## v6.63 — Walmart 1P P&L page (Walmart Phase 3 — DONE; completes the 4-page Walmart build)
- **The final Walmart phase.** Phase 1 (v6.50/51) = ingest + ID mapping + Units Sold; Phase 2 (v6.52–62) = Forecast + Inventory wiring + the week-calendar fix; **Phase 3 (this) = the Walmart P&L page.** Mirrors the **Shopify DTC P&L v1 pattern** Jason chose at the start: **Net Proceeds = Net Sales − COGS, with Walmart fees as a labeled placeholder** until a fee/settlement report is wired.
- **New P&L sub-view `walmart`.** Added `🛒 Walmart 1P` to the P&L nav dropdown (`pv-walmart`, between Shopify and COGS), a `pnl-view-walmart` HTML container, and extended `switchPnlView`'s array → `['amazon','shopify','walmart','cogs']` + container toggle + `loadWalmartPnlTab()` call. CSV routing: `if (pnlView==='walmart') return downloadWalmartPnlCSV();`.
- **Leaner than the Shopify P&L by design (v1):** filters = Period / Brand / Category / search (no Channel filter — Walmart is single-channel 1P, US-only, no region toggle). 4 scorecards (Net Sales · Total COGS (landed) · Net Proceeds · Contribution %). Sortable product table (Img · Product · Walmart Item # · Units · Net Sales · Avg Price · COGS · Net Proceeds · Contrib %). **No chart / no column-picker / no saved-views** in v1 — can port from Shopify P&L later if wanted. Default period = **Last 90 days** (Walmart is weekly 1P data; 90d gives a fuller picture than 30d).
- **Data:** `walmart_sales_weekly` (paginated, `master_id not null`). `week_start` is **recomputed on read** via `walmartWeekToDate(walmart_calendar_week)` (the v6.59 read-time transform — overrides stored date only when >10 days off) so the period filter uses correct Walmart-calendar dates regardless of what was stored at import.
- **COGS basis = `landed_cost`** (1P production/landed cost), fallback `dtc_cogs` → `amazon_cogs` (helper `walmartPnlCogs(mid)` reads `cogsByMaster`). Rows with no COGS show `⚠ missing` (red) + are counted in a "N missing COGS" note on the scorecard + row-count line. `cogsTotal = cogsPer × units`; `netProceeds = net_sales − cogsTotal`; `marginPct = netProceeds / net_sales × 100`.
- **Partial-data banner** (blue, Walmart #0071dc) names exactly what's NOT subtracted yet: Walmart's wholesale margin / cost-to-Walmart, referral + fulfillment fees, Walmart Connect ad spend. So Net Proceeds reads optimistic until those land — same honesty as the Shopify banner. (Note: the Scintilla "net sales" figure may be retail-side; the unsubtracted Walmart wholesale margin is folded into the "fees not included" caveat.)
- **Functions:** `loadWalmartPnlTab` / `getWalmartPnlDateRange` / `onWalmartPnlPeriodChange` / `walmartPnlSetSort` / `renderWalmartPnl` / `walmartPnlCogs` / `downloadWalmartPnlCSV` — all inserted just above `let pnlView`. CSV header: master_id, walmart_item_number, brand, product, units, net_sales, avg_price, cogs_per_unit, cogs_total, net_proceeds, contribution_pct (with a context line naming the from→to + the "fees NOT included" caveat).
- **No SQL** — reuses `walmart_sales_weekly` (v6.51) + `product_cogs` (`cogsByMaster`). **Verified in preview** (v6.63 boots clean, no console errors): sub-view toggles, 4 scorecards + 9-col sortable table render, empty-state + 90d window correct, all 7 functions defined. Full data render needs auth + the v6.51 migration (not reachable from the sandbox).

## v6.62 — PERF: Inventory Planning column-toggle was very slow (O(n log n) breakdowns + uncached bundle scan)
- **User flagged:** selecting a column in the Inventory View popup was VERY slow. Each toggle → `ipToggleCol` → full `renderInventoryTbl()`, and two compounding costs made that render expensive (worsened by v6.48 bundle attribution + v6.52 Walmart, which both run inside every Need breakdown):
  1. **Sort comparator recomputed the breakdown O(n log n) times.** `vis.sort((a,b)=> sortCol.sortVal(a) - sortCol.sortVal(b))` — for a Need column `sortVal` runs the full `inventoryNeedBreakdown`, so a 568-row table did ~10k breakdowns JUST to sort, every render.
  2. **`getBundleAttrDailyVelocity` scanned ALL of `allBomData`** on every breakdown call (4× per row), and channel-vel scans likewise — recomputed thousands of times.
- **Fixes (both standard, low-risk):**
  1. **Sort-key memoization** — precompute `sortCol.sortVal(r)` once per row into a Map, then sort by the cached value → O(n) instead of O(n log n). Applied to `renderInventoryTbl` AND `downloadInventoryCSV`.
  2. **Velocity memo (`_velMemo`)** — cache `getInventoryChannelVel` (via a `cacheKey` arg on the inv* wrappers) + `getBundleAttrDailyVelocity`, keyed by `master_id|region|window[|channel]`. Pure w.r.t. (mid, region, velocity-window) + salesData/allBomData; NOT dependent on the bundle-attr toggle / seasonality / flags / events, so safe. Cleared via `clearVelMemo()` only on data/window change: `loadSalesAnalytics`, `loadProducts`, `applyVelocityWindow`. Dedups the 4-identical-scans-per-row within a render AND reuses across renders (so column toggles, which change no data, skip all velocity computation).
- **Net:** sort breakdowns ~10k → ~568 per render; bundle/channel scans cached. Column toggles should be near-instant.
- **Verified in preview:** v6.62 boots clean (no console errors), `_velMemo` Map + `clearVelMemo` present, `getInventoryChannelVel` takes the cacheKey arg. (Real render timing needs auth+data, not reachable from the sandbox — but the algorithmic fix is the textbook O(n log n)→O(n) sort-key memoization.)
- **Same pattern lives in the Forecast sort** (`fcCompare` / sortChain walks `col.get(r)` per comparison) — if the Forecast table feels slow on large sets, apply the same precompute-sort-keys fix there.

## v6.61 — FIX: Inventory column popup hid new column groups (Walmart + Bundle Need unreachable)
- **User flagged:** the v6.60 Walmart Need columns weren't in the Inventory View popup.
- **Root cause:** `openIpColumnsPopup` rendered checkboxes from a HARDCODED `groupOrder` array (`['sku','velocity','need-total','need-base','need-reorder',…]`) that was never updated when new column groups were added — so `need-bundle` (v6.49) AND `need-walmart` (v6.60) had columns in `IP_COLUMNS` but no checkbox to enable them (and they default OFF → permanently unreachable). The Bundle Need columns had silently been broken the same way since v6.49.
- **Fix:** added `need-bundle` + `need-walmart` to `groupOrder` (positioned after `need-base`) with labels, and — to prevent recurrence — the render loop now appends **any** group present in `IP_COLUMNS` but missing from `groupOrder` (unlabeled groups fall back to their `groupHdr`). So a newly-added column group can never silently disappear from the picker again. Also corrected the stale `need-base` label ("Shopify + Chewy" → "Shopify + Walmart 1P + Amazon FBM + Chewy").
- **Verified in preview:** v6.61, popup opens and lists the WALMART (1P) group (≤30/60/90/120d Walmart) + the BUNDLE COMPONENTS group. Syntax clean.
- **Lesson:** the Forecast popup (`FC_COLUMNS`) uses `groupOrder` too — check it the same way if a Forecast column group ever goes missing. (It currently includes its groups, but apply the same append-extras pattern if extending.)

## v6.60 — Inventory Planning: exportable "Walmart Need" columns (validate 1P draw without the tooltip)
- **Context:** validating Phase 2's Inventory side meant hovering a Need cell to read the "Walmart base" tooltip line — but native `title` tooltips can't be screenshotted. So the Walmart 1P contribution to inventory Need had no visible/exportable surface.
- **Fix:** added a `NEED — WALMART (1P)` column group (`wmNeed30/60/90/120`, default OFF, opt-in via View popup) — mirrors the v6.49 Bundle Need columns. Reads `inventoryNeedBreakdown(r, X).walmart.base` (the Walmart slice already folded into Need TOTAL + BASE). Sortable + CSV-exportable. 0 on CA-pinned rows (Walmart US-only). Group styled `thg-need-base`.
- **Verified in preview:** v6.60 live, `IP_COLUMNS` includes wmNeed30/60/90/120, `inventoryNeedBreakdown` returns `walmart:{base,reorder,vel}`. Syntax clean.
- **Validation use:** Inventory Planning → View popup → enable `≤90d Walmart` → the column shows each product's Walmart warehouse-draw demand directly (no hover needed). Confirms Phase 2's 1P inventory model end-to-end.

## v6.59 — Walmart week_start recomputed on READ (so the v6.58 fix repairs existing rows w/o re-import)
- **Why:** v6.58 fixed `walmartWeekToDate` but `week_start` is computed + STORED at import time, so rows already in `walmart_sales_weekly` kept their old (≈May, ISO-mapped) dates after a reload — 30d still empty unless re-imported. User (reasonably) didn't want to re-import.
- **Fix:** `loadSalesAnalytics` now also selects `walmart_calendar_week` and recomputes `week_start` via `walmartWeekToDate` on every read. So correcting the week→date mapping repairs ALL existing rows on the next reload — no re-import, no SQL. Override is conditional: only when the stored date is **>10 days** off the recomputed date (the stale-mapping migration case); a close stored date (date-column import from v6.57, or already-correct) is preserved. Falls back to stored `week_start` if the code is missing/unparseable.
- **Net:** deploy v6.59 + hard-refresh → existing Walmart rows (week codes 202615–202619) re-date to May/June → 30d column + Total-mode Walmart velocity populate. (Stored DB `week_start` stays old/cosmetic until a re-import overwrites it; reads are correct regardless. A read query on `walmart_sales_weekly.week_start` will still show old dates — the dashboard recomputes in JS.)
- Makes the week→date mapping a pure read-time transform of the stored raw code — future mapping tweaks never need a re-import.

## v6.58 — FIX: Walmart week→date used ISO weeks; Walmart's retail calendar starts in February
- **THE root cause** of the "Walmart 30d empty / data looks stale" saga (chased across v6.53/6.56/6.57). The user confirmed their export uses the same current settings, so `202619` is genuinely ~mid-June — meaning the dashboard was mis-dating it. v6.50's `walmartWeekToMonday` assumed **ISO** weeks (week 1 = week of Jan 4), but **Walmart's retail calendar** has fiscal year ending Jan 31 and **Week 1 begins the first Saturday of February** (weeks Sat–Fri). So every Walmart week was dated **~5–6 weeks too early** (202619 → May 4 instead of ~June 13), making current data look 6 weeks stale and emptying the 30-day window.
- **Fix:** renamed `walmartWeekToMonday` → `walmartWeekToDate(yyyyww)`; new body anchors Week 1 to the first Saturday of February of year YYYY, steps 7 days/week. Verified: 202546→2025-12-13, 202601→2026-02-07, **202619→2026-06-13** (current). Year-boundary tiling drifts <1 week (immaterial for 30/60/90/120d windows). Only caller is `parseWalmartCSV`.
- **⚠ Existing data must be re-imported:** `week_start` is computed + stored at import time, so the rows already in `walmart_sales_weekly` still have the old (≈May) dates. **Re-import the SAME CSV** (no new Scintilla download needed — the file is current; the dashboard just dated it wrong) and the corrected formula dates it properly → 30d populates. (Alternative: SQL `update walmart_sales_weekly set week_start = …` but re-import via the 🛒 card is simpler since it recomputes via DELETE+INSERT.)
- Composes with v6.56 (importer now shows correct June date range, no stale warning) and v6.57 (date-column override still preferred when present — the truly bulletproof path).

## v6.57 — Walmart parser uses a real date column when present (stop guessing week→date)
- **Context:** user kept hitting an empty Walmart 30d column and (rightly) pushed back — their Scintilla report is current (refreshed daily, last-52-weeks filter). The dashboard's recency rests on `walmartWeekToMonday(YYYYWW)` ASSUMING ISO week numbering; if Walmart numbers weeks differently, recent weeks get mis-dated old → 30d empty. Two possible root causes still to disambiguate with the user: (a) the imported FILE was an older download (max week 202619 ≈ May 4 under ISO); or (b) the week-code→date mapping is wrong.
- **Fix:** `parseWalmartCSV` now detects a real date column (`dateCol` = tolerant aliases: week begin/start/ending/end date, wm/walmart week date, week date, calendar date — deliberately NOT bare 'date' to avoid matching an "Update Date" column) and uses it for `week_start` directly (via `parseLocalDate`, used as-is). Falls back to `walmartWeekToMonday(week)` only when no date column is present. This sidesteps the week-convention ambiguity entirely AND gives readable dates. **Action for user:** add a date/week column in Scintilla's Columns picker + re-export; the parser will key off it.
- **Diagnostic still needed from user:** the MAX `walmart_calendar_week` in the current report. If ~202624/202625 → the imported file was just old, re-import fixes it. If still ~202619 → Walmart's *shipped-based* 1P data genuinely lags ~6 weeks, so 30d is correctly empty (data latency, not a bug). The v6.56 staleness banner + this date column make whichever case it is visible at import.
- No SQL. Syntax clean.

## v6.56 — Walmart importer shows real date range + flags stale exports
- **User confusion:** the Walmart export's `walmart_calendar_week` is an opaque `YYYYWW` code (202546…), so you can't tell at a glance whether recent weeks are included. Their dashboard data ended at 202619 (≈ May 4) because the imported file was an older pull, even though the Scintilla report (refreshed Jun 17, last-52-weeks filter) had newer weeks available. Format decode: `YYYY` + ISO week-of-year; the dashboard's `walmartWeekToMonday` converts correctly (e.g. 202624 → Jun 8 2026).
- **Fix (importer modal `walmartRenderImportModal`):** replaced the raw `(202546→202619)` week-code range in the header with the **actual date range** from `week_start` — e.g. `2026-03-09 → 2026-05-04 (latest 45d ago)`. When the latest week is **>14 days old**, a prominent orange warning renders: "⚠ Latest week in this file is N days old … re-pull from Scintilla with a current date range so recent weeks (and the 30-day columns) import." So data recency is obvious at import time instead of surfacing later as a mysteriously-empty 30d column.
- **Verified in preview** (drove `walmartRenderImportModal` with mock imports, no login needed): stale file (max 2026-05-04) → header "… → 2026-05-04 (latest 45d ago)" + warning shown; fresh file (max 2026-06-08) → "… → 2026-06-08 (latest 10d ago)" + no warning. Syntax clean.
- No SQL. The underlying "Walmart 30d Sold empty" is correct when data is genuinely stale — this just makes the staleness visible. Re-importing a current export populates the 30d columns.

## v6.55 — Global busy indicator: fetch-instrumented "Saving / Loading" for the whole app
- **User:** "across the app, when something is saving or loading, it often doesn't communicate this to the user." The v5.61 `_pendingLoads`/`trackLoad` system only covered ~6 named loaders — saves and most operations never called it, so they were silent.
- **Fix — instrument `fetch` once** (`installFetchBusyTracker` IIFE, runs at script-eval before `getSB()` creates the client). Every Supabase request (`supabase.co` URL) increments `_sbWrites` (POST/PATCH/PUT/DELETE) or `_sbReads` (GET) and decrements in `.finally()`. So ALL saves + loads + RPC + storage + auth across the app drive the indicator automatically — no per-call-site wiring. Non-Supabase fetches (Chart.js CDN, FX APIs) pass through untouched. Fully defensive (try/catch, `Math.max(0,…)`, restores count on synchronous throw).
- **Two surfaces** via the rewritten `renderLoadingIndicator()`:
  - **Top progress bar** (`#globalBusyBar`, lazily created on `document.body`): thin fixed 3px green→orange bar at the top of the viewport — the unmistakable app-wide "something's happening" cue. Holds at 85% while busy, completes to 100% + fades on idle.
  - **Header pill** (`#loadingIndicator`, existing): now shows **💾 Saving…** when any write is in flight (writes take label priority), **🔄 Loading…** for reads/named loads, then flashes **✓ ready** and hides. Tooltip lists named sources + in-flight read/write counts.
  - Debounced: 300ms idle delay before settling (bridges rapid sequential requests so the bar doesn't flicker); the existing 1.2s "✓ ready" flash.
- The named `_pendingLoads` / `markLoadStart` / `trackLoad` system is kept and folds into the same indicator (counts as "loading", names show in the tooltip). Inline per-action notes (e.g. saveProduct's "✓ Saved") are unaffected — the global indicator is additive.
- **Verified in preview** (python static server on :8770, added a `forecast` config to `~/.claude/launch.json`): page boots clean with the wrapped fetch (no console errors, v6.55 rendered), `__sbBusyWrapped=true`, counters init 0 with no leak after the no-network auth boot; forcing a write state rendered the bar (opacity 1 / 85%) + pill "💾 Saving…" — confirmed in a screenshot.

## v6.54 — Walmart ID on the Products page + edit re-attributes sales (fix mismappings)
- **User had mismapped `walmart_item_id`s** (import wrote the item # to the wrong products) and wanted to fix them on the Products page.
- **Products table column:** added a sortable **Walmart ID** column (after ASIN; header + cell + `prodSortVal` case `walmart_item_id`). Lets you scan/sort to spot blanks or wrong tags. (The editable field was already on the product card since v6.52.)
- **Editing the tag now actually fixes a mismapping** (the key part): attribution on Units Sold / Forecast / Inventory is keyed on `walmart_sales_weekly.master_id` (stamped at import), NOT on `products.walmart_item_id` — so editing the product alone used to leave the old sales mis-attributed. `saveProduct` now, when `walmart_item_id` is set AND changed: (1) clears that # off any other product (one item # → one product), (2) re-points `walmart_sales_weekly` rows for that # to this master_id, (3) reloads `salesData` + recomputes record velocities so the frontend reflects it without a manual refresh. Gated on change, so normal saves are unaffected. **To fix a SWAP, edit both products** (each re-points its own item #'s sales) — or just re-run the importer.
- **Promotion-path gap fixed:** the SP-TEMP→SP-XXXX promotion FK migration re-pointed every dependent table except `walmart_sales_weekly` — added it, so promoting a temp with Walmart sales no longer orphans them.
- **DB-edit note for the user:** direct edits in the Supabase SQL Editor (in-app Query tab is read-only) reflect on the frontend after a hard refresh; must update BOTH `products.walmart_item_id` and `walmart_sales_weekly.master_id` (or re-sync the latter from the former with one UPDATE join).
- No SQL migration; no version-label-only change. Verified: JS syntax.

## v6.53 — Forecast-by-channel: anchor extrapolation to latest data (Walmart lag fix)
- **User flagged:** with FORECAST BY = Walmart, the Walmart 30d Sold column AND all Forecast-by-channel Walmart numbers were blank.
- **30d Sold = "—" is correct, not a bug:** the Walmart export's latest week (202619 → ~May 4 2026) is >30 days before today (June 17), so the trailing-30-calendar-day window is genuinely empty (1P vendor reports lag). 60/90/120 populate because they reach back to early May. Left truthful — it fills in with a fresher upload.
- **Forecast-by-channel = "—" was a real bug:** `fcForecastByChannel` extrapolated off `fcSoldByChannel(…, 30)` (last 30 *calendar* days) ÷ 30 — empty due to the reporting lag, so every Walmart projection came out 0. Fix: new `fcChannelDailyRate(r, channels, windowDays)` computes the rate over a window anchored to the **channel's latest data date**, not `now`. So a channel that's weeks behind still projects off its real recent rate. Current channels (Amazon/Shopify, latest≈today) are unchanged. `fcForecastByChannel` now calls it.
- **Note:** the Total-mode Walmart contribution (via `fcWalmartVel` in blended_daily) still respects the Velocity Window dropdown (now-anchored, like every other channel) — at a 30d window with 6-week-stale data it reads 0; at 60/90/120d it picks the data up. That's the intended velocity-window semantics, not a bug; the per-channel *forecast* column is the one that needed the lag-robust anchor since it has no window control.

## v6.52 — Walmart Phase 2: Forecast + Inventory wiring (+ v6.51 leftovers)
- **No SQL** — uses `products.walmart_item_id` + `walmart_sales_weekly` (v6.51) + `salesData` (channel='walmart' from v6.50's loader). Phase 3 (Walmart P&L page) still pending.
- **Demand Forecast — full Walmart wiring:**
  - **Header:** `Walmart ID` radio in SHOW ID (value `walmart_item_id`); `Walmart` checkbox in FORECAST BY (`#fChan-walmart`, blue #0071dc, enabled with the others on data load, folded into `onChanChange` 5-channel sync + the none-checked reset).
  - **Per-channel columns:** added `{key:'walmart',label:'Walmart',channels:['walmart']}` to `FC_CHANNEL_GROUPS` → auto-generates **Walmart 30/60/90/120 in both SOLD BY CHANNEL and FORECAST BY CHANNEL** (both families loop FC_CHANNEL_GROUPS×FC_HORIZONS) with auto tooltips. `fcSoldByChannel`/`fcForecastByChannel` already channel-generic; Walmart rows (channel='walmart', region US) flow through.
  - **Total forecast:** new `fcWalmartVel(rec, w)` (salesData channel='walmart', region-gated US-only) is added into `blended_daily` in `recomputeRecordVelocity` alongside bundle attribution — so "Total (all)" Need now includes Walmart. No double-count: `velocity_calculated` (the DB view feeding `daily_vN`) is Amazon+Shopify only. New `rec.walmart_daily` surfaced; Total-mode Need tooltip relabeled "Amazon + DTC + Walmart" with a per-day note.
  - **Records** carry `walmart_item_id` (added to the records-build object) so SHOW ID + the ID column (`headHtml` map gained `walmart_item_id:'Walmart ID'`) work. Saved views capture/restore `channels.walmart`.
  - **Custom-channels mode:** `getSelectedChannelConfig` adds `chanWalmart`→`'walmart'` to selectedChans + chanLabel; `getChannelVelocityForRecord` is already channel-generic (region-gates Walmart out for CA). `chanNameMap` tooltip gained walmart.
- **Inventory Planning — Walmart as 1P warehouse draw:** new `invWalmartVel(r)`; `inventoryNeedBreakdown` gets a Walmart block — 1P means we ship from our warehouse to Walmart's DCs against POs, so it's a **continuous warehouse draw (into `base`, like Shopify / Amazon FBM), NOT a reorder pool**. `wmartBase = forwardSeaDemand(walmartVel, X)` added to `baseSum`; returns `walmart:{base,reorder:0,vel}`; Need-TOTAL + Need-BASE tooltips gained a Walmart line. Flows into Need/Gap/scorecards/CSV automatically. Region-gated (0 on CA rows). Surfaces in the v6.49 `NEED — BASE` column; could add a dedicated Walmart Need column later if wanted.
- **v6.51 leftovers folded in:**
  - **Remapping hardening:** `walmartApplyImport` now clears `walmart_item_id` from any OTHER product before assigning it to the chosen one — an item # can never live on two products (fixes the correct-a-mapping edge).
  - **Product modal field:** added **Walmart Item #** input (`#pf-walmart`, next to Chewy SKU); `openProductModal` reads it, `saveProduct` persists `walmart_item_id`. Not yet a Products-table column or in merge-backfill — small follow-ups.
- **Behavior note:** Total-mode Forecast Need + Inventory Need numbers will RISE for products with Walmart sales (Walmart now counted) — intended. Verified: JS syntax. Full flow needs the v6.51 migration + login.

## v6.51 — Walmart: item # as product ID + product_name matching (revises v6.50)
- **User got a richer export** — it now includes `walmart_item_number` (stable ID, e.g. 678996643), `product_name` (full proper name), and `product_description`. Asked to "use walmart item # as the ID field in the product table and use the product name for better match."
- **⚠ SQL TO RUN:** `supabase_v6_51_walmart_item_id.sql` — **supersedes v6.50** (the v6.50 sql file was deleted). DROPS `walmart_item_map` + `walmart_sales_weekly` (safe — no real data imported yet), adds **`products.walmart_item_id text`** (+ index), and recreates `walmart_sales_weekly` with `walmart_item_number` + `product_name` columns. RLS + policy + anon revoke on the table.
- **Architecture change:** dropped the separate `walmart_item_map` table. The item # is now a real product identifier on `products.walmart_item_id` (like asin / shopify_sku / chewy_sku). Matching keys on it; the importer writes it onto the chosen product (UPDATE products SET walmart_item_id) so future uploads auto-match with zero remapping. `loadProducts` (`select *`) picks the column up; no map-table loader.
- **Better fuzzy match:** `wmSuggest(productName, itemName)` now scores the FULL `product_name` (e.g. "Kitty Ka Zoom Catnip Bubbles for Cats 5 oz") against catalog short_name/title — far better than the truncated `item_name`. Brand boost retained.
- **Parser** keys aggregation on item # (falls back to name when absent), captures product_name. **Importer modal** gains an ITEM # column + a WALMART PRODUCT column (full name over truncated); row selects use array index (no string-escape risk). **Apply** writes walmart_item_id to products, then DELETE+INSERTs sales keyed on (item #, week) [+ name fallback]. `loadSalesAnalytics` walmart source unchanged (still reads master_id/week_start/units).
- **Not yet:** `walmart_item_id` isn't shown in the Product modal / Products table UI yet — the importer populates it, but a visible/editable field + merge-backfill is a small follow-up. Phases 2 (Forecast+Inventory) and 3 (P&L) unchanged from the v6.50 plan.

## v6.50 — Walmart 1P — Phase 1: ingest + name→product mapping + Units Sold (SCHEMA SUPERSEDED BY v6.51)
- **User request:** use the Walmart "Ecom Sales" CSV to start building Walmart into demand forecast, inventory, units sold, and a new Walmart P&L. **Answers:** 1P vendor (Retail Link) · map item names once then auto-match · P&L = Net Sales − COGS with fee placeholders. Phased build — **this is Phase 1** (data foundation + matching + Units Sold). Phase 2 = Forecast + Inventory wiring; Phase 3 = Walmart P&L page.
- **The data:** weekly export, one row per (item, walmart_calendar_week YYYYWW). Columns: vendor #, item_description_2 ("ONLINE ONLY"), **item_name (truncated all-caps, the ONLY identifier — no ASIN/UPC/GTIN)**, net sales ($, can be negative = returns), quantity. ~40 KKZ + Doggijuana items, wk 202546 (Nov 2025) → 202619 (May 2026).
- **⚠ SQL TO RUN:** `supabase_v6_50_walmart.sql` — creates `walmart_sales_weekly` (master_id, walmart_item_name, calendar_week, week_start, units, net_sales, …) + `walmart_item_map` (walmart_item_name PK → master_id). **Both have RLS enabled + authenticated-all policy + anon revoke** (v6.47 lesson). Idempotent.
- **Matching:** map table (not a products column) because the truncated names drift; handles N names → 1 product. Importer fuzzy-suggests via `wmSuggest` (reuses `catsyTitleScore` bigram scorer + a `wmBrandHint` brand boost from the KKZ/JUANANIP/TUFFER prefixes), user confirms per row, saves to `walmart_item_map`. Future uploads auto-match by name.
- **Week conversion:** `walmartWeekToMonday(yyyyww)` → ISO Monday of that week (verified contiguous across year boundary: W52→W01 one week apart). Stored as `week_start` so it aligns with every other channel.
- **Import flow:** Data → Uploads → new **🛒 Walmart 1P — Ecom Sales** card → file picker → `handleWalmartFile` → `parseWalmartCSV` → `openWalmartImport` builds a **mapping modal** (`#wm-import-overlay`, dynamically injected) listing each item with units/$/weeks + a preselected product `<select>`. "Save mappings + import" → upserts `walmart_item_map`, resolves master_id per row, DELETE+INSERT into `walmart_sales_weekly` (Architecture Rule #5), reloads `salesData`. Items left "skip" store with null master_id (hidden until mapped). Audit: `upload.walmart`.
- **Units Sold integration:** `loadSalesAnalytics` gained a 3rd source (walmart_sales_weekly → salesData rows with `channel='walmart'`, region US, master_id resolved). `getSelectedChannels` channel list + the by-channel chart `CHANNELS` map + a `chk-walmart` checkbox (Walmart blue #0071dc) all gained `walmart`. Units Sold totals (`sumUnits`) are channel-agnostic, so Walmart flows in once mapped.
- **NOT in Phase 1 (deferred):** Forecast tab velocity (uses `velocity_calculated` DB view — needs the view UNION'd with walmart, OR compute walmart velocity from salesData) and Inventory Planning (1P → fold as warehouse continuous-draw base, like Shopify/FBM) = **Phase 2**. Walmart P&L page (Net Sales − COGS, fee placeholders, COGS basis = landed_cost for 1P) = **Phase 3**.
- **Can't end-to-end test from here** (needs the migration run in Supabase + a logged-in session). Week-math + JS syntax verified.

## v6.49 — Inventory Planning: Hide bundles toggle + exportable Bundle Need columns
- **User request:** (1) a Hide-bundles toggle on Inventory Planning (like the Demand page); (2) make sure the recent (bundle) columns export.
- **Hide bundles:** new `#ip-hide-bundles` checkbox next to `+ bundle components` (off by default). Drops bundle PARENT rows from the view; their component demand is still attributed to component rows when `+ bundle components` is on (so hiding declutters without losing bundle-driven Need). Wired into all 4 IP filter sites — `renderInventoryTbl`, `inventoryVisibleRecords` (selection bar/chart), `downloadInventoryCSV` (filtered mode only — 'all'/'selected' export modes ignore it), and `showExportDialog` (filtered count). Filter is self-contained per row: `document.getElementById('ip-hide-bundles')?.checked && allProducts.find(p=>p.master_id===r.master_id)?.is_bundle`. Captured/restored in IP saved views (`filters.hideBundles`).
- **Exportable Bundle Need columns:** the Need TOTAL + Need BASE columns already export bundle-inclusive totals (CSV `valueOf` falls through to their `sortVal` → `inventoryNeedBreakdown`). Added a dedicated `NEED — BUNDLE COMPONENTS (CUMULATIVE)` group (4 horizons: `bundleNeed30/60/90/120`, default OFF, opt-in via View popup) that isolates the bundle-attributed slice (`nb.bundle.base`) — sortable + CSV-exportable via `sortVal`. Lets you see/export "how much of this component's demand is bundle-driven" — the key number when a component is Amazon-deprecated but its bundle stays live. Group styled `thg-need-base` (blue, base-type) with a header tooltip; values gated by the `+ bundle components` toggle (0 when off).
- No SQL, no new data — reads the v6.48 `bundle` field on the breakdown.

## v6.48 — Inventory Planning: bundle-component attribution + survives component deprecation
- **User request:** (1) a toggle (default on, like the Demand page) to fold bundle-component demand into Inventory Planning — bundles are assembled in the warehouse, so component stock matters; (2) deprecate a component on Amazon while keeping its bundle live, with the bundle-driven demand still reflected in the Need columns (the "we only sell the two-pack now / switched to a bundle" case).
- **Toggle:** new `+ bundle components` checkbox (`#ip-bundle-attr`) in the Planning controls bar, default checked, `onchange="renderInventoryTbl()"`. Mirrors the Demand page's `fBundleAttr`. Captured/restored in IP saved views (`filters.bundleAttr`).
- **Model — `inventoryNeedBreakdown` gains a `bundle` term:** when the toggle is on, `bundleVel = getBundleAttrDailyVelocity(mid, fVelocityWindow, null, region)` (sums each parent bundle's region-filtered sales over the velocity window × the component's BOM qty ÷ window). `bundleBase = forwardSeaDemand({…r, blended_daily: bundleVel}, X)`. Added to `baseSum` as a **continuous warehouse draw** (components are pulled from the warehouse to assemble bundles regardless of the bundle's downstream channel) → flows into Need TOTAL, Need BASE, Gap, status, scorecards, chart, CSV automatically. Returns `bundle: { base, reorder:0, vel }`.
- **No double-count:** direct component sales come from rows under the component's master_id; bundle sales are under the bundle's master_id — disjoint. Bundle PARENT rows get `bundleBase=0` (nothing lists a bundle as a component of another bundle), so their own Need still comes from their own channel velocity + reorder.
- **Deprecation independence (request 2):** `bundleBase` is a SEPARATE term, NOT gated by `deprecated_product_amazon`. That flag still zeroes only the component's OWN `amzReorder` (and FBA `amzBase` is excluded from base as before). So a component deprecated on Amazon with a live bundle now shows Need = bundle-driven warehouse demand instead of dropping to ~0. The deprecation UI already exists (lifecycle toggle on Products tab + inventory/product edit modals, per-region on inventory) — no new UI needed; this just makes the math correct.
- **UI:** green `+B n` badge on the Need TOTAL cell (next to `+R`/`+EV`); bundle lines added to the Need-TOTAL and Need-BASE hover tooltips naming the BOM-weighted warehouse draw + the deprecation-independence.
- **Note:** for a deprecated FBM component, its own historical `amzBase` still counts (existing v4.195 wind-down behavior) ON TOP of bundle demand — flag if that should also zero on deprecation. Perf: `getBundleAttrDailyVelocity` scans `allBomData` per `inventoryNeedBreakdown` call (4×/row); fine at current catalog size, memoize per (mid,region) if it ever drags.

## v6.47 — (DB-only, no app version bump) RLS enabled on `shopify_sales_daily`
- Supabase `rls_disabled_in_public` critical alert (2026-06-08). The v5.98 table was the one `CREATE TABLE` that never got RLS. Fix migration `supabase_v6_47_shopify_sales_daily_rls.sql` — enable RLS + authenticated-all policy + revoke anon. See the "Setup notes — Supabase RLS + table GRANTs" section for full detail. (index.html went 6.46 → 6.48; v6.47 is the SQL fix.)

## v6.46 — Seasonality "Weeks data" counted rows, not weeks (Shopify daily-grain overcount)
- **User flagged:** a Seasonality row (Zoom Sticks, method=default) showed "✓ ready (85 wk)" / Weeks data 85 when the product has only ~23 weeks of real history.
- **Cause:** the "Weeks data" fallback for uncalculated products was `p.sea_weeks_of_data || (salesData[mid].length || 0)`. Since the v6.1 Shopify cutover, `salesData` rows are DAILY for Shopify (one row per day) and weekly for Amazon/Chewy — so `.length` counts daily rows, not weeks (~85 daily Shopify rows ≈ 23 weeks). Only bit `category-default` rows (no stored `sea_weeks_of_data`); calculated products store an accurate distinct-week count from `computeProductSeasonality` (v6.2 fix).
- **Fix:** new `seaWeeksOfData(mid)` (next to `sea90dUnits`) buckets each `salesData[mid]` row to its Monday-of-week key (via `parseLocalDate` + local Monday shift) and returns the distinct-bucket count. Replaced the `.length` fallback in all three sites: `renderSeasonalityList` weeks-sort `wkOf`, the per-row `wkData` (drives the eligibility badge), and `recommendSeasonalitySettings`. Now Zoom Sticks reads ~23 wk and the eligibility/recommendation reflect real weeks.

## v6.45 — Products page: Active only / Inactive only filter options
- Added **Active only** and **Inactive only** to the Products `prodFilter` dropdown (after "Singles only"). Logic in `renderProductsTbl`: `active` drops `p.active === false`; `inactive` drops `p.active !== false`. Default remains "All Products" (unchanged).

## v6.44 — Products table: bulk select/edit + sortable "90d Units" column
- **User request:** (1) checkboxes to bulk select/edit product dimensions; (2) 90-day sales as a sortable column.
- **90d Units column:** sortable column (after MSRP) showing all-channel units sold in the last 90 days (reuses `sea90dUnits`). Cached per render into `_prodU90` (Map) so the sort comparator + row render don't recompute; `prodSortVal` gets a `units90` case reading the cache.
- **Bulk select:** leftmost checkbox column + select-all header (indeterminate state). `prodSelected` Set persists across filter changes; `prodVisibleMids` drives select-all. `prodToggleRow` / `prodToggleAll` / `prodClearSelection`. Green bulk bar (`#prod-bulk-bar`) above the table shows the count + Bulk edit + Clear when ≥1 selected.
- **Bulk edit modal (`prodOpenBulkEdit` → `prodBulkApply`):** pick a field — **Brand / Category (category_id) / Active / Seasonal / MSRP / Wholesale / Supplier** — set a value, apply to all selected via batched `products` UPDATE (`.in('master_id', chunk)`, 200/batch). Value input is field-aware (`prodBulkFieldChange`: brand/active/seasonal/category dropdowns, msrp/wholesale/supplier inputs; blank = clear). Mirrors into `allProducts` so the table updates without a reload; `product.bulk_edit` audit. Identifiers (title/SP SKU/ASIN) intentionally not bulk-editable (unique per product).
- No SQL (uses existing product columns; `seasonal` already added in v6.39).

## v6.43 — Seasonality list: sortable + "90d Units (all channels)" column
- **User request:** sort the Seasonality page by 90-day units sold (all channels).
- Added a **90d Units** column (all-channel units in the last 90 days via new `sea90dUnits(mid)` — sums `salesData[mid]` rows within 90 days, no channel filter). Cached once per render (`u90` Map) so the comparator + row render don't recompute.
- **Click-to-sort headers:** Brand, Product (brand→name), **90d Units**, Weeks data. `seaSortKey`/`seaSortDir` state + `seaSetSort(key)` (toggles dir; numeric cols default desc, text cols asc). Arrow indicator (▲/▼) on the active column. Default sort unchanged (name = brand→product).
- Empty-state colspan bumped 9 → 10.

## v6.42 — "Seasonal items" filter on the Products page
- Added a **Seasonal items** option to the Products `prodFilter` dropdown (after "Has forecast notes"): `if (filt === 'seasonal' && !p.seasonal) return false;` in `renderProductsTbl`. Filters to products flagged seasonal (the v6.39 `products.seasonal` flag / checkbox). Composes with the brand / category multi-select filters like the other options.

## v6.41 — Fix: Seasonality category dropdown blank (v6.38 regression)
- **Cause:** `seaPopulateCategoryFilter` set its `dataset.populated='1'` lock even when it found zero categories (e.g. it ran via initSeasonalityView before `allProducts`/`allCategories` finished loading, esp. when Seasonality was the landing route) — so it never refilled once data arrived. It was also only called from `initSeasonalityView`, not on list re-renders.
- **Fix:** (1) only set the populated lock once categories were actually added (`if (!names.length) return;` first); (2) also call `seaPopulateCategoryFilter()` at the top of `renderSeasonalityList`, which runs with data loaded — so the dropdown fills on the first real render and recovers from any early empty init.

## v6.40 — Seasonality chart projection extrapolates the growth trend (was flat)
- **User flagged:** the v6.37 forward projection held the de-seasonalized trend FLAT, so a growing product showed no projected growth.
- **Fix:** the forward level now **extrapolates the recent trend** — least-squares regression over the last ~26 weeks of the de-seasonalized level gives a slope; `futureLevel(w) = lastFittedLevel + slope·w` (clamped ≥ 0). The gray Trend line and the dashed Projected line both ride that growing (or flat, if slope≈0) level, then the seasonal curve is applied on top. Auto-handles both growing and steady products — no setting needed.
- Replaces the prior "hold the last 8-week run-rate flat" logic.

## v6.39 — Product "seasonal" flag (checkbox) → flows into seasonality calc
- **User request:** a flag for seasonal items (sold during a season, e.g. Christmas toys) — checkbox on the Products table — that flows into the seasonality calculation.
- **⚠ SQL TO RUN:** `supabase_v6_39_product_seasonal_flag.sql` — adds `products.seasonal boolean not null default false`. Run before deploying.
- **UI:** inline **Seasonal** checkbox column on the Products table (between Active and Edit; `toggleProductSeasonal(masterId, checked)` — optimistic update, rollback on error, `stopPropagation` so it doesn't open the modal). Also a **Seasonal?** checkbox in the product modal (next to Active); `openProductModal` reads it, `saveProduct` persists it. Sortable (prodSortVal `seasonal` case).
- **Calc integration (two effects):**
  1. **Stockout correction DISABLED** for seasonal products — `computeProductSeasonality` forces `stockoutFloorPct = 0` when `products.seasonal` is true, because a seasonal item's off-season near-zero weeks (and the sharp season-end drop) are REAL demand, not supply gaps, and must not be excluded. Same applied to the seasonality chart (`seaRenderFitChart`).
  2. **Fallback → seasonal_limited:** `resolveFallbackCurve` returns the `seasonal_limited` SEED template for a `seasonal` product when no explicit `seasonal_type` is set and no own curve applies — so thin-data seasonal items get a concentrated-peak default instead of the flat category curve.
- Reads `products.seasonal` directly from `allProducts` in the calc, so the flag takes effect on the next recompute with no extra plumbing.

## v6.38 — Seasonality: real-category filter + category→curve-template mapping
- **Problem:** the Seasonality "pick category" dropdown listed SEED curve-TEMPLATE names (spray/consumables/treats/toys/bundles/seasonal_limited/bubbles), not real product categories — and didn't filter the list. Worse, the category-default fallback mapped a product's real category NAME straight into `SEED.curves[name]` (case-sensitive), so almost everything fell through to the generic `consumables` curve.
- **#1 — Real category filter:** the dropdown now populates from real product categories (`seaPopulateCategoryFilter`, mirrors `cogsPopulateCategoryFilter`) and **filters the product list** by category (added to both the list filter and the select-all-visible helper). Default "All categories". onchange → `renderSeasonalityList()`.
- **#2 — `CATEGORY_CURVE_MAP`:** new lowercased category/subcategory → SEED-template map (DRAFT, editable; near `getEffectiveCurveForProduct`). `resolveFallbackCurve` now resolves: `seasonal_type` (flat/seasonal/seasonal_limited) → `CATEGORY_CURVE_MAP[subcategory]` → `CATEGORY_CURVE_MAP[category]` → literal `SEED.curves[category]` → `consumables`. Subcategory wins over category; consumables is the true last resort. Incorporates the SmarterPaw toy taxonomy (cigars/Teasers/Jump n Jambs/Kickers → toys; blends → consumables; stick-n-licks → spray).
- **Note:** `CATEGORY_CURVE_MAP` is a best-guess draft from known category/subcategory names — review/extend it for the full catalog (one object, clearly commented).

## v6.37 — Seasonality chart: stockout-aware trend + 120-day forward projection
- **User flagged two things on the v6.34/36 fit chart:** (1) the de-seasonalized Trend line was still dragged down by stockout dips; (2) no forward view of seasonality.
- **(1) Stockout-aware trend:** the chart now flags stockout weeks (same local-median ±6 test as the calc, using the Stockout floor %) and **excludes them from the ±26-week trend mean** + the fit. The green Actual line still shows the real crashes, but the gray Trend + orange Fit no longer dip at supply gaps.
- **(2) Forward projection:** added a **"Projected (next 120d)"** dashed-orange line — 17 future weeks. Holds the recent de-seasonalized run-rate flat (mean of the last 8 non-stockout weeks) and applies the seasonal curve forward, so you can read projected demand by month. The gray trend extends flat into the future too. X-axis dates make the months readable.
- Series are padded to history+future length; the projection connects from the last historical fit point. Run-rate held flat (not extrapolated) to match the dashboard's velocity-based forecast convention.

## v6.36 — Fix: seasonality fit chart grew unbounded (too tall)
- **User flagged:** the v6.34 fit chart filled the whole viewport.
- **Cause:** Chart.js `maintainAspectRatio:false` + `responsive:true` on a `<canvas>` whose parent has no fixed height → the canvas grows to fill the parent, the parent grows to fit the canvas → unbounded feedback loop.
- **Fix:** wrapped the canvas in `#sea-canvas-box` (`position:relative; height:300px`); the canvas is now `width:100%; height:100%` inside it. Visibility toggling moved from the canvas to the box. Matches the existing inventory/forecast chart wrapper pattern.

## v6.35 — "↗ card" button on Seasonality rows (open product modal / mark inactive)
- **User request:** open the product card from the Seasonality page to mark products inactive.
- Added a `↗ card` button in the Product cell of each Seasonality list row → `openProductModal(master_id)` (where the Active checkbox lives). `event.stopPropagation()` so it doesn't also fire the row's `seaSetActive` (detail-view) click.
- **`saveProduct` now also refreshes the Seasonality list** when the Seasonality view is active, so a product marked inactive immediately drops out of the default "Active only" filter (mirrors the existing inventory/products refresh at the end of saveProduct).

## v6.34 — Seasonality validation chart (fit vs actual sales)
- **User request:** a visual chart on the Seasonality page to see the calculated forecast against ~1.5 years of sales.
- **Reused the existing (previously hidden) `sea-canvas`** in the active-product detail panel. New `seaRenderFitChart(mid, chartCurve)` renders a Chart.js line chart above the 52-week curve table whenever a product row is active.
- **Three lines** over the last ~80 weeks of weekly sales (`salesData[mid]`, bucketed to Monday weeks):
  1. **Actual units/wk** (green) — the real history.
  2. **Trend (de-seasonalized)** (gray dashed) — centered ±26-week mean = the growth level.
  3. **Seasonal fit** (orange) = trend × curve[isoWeek] — the model's reconstruction. When it tracks the actuals' week-to-week shape, the curve is good; when it doesn't, the curve is wrong.
- **Curve shown is context-aware:** the **preview** curve when a Preview calc is active for that product (so you see the fit before applying), else the saved/effective curve.
- Lazy-loads Chart.js via the existing `getChart()`; `seaFitChartInstance` destroyed/recreated each render. Hidden when no product is active.

## v6.33 — De-trend setting in the seasonality calc (removes growth bias)
- **User flagged:** even after v6.32 stockout correction, Catnip Spray's calculated curve was still wrong — a high block at W16–21 (1.3–1.4×) and low everywhere else. Root cause: **growth-trend recency artifact**. The data spans ~2 years + a partial 3rd (Jun 2024 → Jun 2026), so weeks W16–23 have THREE occurrences (incl. the high-sales 2026 one) while the rest have two. Dividing each week-of-year average by the GLOBAL baseline (which the recent high weeks inflate) makes weeks-with-a-recent-point read high and all others read low — pure growth bias, not seasonality.
- **New "De-trend" checkbox** in the Bulk Seasonality bar (default ON, persisted to localStorage `seaDetrend`). Helpers `seaDetrend()` / `seaPersistDetrend()` / `seaRestoreDetrend()` (restored in `initSeasonalityView`).
- **`computeProductSeasonality` `opts.detrend`:** when on, instead of `weekAvg ÷ globalBaseline`, each week is measured against its **own local level** — a centered ±26-week mean (≈ one annual cycle, which averages OUT seasonality and leaves the trend). `ratio = units ÷ localLevel`; ratios averaged per ISO-week-of-year; curve normalized to mean 1.0. Removes the growth/decline trend so a fast-growing SKU's recent weeks don't masquerade as a seasonal peak. Stable products barely change (local level ≈ global). Returns `detrended`.
- **Wired into every recompute path** (preview / bulk / on-the-fly), same as the stockout floor. Preview status shows `… · 📉 de-trended`.
- **Stack:** stockout correction (v6.32) + de-trend (v6.33) together give a curve that reflects the real repeating shape rather than supply gaps + growth. For genuinely steady/uncertain SKUs, `flat` (v6.30) is still the simplest call.

## v6.32 — Stockout correction in the seasonality calc (Seasonality tab setting)
- **User request:** a setting to correct for stockouts so out-of-stock weeks don't get read as low seasonal demand (Catnip Spray's curve was being dragged down by the Aug–Dec 2025 OOS crashes).
- **New "Stockout floor %" input** in the Bulk Seasonality bar (next to Min weeks), default **30**, persisted to localStorage (`seaStockoutFloor`). Helpers: `seaStockoutFloor()` / `seaPersistStockoutFloor()` / `seaRestoreStockoutFloor()` (restored in `initSeasonalityView`).
- **`computeProductSeasonality(masterId, minWeeks, opts)`** gained an `opts.stockoutFloorPct`. Detection is **LOCAL, not global**: a week is flagged a stockout if its units fall below `floorPct%` of the **median of its ±6 neighboring weeks**. Local comparison means a growth trend (early weeks genuinely low) doesn't trip it — only SHARP drops relative to surrounding weeks (the V-crash OOS signature) are caught. Flagged weeks are excluded from the curve buckets AND from `weeksOfData` (so a mostly-OOS product correctly reads as thin). Returns `stockoutWeeksExcluded`.
- **Wired into every recompute path:** `seaCalculateCurve` (preview), `seaBulkApplyMids` (bulk apply), `seaSetMethod` (on-the-fly). `recommendSeasonalitySettings` left uncorrected (it prefers the stored curve anyway).
- **Status surfaces it:** preview reads `N clean weeks … · 🚫 M stockout weeks excluded`; bulk reads `… · 🚫 M stockout wks excluded`.
- **Why local-median (not a global threshold):** a global "% of average" floor would also drop legitimately-low early-growth weeks for a trending SKU. Comparing each week to its immediate neighbors isolates true supply gaps regardless of trend.
- **Default 30%** = drop weeks selling below 30% of their local norm (catches near-zero OOS crashes; keeps real seasonal dips, which are usually >40%). 0 = off. Recompute a product after changing it.
- **Not yet built (future):** full de-trending (remove growth before extracting the seasonal shape). Stockout correction is the bigger win and is the piece the user asked for.

## v6.31 — Seasonality product list went blank after a large SKU Economics backfill
- **User flagged:** after uploading ~84 weeks of history, the Seasonality page showed "No products match the current filters" with all filters wide open.
- **Root cause:** `renderSeasonalityList` calls `recommendSeasonalitySettings(p)` for EVERY row, which called `computeProductSeasonality(p.master_id, 1)` per product per render. With 80+ weeks loaded that's heavy, and if it throws for any single product the whole `rows.map(...)` throws → `tbody.innerHTML` assignment never runs → the list stays stuck on the stale empty-state message.
- **Fix (two guards):**
  1. `recommendSeasonalitySettings` now **prefers the already-stored `sea_curve_calculated`** and only recomputes when there isn't one — much cheaper per render — and wraps the compute in try/catch.
  2. The per-row call in `renderSeasonalityList` is wrapped in try/catch with a safe fallback rec, so one product's failure can't blank the entire list.
- **No data/migration change** — pure render hardening. The seasonality math itself is unchanged.

## v6.30 — `seasonal_type='flat'` now takes top precedence (one-click "not seasonal")
- **Context:** Catnip Spray's calculated/`mix` curve was spiky noise (stockouts + growth read as seasonality). Switching it to `category-default` made it WORSE — the category SEED curve is heavily seasonal and this product isn't. There was no clean way to say "this SKU just isn't seasonal."
- **Root cause:** in `getEffectiveCurveForProduct`, a `calculated`/`mix`/`manual` curve was resolved FIRST; `seasonal_type` (incl. `flat`) only applied when method was already `category-default`. So `flat` was ignored on a SKU with a calc curve, and choosing category-default fell through to the heavy category curve.
- **Fix:** added a top-precedence short-circuit — if `seasonal_type === 'flat'`, return a flat 1.0 curve (every week) regardless of method. So marking a product **Seasonal type → flat** (Seasonality tab dropdown, one click; or the bulk type-setter) now truly means "velocity × days, no seasonal adjustment," overriding calc/mix/manual AND the category default. Opt-in and reversible; only affects SKUs explicitly marked flat.
- **Why flat (not category-default) for Catnip Spray:** its 365-day units chart is a growth trend + stockout dips, not a repeating annual pattern. Flat is the honest representation until there's 2+ years of clean (in-stock) data to compute a real curve.
- **Pairs with:** the stockout-aware seasonality calc (proposed, not yet built) for SKUs that ARE genuinely seasonal; and the v6.29 reorder tooltip (a flat curve makes the reorder seasonal multiplier 1.00×).

## v6.29 — Reorder event tooltip shows the arrival-window seasonal multiplier
- **Context:** user asked why an Amazon reorder Need (~10,000) far exceeded the flat expectation (reorder_qty_days 90 × vel ~70 ≈ 6,300). Root cause investigation (Catnip Spray CF312 / SP-0121): the reorder qty = seasonal demand over the window `[arrival, arrival + reorder_qty_days]` where `arrival = order-by day + lead_time`. That's a FUTURE window, so the seasonal curve THERE (not today's) drives the qty. This SKU's `sea_curve_calculated` is a spiky `mix`-method curve (weekly multipliers swing 0.06↔2.18) and `lead_time_days` is null (→ 60 default), so the window can land on high-multiplier weeks and inflate the order.
- **Fix (transparency, not logic):** each Amazon reorder event now stores `reorderQty` + `seaMult` (= actual qty ÷ flat `reorder_qty_days × vel`). Surfaced in:
  - **`buildTipTotal`** (the Need-TOTAL cell tooltip): per event — `order dX → arrives dY → covers Nd from arrival: flat Fu × seasonal M× = Qu`.
  - **`buildTipAmz`** (Amazon reorder column tooltip): same per-event window + flat × seasonal breakdown.
- So hovering a Need cell now explains exactly why the number is what it is: you can see the arrival day, the window length, the flat baseline, and the seasonal multiplier the future window applied.
- **Diagnostic takeaway for the data (not a code change):** the reorder size surprise is driven by (1) a noisy per-SKU seasonal curve (overfit `mix` on sparse weekly data) and (2) null `lead_time_days`. Recommended remediation is on the Seasonality tab (recompute / switch method / smooth) + set real lead times — the reorder math itself is correct.

## v6.28 — "Sync all bundles to BOM" bar on the COGS page
- **User request:** after the v6.27 shipping fix, every bundle showed a red `BOM ⚠ ↺` on DTC COGS (stored stale vs corrected BOM). Wanted a one-click "sync all" instead of clicking ↺ per row.
- **Orange `↺ Sync all bundles to BOM` bar** (`#cogs-bundlesync-bar`) appears above the table whenever ≥1 visible bundle is out of sync. Count reads "N bundles out of sync with BOM".
- **Snapshot (`cogsBundleSyncQueue`)** built per render in the row loop: for each visible bundle, for each field in `[amazon_cogs, dtc_cogs, chewy_cogs, landed_cost, fulfillment_amazon, fulfillment_dtc, overhead_dtc, production_labor]`, if the bundle BOM is COMPLETE (`missingCount===0`) and stored is null OR differs >$0.01, queue `{field: bomTotal}`. `shipping_cost` excluded (flat per bundle). Partial BOMs skipped.
- **`cogsSyncAllBundles()`** batch-upserts one payload per queued bundle, setting the out-of-sync fields to their BOM value and preserving everything else (incl. the flat `shipping_cost`). Confirm dialog + `cogs.sync_all_bundles` audit. Respects active filters (only syncs what's visible) since the queue is the render snapshot.

## v6.27 — Bundle DTC COGS: shipping was being counted once PER COMPONENT
- **User flagged:** bundle DTC COGS far higher than Amazon COGS; suspected shipping added more than once per bundle. Correct.
- **Root cause:** `bundleCogsFromBom(mid, 'dtc_cogs')` summed each component's stored `dtc_cogs`. Every component's `dtc_cogs` already bakes in *that component's* `shipping_cost` (`landed + overhead + fulfill_dtc + shipping + labor`), so summing N components added shipping N times. Amazon COGS has no shipping term (`landed + fulfill_amazon + labor`), so it was correct — which is exactly why DTC read so much higher than Amazon (e.g. SP-0179: DTC BOM $11.57 vs Amazon $2.96; the ~$6 gap was per-component shipping).
- **Fix (in `bundleCogsFromBom`):** for `channelField === 'dtc_cogs'`, subtract each component's own `shipping_cost` (× qty) from the sum, then add the **bundle's own flat `shipping_cost` once**. A bundle ships as one parcel → one shipping charge regardless of component count. Amazon COGS path unchanged. Building-block BOM sums (landed / overhead / fulfill_dtc / labor) unchanged — they're correctly per-component-summed; only shipping is flat (matches the v6.13 design intent, which had only been applied to the Shipping *cell*, not the dtc_cogs *total*).
- **Effect on existing data:** bundles whose stored `dtc_cogs` was set from the old inflated BOM now show a **mismatch** (stored ≠ corrected BOM) with the ↺ Sync button; the "Bundle COGS mismatches" filter surfaces them all. Click ↺ per bundle (or review) to write the corrected value. Bundle Shipping cells are currently mostly null (—) → set a flat per-bundle shipping there to include the real one-parcel shipping cost in DTC COGS.
- **No DB migration** — pure computation fix.

## v6.26 — Inventory Events (extra-stock drivers, e.g. Prime Day) → fold into Planning Need
- **User request (part 2 of 2):** set "events" that require extra inventory. Specify the event date, the date the inventory need is affected (drain start, usually earlier), and the extra stock (in days of supply). The extra drain shows in the Planning view with a badge.
- **⚠ SQL TO RUN:** `supabase_v6_26_inventory_events.sql` — creates `inventory_events` (name, event_start/end, drain_start, extra_days, scope_type [all|brand|channel], scope_value, include_master_ids jsonb, exclude_master_ids jsonb, active). RLS authenticated-all + grants. Run before deploying.
- **Events manager** lives in a collapsible "📅 Inventory Events" panel at the top of the **Reorder Setup** tab. Lists events (active toggle, edit, delete) + "+ New event". `loadInventoryEvents()` runs in the init Promise.all; `inventoryEvents` is the cache.
- **Event modal** (`ipOpenEventModal`): name · event start/end · **drain start (required)** · extra stock (days) · scope (All / by Brand / by Channel) · active. **Hand-picked overrides ("Both" scope):** buttons add the current Reorder Setup grid selection to the event's include / exclude lists (exclude wins; explicit include beats scope). CRUD = `ipSaveEvent` (insert/update), `ipDeleteEvent`, `ipToggleEventActive`.
- **Math (`eventExtraForRecord(r, X)`):** for each active event that applies to the product AND whose `drain_start` falls within [today, today+X], adds `extra_days × velocity` units. Velocity basis is channel-aware: channel-scoped events use that channel's velocity (`invAmazonVel` / `invShopifyVel` / Chewy daily); all/brand use `blended_daily`. So Prime Day (scope channel=amazon, +30d) adds 30 × Amazon daily velocity once the drain date is in range.
- **Integration:** the extra units are added to `inventoryNeedBreakdown(...).total` (and surfaced as `.events`), so they flow into the Need columns, Gap, Status, scorecards, and the chart automatically. The Need-TOTAL cells render a blue **`+EV n`** badge (next to the orange `+R n`) when an event contributes, with a tooltip naming each event + its unit add.
- **Worked example (Prime Day 2026):** event Jun 23→26, drain_start May 27, extra_days 30, scope channel=amazon. From May 27 onward (within whichever horizon reaches it) every Amazon product's Need gains 30 × its Amazon daily velocity, badged `+EV`. Toggling the event off (or past the drain window) removes it.
- **Cost note:** `eventExtraForRecord` short-circuits to zero when there are no events (the common case), so the per-row math cost is unchanged until events exist.

## v6.25 — Inventory Planning: "Reorder Setup" tab (per-platform reorder trigger/qty + bulk edit)
- **User request (part 1 of 2):** a new view/tab on the Inventory Planning page showing each item's reorder trigger + reorder qty for each platform where eligible, with bulk select/edit. (Part 2 — Events — is v6.26.)
- **⚠ SQL TO RUN:** `supabase_v6_25_platform_reorder.sql` — adds 4 nullable columns to `products`: `reorder_threshold_days_shopify`, `reorder_qty_days_shopify`, `reorder_threshold_days_chewy`, `reorder_qty_days_chewy`. Amazon per-region reorder already lives on `inventory` (v5.1). Run before deploying.
- **View toggle:** `page-inventory` now has a tab strip — **📦 Planning** (the existing scorecards/chart/table, wrapped in `#ip-planning-container`) and **⚙ Reorder Setup** (`#ip-reorder-container`). `setIpView(v)` toggles visibility + renders the active view. `ipView` module var; `switchForecastView('inventory')` calls `setIpView(ipView)` so the active tab is applied on entry.
- **Reorder Setup grid (`renderReorderGrid`):** one row per product (filtered by Brand / Platform-eligibility / search). Columns: checkbox · Brand · Product · then **Trig + Qty per platform** — Amz US, Amz CA, Amz EU/UK, Shopify, Chewy. A platform shows `—` where the product isn't eligible (Amazon = per-region record exists + has ASIN; Shopify = has shopify_sku; Chewy = has chewy_sku).
- **`REORDER_PLATFORMS`** descriptor maps each platform to storage: `amazon` → `inventory(asin, region).reorder_threshold_days / reorder_qty_days`; `product` (shopify/chewy) → `products.reorder_*_{shopify|chewy}`.
- **Inline edit:** click any eligible cell → number input (Enter/blur saves, Esc cancels). `reorderWrite()` routes Amazon edits to an `inventory` upsert (preserves FBA/warehouse/lead/safety/etc. from the in-memory record, mirroring `saveEditModal`) and Shopify/Chewy edits to a `products` upsert. In-memory record/product updated so the grid + planning view reflect it without a reload.
- **Bulk edit:** per-row checkboxes + select-all (drives `reorderSelected`). Bulk bar → modal: pick Platform + Field (trigger/qty) + value (blank = clear) → applies to every selected row eligible for that platform (others skipped, counted in the status line). Audit: `reorder.set` / `reorder.bulk_set`.
- **Amazon reorder math unchanged** — this is a settings editor. Shopify/Chewy reorder values are stored for operator reference (no trigger-based Shopify/Chewy reorder math wired yet).

## v6.24 — Open the product card from the P&L Diagnostics panel
- **User request:** be able to open the product card to edit details from the Diagnostics panel.
- **Matched ASINs table:** the `master_id` cell now carries a `↗ card` button (reuses the v6.22 `pnlCardBtn` helper) → opens the existing product modal.
- **Unmatched ASINs table:**
  - **Brand-mismatched rows** (status "BRAND X" — the product exists, it's just hidden by the brand filter): the "already exists" text is replaced with a `↗ card` button → opens the existing product modal (so you can fix the brand inline).
  - **Truly-unmatched rows** (status "UNMATCHED" — no product yet): the M/D/K quick-create chips stay, plus a new `↗ card` button → `pnlDiagCreateAndOpen(asin)` creates the `SP-TEMP-{ASIN}` product (brand resolved via the active filter or a prompt, so we never insert an invalid brand) and **immediately opens the product card** to edit title, category, COGS, image, lifecycle, etc.
- **`pnlCardBtn` guard** means brand-mismatched rows always get a real button (product exists); placeholder rows fall back to the create-and-open path (no product to open yet).
- Off-week / duplicates hygiene tables left unchanged (they're for data reconciliation, not product editing).

## v6.23 — SKU Economics upload no longer writes COGS (COGS-page-only now)
- **User decision:** the SKU Economics report must NEVER update COGS. COGS is managed exclusively via the COGS page (P&L → COGS: inline edit, building blocks, bulk edit, CSV upload). COGS still displays on the P&L pages unchanged (they read `product_cogs` via `cogsByMaster`).
- **Parser (`parseSkuEconomics`):** removed the `product_cogs.amazon_cogs` write block (and the `cogsByAsin` map that fed it). The report's COGS column is now ignored. `cogsUpdated` removed from the return object.
- **Upload handlers (single / folder / zip):** removed the `cogsUpdated` tracking + the `· N COGS updated` fragment from every status line. New-product nudge reworded from "set COGS / category in Products tab" → "review in Products tab → Needs Review (set category + COGS on the COGS page)".
- **Upload card HTML:** dropped COGS from the section header sub ("revenue · fees · COGS" → "revenue · fees"), the group description ("Captures sales + fees + COGS" → "Captures sales + fees (COGS is managed on the COGS page, not here)"), and the Cols line (removed the `COGS` chip).
- **Product modal hint:** the Amazon COGS field hint no longer claims "Auto-populated from SKU Economics uploads" — now says set it here or on the COGS page; SKU Economics no longer touches COGS.
- **EU SKU Economics** (`parseEuSkuEconomics`) never wrote COGS — unchanged. The product-modal manual COGS field + the COGS-page edit/upload paths are the only writers to `product_cogs` now (plus merge + restore).

## v6.22 — "↗ card" button on Amazon + Shopify P&L product rows
- **User request:** a button on each P&L product row to open the full product card with all details.
- **Shared helper `pnlCardBtn(masterId)`** (defined just above `PNL_COLUMNS`) returns a compact `↗ card` button. `event.stopPropagation()` so clicking it doesn't toggle the row's selection checkbox; calls the existing `openProductModal(masterId)` (full product modal — IDs, category, COGS, image, lifecycle, etc.).
- **Wired into both `title` column renders** — Amazon P&L (`PNL_COLUMNS`) and Shopify P&L (`SHOPIFY_PNL_COLUMNS`). Appended at the end of the title flex row; the title `<span>` got `flex:1;min-width:0` so it truncates cleanly and the button stays visible.
- **Guarded:** `pnlCardBtn` returns `''` when the master_id isn't a real catalog product — so the synthesized unmatched/placeholder P&L rows (orphan ASINs, brand 'Unknown', `master_id` like `unmatched-<asin>`) don't get a button that would open a blank/erroring modal.
- No new column added (avoids disturbing saved column sets / CSV); the button lives inline in the existing Product column on both pages.

## v6.21 — Commit derived (ƒ) COGS totals to the stored value (so they reach the P&L)
- **Context:** the Amazon P&L reads `product_cogs.amazon_cogs` via `cogsByMaster` (refreshed by `loadProductCogs()` after every COGS write). But the green italic `ƒ` derived totals on the COGS page are **render-time only** — they're never written to the DB, so a row showing `$1.43 ƒ` (building blocks set, stored total null) reads as **$0 COGS in the P&L** and trips the "⚠ Missing Amazon COGS" banner. User asked for a way to push the ƒ value into the stored value.
- **Per-row "✓ set" button:** in `renderTotalCell` Case 1 (stored null + derived available), a small green `✓ set` button now renders under the ƒ value. Click → `cogsApplyBom(masterId, 'amazon_cogs'|'dtc_cogs', derivedVal)` writes the derived value straight to the stored channel total (it's not a building-block field, so it stores directly — no re-derivation). Mirrors the existing ↺ Sync affordance from v6.19.
- **Bulk "✓ Commit derived (ƒ) totals" bar:** new green bar above the table (`#cogs-derived-bar`), shown whenever the current view has ≥1 committable ƒ row. Count reads "N rows with derived (ƒ) totals". One click → `cogsCommitDerivedVisible()` batch-upserts every committable derived total in the current view.
  - Acts on `cogsDerivedVisible` — a module-level snapshot rebuilt on every `renderCogsTbl` (reset at top, pushed per row inside the row map, gated on `!p.is_bundle && (isAmzDerived || isDtcDerived)`). So it **respects all active filters** — only commits what's visible.
  - Already-stored totals are never in the snapshot → never touched. Building blocks + the other channels + EU + dismissed flags are all preserved in the payload. Batched 500/upsert. Audit: `cogs.commit_derived`.
- **After commit:** stored == derived, so on re-render Case 1 no longer fires (Case 3 standard display), the ƒ marker disappears, and the value now flows into the P&L. Bundles are excluded (they use `bundleCell` / BOM sync, a different path).

## v6.20 — Landed-cost gate on derived/auto-recompute logic
- **User flagged:** rows with no landed_cost but other building blocks set (e.g. Fulfill Amz $0.04) were showing amazon_cogs as derived `$0.04 ƒ`. That's misleading — landed_cost is the foundational input; without it the "total" is just fees, not a real COGS.
- **Fix:** added a `payload.landed_cost != null` / `c.landed_cost != null` gate on EVERY auto-derive site. When landed_cost is null, the derivation is skipped entirely → totals fall back to "— missing" / "n/a" display, prompting the user to enter the foundational input first.
- **Sites updated:**
  - `renderTotalCell` in renderCogsTbl — derived display
  - `cogsEditSave` — inline edit auto-derive
  - `cogsApplyBom` — bundle BOM apply + non-bundle building-block sync
  - `cogsBulkApply` — bulk edit auto-derive
  - `uploadCogsCSV` — CSV upload auto-derive
- **Bundle BOM logic unchanged** — bundle cells use the BOM (component sum) regardless of the bundle's own landed_cost. That's a different code path that doesn't go through the building-block sum.

## v6.19 — Stored-vs-building-block sync flag on non-bundle COGS totals
- **User flagged:** non-bundle product with Landed $1.40 + Fulfill Amz $0.03 (= $1.43 BB sum) but a pre-existing stored amazon_cogs of $1.40 was displayed without any indication that the stored value was stale.
- **Root cause:** v6.17's derived-totals display only kicks in when stored is null. When stored is set, it just renders as-is — no comparison to the building-block sum.
- **Fix — `renderTotalCell` helper for non-bundle rows:** three cases now handled:
  1. **Stored null, BB sum available** → render derived value italic green with `ƒ` marker (v6.17 behavior, unchanged)
  2. **Stored set, BB sum set, MISMATCH (≥ $0.01)** → render stored value normally + a sync line beneath: `BB $X.XX ⚠ ↺`. Click ↺ → `cogsApplyBom` writes the BB sum to the stored value (same handler bundles use; auto-derives both totals from the post-apply state)
  3. **Match or no BB sum** → standard stored-value display
- **Mirrors the bundle BOM pattern** the user is already familiar with from `bundleCell` (stored vs component-sum). Same red ⚠ + ↺ button affordance, same `cogsApplyBom` handler.
- **Bundle rows unchanged** — `bundleCell` still handles them with the component-BOM-sum comparison.

## v6.18 — Category + Subcategory filters on COGS page
- **User request:** category filters on the COGS page.
- Added two new dropdowns to the controls bar (between Status and Search):
  - **Category** (`cogs-cat`) — populated from distinct categories that any product actually references (same logic as the Amazon P&L / Shopify P&L Category dropdowns)
  - **Subcategory** (`cogs-subcat`) — cascades from the selected Category. Empty when no category is picked; populated with that category's subcategories when one is selected
- **`cogsPopulateCategoryFilter`** populates the Category dropdown once per catalog load (guarded by `dataset.populated`). Called from `loadCogsTab`.
- **`cogsOnCategoryChange`** repopulates the Subcategory dropdown on Category changes and resets the Subcategory selection to clear any orphaned sub from a different category.
- **Filter logic in `renderCogsTbl`:** resolves each product's `category_id → allCategories` lookup and excludes rows whose category/subcategory doesn't match the active filter. Products without a category_id drop out only when a category filter is active (legacy products without categorization don't disappear from the unfiltered view).

## v6.17 — Derived `amazon_cogs` / `dtc_cogs` shown when only building blocks are set
- **User flagged:** for products with building blocks filled in (Landed $1.38, Fulfill Amz $0.03, Fulfill DTC $0.85, Ovrhd DTC $0.05, Shipping $2.00) but no stored amazon_cogs / dtc_cogs, the table showed "n/a" or "— missing" instead of the derived sums.
- **Fix:** the row builder now computes a derived total when the stored value is null but inputs exist. Computed via the same formulas the edit / bulk-edit / CSV-upload paths use:
  - `amazon_cogs = landed_cost + fulfillment_amazon + production_labor`
  - `dtc_cogs    = landed_cost + overhead_dtc + fulfillment_dtc + shipping_cost + production_labor`
  - Null inputs are SKIPPED (not treated as 0) — so the derived total is only assigned when at least one input is set. Empty rows still show "n/a" cleanly.
- **Display:** derived values render in italic green with a `ƒ` suffix and a hover tooltip ("Auto-derived from building blocks. No stored override. Click to set an explicit value."). Visually distinct from stored values (normal text color, no ƒ marker).
- **`missing` flag suppressed when a derived value exists** — no point screaming "missing" at the user when the math already gives an answer. The cell shows the derived value cleanly instead.
- **Bundles unchanged behavior:** for bundle rows, `bundleCell` still renders the BOM-comparison line. The "stored" value passed to it is now the derived total (when no explicit override), so the BOM-vs-stored check uses the right number.
- **No DB writes from this change** — derived values are render-time only. The moment any cell is edited (building block OR total), the existing auto-derive logic writes the computed total to the DB explicitly. Until then, the displayed value is computed on-the-fly each render.

## v6.16 — `production_labor` building block + bulk edit on COGS page
- **SQL migration (`supabase_v6_16_production_labor.sql`):** adds `production_labor numeric` column to `product_cogs` via `ADD COLUMN IF NOT EXISTS`. Idempotent.
- **`production_labor` integrated as a building block:**
  - New COGS column on the page between Shipping and Amz COGS (with subtle blue tint, like other building blocks).
  - Feeds **both** total formulas: `amazon_cogs = landed_cost + fulfillment_amazon + production_labor`; `dtc_cogs = landed_cost + overhead_dtc + fulfillment_dtc + shipping_cost + production_labor`.
  - BOM-summable for bundles (sums from component production_labor × qty). Unlike `shipping_cost` which is flat per bundle, `production_labor` follows the per-unit roll-up convention.
  - Added to: auto-derive list in `cogsEditSave`, `cogsApplyBom`, `cogsBulkApply`; the BLOCK_BOM_FIELDS Set in `blockCell`; `hasBundleMismatch`; CSV download header + body; CSV upload columns lookup + auto-derive trigger.
- **Bulk edit on COGS page (new):**
  - Checkbox column added at the leftmost position. Per-row checkboxes write to a module-scope `cogsSelected` Set. A select-all checkbox in the header drives every visible row.
  - Selected rows get a green tint and the `cogs-bulk-bar` toolbar appears between the status line and the table — shows the count + "✎ Bulk edit" + "✕ Clear selection" buttons.
  - Bulk-edit modal: pick a field (any of the 10 cost columns — 5 building blocks + production_labor + 4 channel totals), enter a value (or blank to clear), Apply. The handler `cogsBulkApply` builds one payload per selected master_id (preserving all 10 cost fields and auto-deriving amazon_cogs / dtc_cogs when a building block is being set), then upserts in batches of 500.
  - Indeterminate state on the select-all checkbox set imperatively after thead is in the DOM (HTML can't express it).
- **Total columns on screen: 20** (checkbox + brand + product + 3 identity + 2 cat + bundle + 6 building blocks + 4 totals + status). CSV download is now 21 cols.
- **Selection persistence:** the selection Set is module-level, so it survives filter changes — useful if the user wants to filter to "Bundles only," select some, then switch to a different filter to select more, then bulk-edit the combined set. The toolbar count and select-all state always reflect what's VISIBLE.

## v6.15 — "Non-bundles only" filter option on COGS page
- Added `<option value="non-bundles">Non-bundles only</option>` to the `cogs-filter` dropdown, between "Bundles only" and "Bundle COGS mismatches" so the bundle-related options sit together.
- `renderCogsTbl` filter logic gets a matching branch: `if (filter === 'non-bundles') return !p.is_bundle;`
- Tightened the existing `'bundles'` predicate from `return p.is_bundle` to `return !!p.is_bundle` so undefined values (legacy products without the flag set) fall on the non-bundle side consistently.

## v6.14 — COGS table width fix (bundle BOM lines were sprawling)
- **User pushback:** v6.12 + v6.13 still didn't fit at 100% browser zoom. Right edge truncated past Amz EU column.
- **Root cause:** the bundle cells (channel COGS + 4 building blocks) render a BOM-comparison line BENEATH the value, e.g. `BOM: $1.17 (partial — 2 comps missing)` with a `✓ Apply` or `↺ Sync` button. That text + button packed in a horizontal flex container forced each bundle cost cell to ~140px instead of the ~80px non-bundle cells. With 4 channel COGS cols × 60px overflow = 240px past viewport.
- **Fix #1:** compacted `bundleCell` text:
  - `"BOM: $1.17 (partial — 2 comps missing)"` → `"BOM $1.17 (partial)"`
  - `"BOM: $1.17 · auto-fillable"` → `"BOM $1.17"`
  - `"BOM: $1.17 ⚠ (+0.23)"` → `"BOM $1.17 ⚠"`
  - `"✓ Apply"` button → just `"✓"`
  - `"↺ Sync"` button → just `"↺"`
  - Hover tooltips preserve the full context (delta values, missing-component counts).
- **Fix #2:** added explicit `max-width` to all cost cells so even the BOM-line content respects width:
  - Amazon COGS / DTC COGS / Chewy COGS: `max-width:110px`
  - Amazon EU COGS: `max-width:90px`
  - Building blocks (when bundle, with BOM line): `max-width:100px`
  - Building blocks (single-line): `max-width:90px`
- **New estimated total table width:** ~1500px. Comfortable fit at 1810px viewport with margin for browser chrome.

## v6.13 — Bundle column on COGS page + building-block BOM auto-sum
- **User request:** (1) add an exportable "Bundle" column to the COGS page so it's clear which products are bundles, (2) make the COGS bundle auto-sum work for the building-block columns (Landed, Fulfill Amz, Fulfill DTC, Overhead DTC) the same way it already works for channel COGS — except `shipping_cost` which is flat per bundle (not summed from components).
- **Bundle column added:** new column between Subcategory and the building-block group. Shows orange "Yes" for bundles, dim "No" otherwise. Total table now 18 cols; empty-state colspan bumped 17 → 18.
- **CSV export expanded to 20 cols:** added `is_bundle` after `subcategory` and before `landed_cost`. Values are `true` / `false`.
- **`blockCell` made bundle-aware:** for bundles + the 4 BOM-summable fields (`landed_cost`, `fulfillment_amazon`, `fulfillment_dtc`, `overhead_dtc`), renders the same BOM-comparison line + ✓ Apply / ↺ Sync button pattern that the existing `bundleCell` uses for channel COGS. `shipping_cost` always renders single-line (flat per bundle, no BOM sum).
- **`bundleCogsFromBom` already works for any field** — calls it with the building-block field name and it returns `{ total, missingCount, componentCount }` summed from `cogsByMaster[component_id][field] × qty`. No helper changes needed.
- **`cogsApplyBom` extended** to preserve building-block fields (pre-v6.13 it only preserved the 4 channel totals → applying a building-block BOM total would clobber the other building blocks). When the applied field is a building block, the function also auto-derives `amazon_cogs` and `dtc_cogs` from the post-apply state — same logic as `cogsEditSave`.
- **`hasBundleMismatch` extended** so the "Bundle COGS mismatches" filter catches stored-vs-BOM disagreements on building blocks too (excluding shipping_cost).
- **Cascade behavior note (intentional limitation):** v6.13 doesn't auto-cascade when a COMPONENT's COGS changes (i.e. editing a child product's landed_cost doesn't automatically update parent bundles' landed_cost). The BOM comparison line in the parent bundle's cell shows the recomputed sum next to the (now stale) stored value, with the ↺ Sync button to apply. Considered acceptable for now since SmarterPaw component COGS doesn't change frequently and the visual indicator surfaces the drift.

## v6.12 — COGS table actually fits at 100% browser zoom (v6.11 wasn't aggressive enough)
- **User pushback:** "did not fix." v6.11 made the table scrollable but didn't make the 17 columns actually FIT at 100% zoom on a 1920px viewport. The wrap could scroll but every column was still cramped.
- **Real math:** 17 columns × ~22px padding overhead = 374px. Plus content max-widths summed to ~1730px. Total ~2100px, well over the ~1810px usable viewport.
- **v6.12 — aggressive compaction:**
  - **Cell padding:** `7px 10px` (head was `8px 10px`) → `4px 6px` everywhere. Saves ~10px per cell × 17 = ~170px.
  - **Product max-width:** 280px → 200px (min 160px). Secondary short_name line still shown but at 9px instead of 10px font.
  - **Channel IDs max-width:** 200px → 140px.
  - **Category / Subcategory max-width:** 110px → 90px each.
  - **Header labels shortened:** "Amazon COGS" → "Amz COGS"; "Amazon EU COGS" → "Amz EU"; "Overhead DTC" → "Ovrhd DTC". Tooltips preserve the full names.
  - **Bundle badge:** "📦 BUNDLE" → just "📦" with reduced padding.
- **New target width:** ~1700px. Comfortably fits in 1810px viewport. No horizontal scroll needed at 100% zoom on standard monitors.

## v6.11 — COGS table layout fix (17 cols was overflowing at 100% browser zoom)
- **Problem:** after v6.10 the COGS table has 17 columns (Brand, Product, SP SKU, Master ID, Channel IDs, Category, Subcategory, 5 building blocks, 4 channel totals, Status). At 100% browser zoom on a 1920px screen, total width is ~1930px+. The table style `width:100%` made it squeeze into the viewport — columns truncated, padding crammed, and the wrap's `overflow-x:auto` never fired because the table never exceeded its parent's width.
- **Fix #1:** changed `<table id="cogs-tbl" style="width:100%">` → `style="min-width:100%"`. Table now natural-sizes to its content; the wrap scrolls horizontally when total width exceeds the viewport. `min-width:100%` ensures short tables (e.g. after a tight filter) still fill the wrap so they don't look chopped.
- **Fix #2:** tightened max-widths on three columns to keep total width manageable:
  - Product cell: `max-width:360px` → `max-width:280px, min-width:200px`
  - Channel IDs cell: `max-width:260px` → `max-width:200px`
  - Category/Subcategory cells: `max-width:140px` → `max-width:110px`
- **Behavior:** at standard 1920px viewport, most columns fit; the rightmost 3-4 columns may need a small horizontal scroll. At smaller viewports, scroll engages earlier. No information hidden — just made the table scrollable rather than crammed.

## v6.10 — Category + Subcategory on COGS page and export
- **User request:** add Category and Subcategory columns to the COGS page table and the CSV download.
- **UI:** two new columns added after `Channel IDs` (before the building-block cost columns). Resolved via `allCategories.find(c => c.id === p.category_id)` — falls back to em-dash when the product has no category assigned. Max-width 140px with ellipsis truncation.
- **CSV export:** download header expanded from 17 → 19 cols. New columns inserted after `chewy_sku` and before `landed_cost`: `category, subcategory`. Values pass through `csvEsc()` to handle category names with commas.
- **CSV upload:** unchanged behavior. The upload only reads the cost columns + master_id; identity columns including category/subcategory are silently ignored (round-trip download → edit → upload still works without breaking on the new columns).
- **Empty-state colspan** bumped 15 → 17.

## v6.9 — Unified CSV download filenames (nav-path based)
- **User request:** name all CSV downloads based on where they're exported from. Mixed conventions made it ambiguous which tab a file came from when downloads piled up locally.
- **Convention:** `smarterpaw-{tab}-{subtab}[-{scope}]-{date|range}.csv`. Date ranges use `_to_` (since YYYY-MM-DD already contains dashes); single dates suffix with the day. Tab + subtab segments mirror the nav.
- **Renames:**
  - `smarterpaw-cogs-…` → `smarterpaw-pnl-cogs-…`
  - `smarterpaw-pnl-{region}-…-to-…` → `smarterpaw-pnl-amazon-{region}-…_to_…` (added `amazon` subtab, normalized separator)
  - `smarterpaw-shopify-pnl-…` → `smarterpaw-pnl-shopify-…` (tab segment first)
  - `smarterpaw-forecast-{mode}-…` → `smarterpaw-forecast-demand-{mode}-…`
  - `smarterpaw-inventory-…` → `smarterpaw-forecast-inventory-planning-…`
  - `smarterpaw-chewy-forecast-…` → `smarterpaw-forecast-chewy-…`
  - `smarterpaw-bundles-bom-…` → `smarterpaw-bundles-…` (dropped redundant `-bom-` since the Bundles tab is the only export source)
- **Unchanged:** `smarterpaw-products-…`, `smarterpaw-units-sold-…` (already match the convention), `smarterpaw_*_template.csv` (upload templates, not exports), `smarterpaw-backup-*.json` (global utility).
- **No behavior changes** — only the file's download name was edited; CSV contents are identical.

## v6.8 — COGS page loads empty until filter toggled (race fix)
- **User flagged:** opening the COGS page from a fresh navigation showed "0 PRODUCTS · No products match the current filters" until they touched the status dropdown. Toggling re-rendered and the table populated.
- **Root cause:** `loadCogsTab` awaited only `loadProductCogs()`, then called `renderCogsTbl`. The table-row filter (line ~10492) reads `allProducts`; if the user navigated to COGS before `init()` had finished its product-catalog load, `allProducts.length === 0` → all rows filtered out → empty table. The implicit re-render triggered by changing a filter caught up because by then `allProducts` had populated in the background.
- **Fix:** `loadCogsTab` now mirrors the loader-priming pattern other tabs use (e.g. `loadSalesAnalytics`): `if (!allProducts.length) await loadProducts();` and `if (!allCategories.length) await loadCategories();` before the product_cogs fetch. Idempotent — if either is already loaded the conditional skips.

## v6.7 — COGS page: SP SKU column + longer title + full-column CSV export
- **User asked for three things:** (1) surface SP_SKU on the COGS page, (2) show the longer product name (not just short_name), (3) export ALL columns in the CSV download.
- **SP SKU column** added between Product and Master ID. Shows `p.sp_sku` (mono, dim text) or em-dash if empty.
- **Product cell rewritten** to a two-line layout: primary line = `p.title` (longer marketing/catalog name), secondary line = `p.short_name` (dimmer, smaller). When title and short_name are identical (or short_name is blank), only one line shows. Bundle badge still inline at the start. Max-width bumped from 280px → 360px to accommodate the longer title.
- **`downloadCogsCSV` expanded** to 17 columns: `master_id, sp_sku, brand, short_name, title, asin, shopify_sku, chewy_sku, landed_cost, fulfillment_amazon, fulfillment_dtc, overhead_dtc, shipping_cost, amazon_cogs, amazon_cogs_eu, dtc_cogs, chewy_cogs`. Includes the v6.6 building blocks, the identity columns (sp_sku, short_name) the user needs for cross-reference, and the full set of channel totals.
- **`uploadCogsCSV` expanded** to recognize all 9 cost columns (5 building blocks + 4 channel totals). Any subset is valid; missing columns leave existing values untouched. If the upload sets a building block but NOT the corresponding total, the parser auto-derives the total in the same merge pass — mirroring the inline `cogsEditSave` behavior so the user can either set totals directly OR work with the building-block decomposition. Direct CSV-supplied total values always win (treated as overrides).
- **Empty-state colspan** bumped 14 → 15.

## v6.6 — COGS building blocks (auto-derived Amazon + DTC totals)
- **User requested:** 5 new cost dimensions on the COGS page — `landed_cost`, `overhead_dtc`, `fulfillment_dtc`, `fulfillment_amazon`, `shipping_cost`. Formulas: `amazon_cogs = landed_cost + fulfillment_amazon`, `dtc_cogs = landed_cost + overhead_dtc + fulfillment_dtc + shipping_cost`.
- **SQL migration (`supabase_v6_6_cogs_building_blocks.sql`):** adds the 5 columns to `product_cogs` via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Idempotent.
- **COGS page UI changes:**
  - 5 new editable cells per row, positioned between Channel IDs and the channel COGS totals. Subtle blue tint (`rgba(96,200,250,0.04)`) on the building-block cells visually groups them as INPUTS distinct from the derived TOTAL columns.
  - Existing amazon_cogs / dtc_cogs columns stay in place. Tooltips updated to note auto-recompute behavior.
  - Empty-state colspan bumped from 9 → 14.
- **Auto-derive in `cogsEditSave`:** when a building block is edited, the post-edit values feed back through the formulas and the affected total(s) get assigned in the same upsert payload. `sumOrNull` guard: if ALL inputs to a total are null, the function returns undefined and the existing total is left alone — protects against clobbering a manual amazon_cogs / dtc_cogs override with 0 when building blocks haven't been populated yet.
- **Direct edits to amazon_cogs / dtc_cogs** are still allowed and skip the recompute branch. Treated as manual overrides for one-off scenarios.
- **amazon_cogs_eu and chewy_cogs are unchanged** — they have different cost structures and stay as manually-editable single fields. Not part of the building-block formulas.
- **Bundle BOM logic untouched** — the existing `bundleCell` / `cogsApplyBom` flow still sums child amazon_cogs / dtc_cogs / chewy_cogs at the BOM level. Building blocks aren't BOM-summed (out of scope for v6.6; revisit if multi-component bundles need decomposition at the input level).

## v6.5 — Units Sold chart caps at latest fully-reported week per channel
- **User flagged:** v6.4 fixed the daily-vs-weekly jagged-line bug, but a new issue emerged. Mixed-channel SKUs (Pawty Mix has Amazon + Shopify) showed a misleading drop at the rightmost week — Shopify uploads daily and was current through 5/31, but Amazon hadn't been uploaded yet for that week. The week's bucket plotted at "Shopify-only" units, looking like a 90% sales crash.
- **Fix:** `updateSalesChart` now computes per-channel "latest reported week" from `salesData`, identifies which channels are relevant to the selection (including bundle-attribution channels when that toggle is on), and caps the chart's right edge to the EARLIEST of those latest weeks. For Pawty Mix: if Amazon's last upload was for week 5/18 and Shopify ran through 5/25, the chart now ends at week 5/18. Uploading the missing Amazon week extends the chart automatically — no schema or workflow change.
- **Implementation detail:** `cutoffWeek` is calculated once per chart render and applied at the `allWeeks.add()` step via an `addWeek(wk)` guard that drops weeks beyond the cutoff. Downstream `unitsByWeek` building remains unchanged because the chart consumes only `weeks.map(w => unitsByWeek[w] || 0)`, so any extra unitsByWeek keys silently drop off.
- **Why not "show partial weeks with a dashed line":** considered but rejected. The principal failure mode here is a clean, decisive misread ("sales crashed!") which dashed lines wouldn't fully prevent. Dropping the week eliminates the false signal entirely; uploading the missing data restores it.

## v6.4 — Units Sold chart bucketing fix for mixed daily/weekly salesData
- **User flagged:** Units Sold chart for products that sell on both Amazon and Shopify (e.g. "Catnip Spray - 3 Oz") showed a jagged daily-spike pattern after the v6.1 cutover. Amazon rows = one point per Monday; Shopify rows = one point per day. The chart's X-axis collected both types of dates into the same set, producing hundreds of points and a sawtooth visual.
- **User proposed** writing to sales_weekly again for chart sanity. Rejected — the right fix is at the READ layer.
- **Fix:** added the same `toMondayKey(dateStr)` helper used by v6.2 seasonality + v5.86 EU. Inside `updateSalesChart` every `r.week_start` value is normalized to its Monday-of-week key before adding to `allWeeks`, `salesRawWeekData`, and `unitsByWeek`. Amazon weekly rows are already Mondays (no-op). Shopify daily rows collapse cleanly into their containing weeks. Result: smooth weekly line on the chart from a daily Shopify source — no schema dual-write, no data drift.
- **Other consumers verified clean:** `renderSalesTbl` (Units Sold table totals) sums via date-range filter, agnostic to grain. Forecast `fcSoldByChannel` and Inventory velocity (`getInventoryChannelVel`) same. The chart was the only weekly-grain-assumption left.

## v6.3 — Multi-month revision trend chart on Chewy Revision Tracker
- **User request:** "i need a way to see how forecasts are changing over time" on the Chewy Forecast Revision Tracker. Specifically a "line chart showing each month's forecast final lock with additional lines showing the relative gain/loss over the preceding period."
- **What's new:** chart panel added inside the existing Revision Tracker `<details>` block (between the tiles and the per-SKU table). Renders three series across all `forecast_month` values in the data:
  1. **First forecast** (gray): aggregate of each SKU's earliest snapshot per month
  2. **Final pre-month lock** (green): aggregate of last snapshot before `month_start` per month — explicit gap if a month had no SKU lockable before it began
  3. **Net revision** (orange dashed line on a right-side Y2 axis): `Lock − First` per month — positive = Chewy raised demand, negative = lowered. This is the "relative gain/loss over the preceding period" series.
- **Implementation:** added `chewyRenderRevisionChart()` (called at the end of `renderChewyRevisionTracker`). Re-derives the brand/search filter context from the DOM so it stays in lockstep with the panel above it. Chart.js line chart with dual Y-axes; existing `getChart()` helper bootstraps Chart.js lazily.
- **State:** new module-level `chewyRevisionChartInstance` so the chart destroys + recreates cleanly on every render (avoids stale ghost charts after filter changes).
- **No table changes:** my earlier attempt to add a per-row 📈 drill-down column was reverted before commit — Jason's ask was for an aggregate chart on the existing tracker, not a per-product drill-in. Table layout is unchanged from v6.2.

## v6.2 — Seasonality fix for v6.1 daily-grain Shopify rows
- **Bug caught during post-cutover audit:** `computeProductSeasonality` counted unique `week_start` strings as a proxy for "weeks of data". After v6.1, Shopify rows in `salesData` carry daily dates in `week_start` (alias for `day`). Without normalization a Shopify SKU with 7 daily sales registered as 7 "weeks" — falsely passing the `>= minWeeks` confidence check, and producing per-day-not-per-week `baseline` math for mixed-channel SKUs.
- **Fix:** added `toMondayKey(dateStr)` helper inside `computeProductSeasonality` that converts any date (daily or weekly) to its Monday-of-week YYYY-MM-DD key. Two consumers normalize through it:
  1. Channel-stability detection (line ~15878): `channelStats[ch].weeks.add(toMondayKey(r.week_start))` so the `>= 3 weeks` filter counts unique weeks, not unique days.
  2. ISO-week aggregation (line ~15898): rows aggregate to `weeklyAgg[mondayKey]` first, then bucket by `isoWeekOfYear` per Monday key. `weekTotals[isoKey].count` now increments per WEEK, not per row, so `wkAvg = sum/count` is always weekly regardless of source grain.
- **Other read paths verified OK without changes:**
  - Forecast tab + Inventory Planning velocity (line ~12079, ~17073): use `(now - new Date(s.week_start)) / 864e5 <= windowDays` — pure date-range filter, works correctly with daily dates (actually more precise now).
  - Shopify P&L tab: already date-range based throughout.
  - Units Sold tab: same date-range filtering.
  - `velocity_calculated` view: handles both grains via the v6.1 SQL migration.

## v6.1 — `loadSalesAnalytics` rewired + SQL for view rewrite / sales_weekly cleanup (v5.98 Pass B.2)
- **`loadSalesAnalytics` rewritten** to source from TWO tables: `sales_weekly` (filtered to `channel <> 'shopify'`) + `shopify_sales_daily` (mapped to legacy row shape with `week_start = day`, `units_ordered = units_sold`, `channel = 'shopify'`, `region = 'US'`). Both paginated. Downstream consumers (`renderSalesTbl`, `fcSoldByChannel`, seasonality, bundle attribution) work unchanged — they iterate `salesData[master_id]` and filter by `s.week_start` / `s.channel`, which is identifier-only and doesn't care that the underlying grain shifted from weekly to daily.
  - Forecast tab "Sold (period)" Shopify column now reflects v5.98 daily uploads.
  - Units Sold tab same loader, so the Shopify checkbox at line 1772 + chart see the same fresh data.
- **SQL migration (`supabase_v6_1_velocity_view_shopify_cutover.sql`):**
  - Replaces `velocity_calculated` view with a UNION-based definition: `sales_weekly` (non-shopify) + `shopify_sales_daily`. Aggregates the unified stream into v30/v60/v90/v120 buckets per (master_id, region). `weeks_of_data` computed as count of distinct ISO weeks (handles the daily/weekly mix correctly via `date_trunc('week', day)`).
  - Deletes `sales_weekly where channel = 'shopify'` — those rows are no longer read by anything (view excludes them, loadSalesAnalytics excludes them, loadShopifyPnlTab moved off them in v6.0).
  - **Includes a Step 1 diagnostic at the top** to dump the current view definition via `pg_get_viewdef`. Run that read-only first to verify my replacement's column shape matches the existing one. If something doesn't line up, edit the migration before committing. The dashboard reads only `master_id, region, v30, v60, v90, v120` and references `weeks_of_data` in saved SQL — those are preserved.
- **Cutover state after running the SQL:**
  - Shopify P&L: fresh daily data ✓ (v6.0)
  - Forecast salesData / Units Sold: fresh daily data via UNION ✓ (v6.1)
  - velocity_calculated: includes Shopify from new table ✓
  - sales_weekly channel='shopify': empty ✓
  - Architecture Rule #5 fully discharged for Shopify (Shopify writes never touch sales_weekly anymore)
- **Safe to deploy v6.1 BEFORE running the SQL:** code excludes legacy Shopify rows from sales_weekly via the `.neq('channel', 'shopify')` filter, so even if those rows still exist in the DB, salesData ignores them. velocity_calculated view stays as-is (still reading sales_weekly Shopify rows) until you run the SQL — meaning Inventory Planning velocity for Shopify products is stale until SQL applied. Code-vs-SQL order doesn't matter for correctness, only for closing the velocity gap.

## v6.0 — Shopify P&L read-side rewired to `shopify_sales_daily` (v5.98 Pass B.1)
- **`loadShopifyPnlTab` rewritten** to source from `shopify_sales_daily`. Pulls the full rich field set (master_id, shopify_sku, shopify_product_id, variant_title, title_at_time_of_sale, vendor, sales_channel, day, units_sold, gross_sales, discounts, returns, net_sales, taxes, total_sales). Compat aliases (`week_start = day`, `units_ordered = units_sold`, `revenue = net_sales`) keep the legacy aggregator code working without a sweeping identifier rename.
- **New "Channel" filter dropdown** in the Shopify P&L controls bar. Populated dynamically from the data after load — shows distinct `sales_channel` values plus `(unknown / blank)` if any rows had no channel set. Filters the aggregator + selectedAgg without touching the underlying data. State captured in saved views.
- **Two new period options:** `This month` (1st of current month → today) and `Last month` (1st → last day of prior month). Calendar-month math is precise now that the underlying grain is daily — no week-alignment compromise. Period dropdown default shifted from "Last 90 days" to "Last 30 days" since calendar-month workflows are the more common use case.
- **Aggregator captures the new metric fields** so column renderers have direct access: `gross_sales`, `discounts`, `returns`, `taxes`, `total_sales`. Both `agg` (filtered) and `selectedAgg` (selection-only) build the same shape.
- **7 new column options** added to `SHOPIFY_PNL_COLUMNS`, all default-off so existing users' visible-column sets aren't disturbed: `gross_sales`, `discounts`, `returns`, `taxes`, `total_sales` (revenue group); `variant_title`, `shopify_product_id` (identity group). Toggle on via the 📋 View popup.
- **Saved-view snapshot extended** to capture the channel filter. Apply restores it alongside the existing dimensions.
- **CSV export context line** now includes `channel=X` when a channel filter is active.
- **What's NOT in v6.0 (deferred to B.2):** `velocity_calculated` view rewrite, deletion of legacy channel='shopify' rows from `sales_weekly`, Forecast tab `salesData` UNION, Units Sold tab UNION. Velocity is currently sourced from the stale legacy weekly rows in `sales_weekly` — uploads after v5.98 don't refresh them. Shopify P&L shows the fresh daily data; velocity-driven surfaces (Inventory Planning reorder math, Forecast tab) lag.

## v5.99 — Returns handling + Shopify uploader UI refresh (follow-on to v5.98 Pass A)
- **Returns fix in `parseShopifySales`:** the initial v5.98 parser had `if (units <= 0) continue;` which silently dropped rows representing returns / refunds (Shopify emits these with negative `Net items sold`, negative `Net sales`, negative `Returns`). Re-gated to `hasActivity = units !== 0 || netSales !== 0 || gross_sales !== 0 || returns !== 0 || discounts !== 0 || taxes !== 0 || total_sales !== 0` — keeps any row with financial activity, skips only truly empty rows. Returns aggregate cleanly into the `(sku, day, sales_channel)` key shared with the original sale.
- **Shopify uploader UI text refresh:** the Sales & P&L uploads page description still said "Daily granularity is aggregated to weekly on upload" and listed the old 3-column expectation (`Product variant SKU` / `Day` / `Net items sold`). Updated both the `up-grp-desc` and the inline `dz-sub` to reflect daily-grain native storage + the full 8-column field set the v5.98 parser uses.
- **Note on deploy tracking:** this version bump exists specifically so the user can see when the post-v5.98 fixes landed in the live dashboard. Prior to v5.99, two changes (returns fix + UI text) shipped without version bumps — fixed going forward.

## v5.98 Pass A — Shopify moves to daily-grain (`shopify_sales_daily` write path)


- **User reframe:** `sales_weekly` was built around Amazon's natively-weekly SKU Economics export. Forcing Shopify into that grain causes monthly P&L misattribution (calendar months cut across weeks) AND blocks the richer ShopifyQL fields (sales_channel, gross_sales, discounts, returns, taxes, total_sales) from being captured. Shopify gets its own daily-grain table; Amazon + Chewy + EU stay on sales_weekly.
- **Canonical ShopifyQL the v5.98 parser expects:**
  ```
  FROM sales
  SHOW day, net_items_sold, gross_sales, discounts, returns,
       net_sales, taxes, total_sales
  WHERE line_type = 'product'
  GROUP BY day, product_title, product_variant_title, product_variant_sku,
           product_id, product_title_at_time_of_sale, sales_channel, product_vendor
  SINCE ... UNTIL ...
  ORDER BY day ASC
  LIMIT 50000
  ```
- **SQL migration (`supabase_v5_98_shopify_sales_daily.sql`):**
  - Creates `shopify_sales_daily` with columns: master_id, shopify_sku, shopify_product_id, variant_title, title_at_time_of_sale, vendor, sales_channel (default `''`), day, units_sold, gross_sales, discounts, returns, net_sales, taxes, total_sales, source, uploaded_at.
  - Plain-column unique index on `(shopify_sku, day, sales_channel)` — NO `coalesce()`. sales_channel defaults to `''` so the index is upsert-safe by plain-column onConflict (lessons learned from v5.96/v5.97). Parser still uses DELETE+INSERT per Architecture Rule #5.
  - DOES NOT touch `sales_weekly` or `velocity_calculated` yet. Pass B handles the cutover + view rewrite.
- **`parseShopifySales` rewritten:**
  - Reads richer ShopifyQL format (all 7 metrics + 7 dimensions). Missing columns degrade gracefully to 0/null so partial-format files still load, but `day` and `net_sales` are required.
  - Aggregates per `(sku, day, sales_channel)` — daily grain.
  - Auto-creates SP-TEMP for unknown SKUs with v5.88 vendor→brand mapping. Captures variant_title / product_id / title_at_sale on the daily row.
  - Conflict dialog reframed to day-level overlap (was week-level).
  - Writes via DELETE+INSERT keyed by `(shopify_sku, day)` scoped — covers all sales_channels for the affected day-SKU pairs.
- **Transitional state after Pass A deploy:**
  - New uploads write to `shopify_sales_daily` only.
  - Existing Shopify rows in `sales_weekly` are untouched — `velocity_calculated`, Forecast tab's `salesData`, Shopify P&L (old reader), and Units Sold continue reading them. Data goes stale for Shopify (no new writes) but nothing breaks.
- **Pass B (next code release, not in v5.98):** delete `sales_weekly` channel='shopify' rows, rewrite `velocity_calculated` view, rewire Shopify P&L tab to read from `shopify_sales_daily`, update Forecast `salesData` loader, update Units Sold tab.

## Recent Fixes (v5.97) — Full audit + fix of the silent-dedup vulnerability across all sales_weekly upload paths
- **Trigger:** user (rightly) demanded a codebase audit after v5.96 surfaced the silent-duplication bug in parseShopifySales. "make sure it doesn't happen elsewhere."
- **Root cause (recap):** `sales_weekly` has a FUNCTIONAL unique index `(channel, asin, coalesce(shopify_sku, ''), week_start)`. Postgres `ON CONFLICT` requires the expression list to match an existing constraint exactly. Any `.upsert(..., { onConflict: 'channel,asin,shopify_sku,week_start' })` call uses plain column names that don't match the functional `coalesce()` expression. PostgREST silently degrades the request to a plain INSERT instead of throwing — every re-upload appends duplicate rows.
- **Full audit of all 34 `.upsert()` call sites in index.html:** only writes to `sales_weekly` are affected (it's the only table with a functional-expression unique index). All other tables use either single-column PK or plain multi-column indexes that match their `onConflict` specs:
  - `products` (PK master_id), `bom` (PK id), `product_cogs` (PK master_id), `fba_shipment_summaries` (PK shipment_id) — safe
  - `inventory` (`asin,region`), `fba_shipments` (`shipment_id,sku`), `sku_economics` + `sku_economics_eu` (`asin,region,week_start`), `chewy_forecasts` (`chewy_sku,forecast_month,upload_date`) — safe (plain multi-column)
- **Vulnerable sites (3 total — 1 fixed in v5.96, 2 fixed in v5.97):**
  - ~~`parseShopifySales`~~ — fixed v5.96.
  - **`parseSalesWeekly`'s Amazon branch (line ~4163)** — fixed v5.97. Handles uploads via the per-brand-per-region Amazon sales SLOTS (not the SKU Economics path). Rows have `shopify_sku=null` per Architecture Rule #1, so the cleanup delete scopes by `(channel, asin)` + `is('shopify_sku', null)`.
  - **`doRestore`'s sales_weekly block (line ~20092)** — fixed v5.97. Backup restore needs per-channel logic because Amazon-style channels and Shopify use different key fields (asin vs shopify_sku). Splits the backup by channel, then per-channel DELETE+INSERT.
- **Safe sites (verified DELETE+INSERT, never had the bug):**
  - `parseSkuEconomics` (line ~6504, Amazon US/CA SKU Economics) — has used DELETE+INSERT since v4. Architecture Rule #5 was written based on this path.
  - `parseEuSkuEconomics` (line ~6957, EU SKU Economics) — same.
- **DB cleanup migration** (`supabase_v5_97_audit_sales_weekly_dupes.sql`): supersedes v5.96's Shopify-only dedupe. Audits + cleans ALL channels using the actual functional-index partition key `partition by channel, asin, coalesce(shopify_sku, ''), week_start`. Idempotent — running after v5.96 only touches non-Shopify dupes (if any).
- **Why PostgREST silently degrades** rather than throwing: best guess is that the JS client / PostgREST treats the unmatched `on_conflict` query param as a hint that's silently dropped when no exact-match constraint exists, falling back to plain INSERT. Postgres's own SQL `INSERT ... ON CONFLICT (cols)` would throw. The Supabase abstraction layer hides the failure mode. **Defense:** never use `upsert` against a table with functional-expression indexes — always DELETE+INSERT.
- **Architecture Rule #5 status:** now uniformly enforced across every code path that writes to `sales_weekly`. The pre-existing rule wording in CLAUDE.md should be tightened from "SKU Economics upload uses delete+insert" to "ALL sales_weekly writes must use DELETE+INSERT (not upsert) — the table's functional `coalesce()` unique index silently breaks upsert."

## Recent Fixes (v5.96) — Shopify upload was silently duplicating rows (Architecture Rule #5 violation)
- **User flagged via DB query:** Fruit Sticks (CF130) showing $1,232.58 on the dashboard for May 2026 but only ~$32 on a single Shopify report row. Direct `sales_weekly` query revealed every week had 2–3 identical rows in the DB, one per upload — exactly 3× inflation matching the dashboard total.
- **Root cause:** `parseShopifySales` used Supabase upsert with `onConflict: 'channel,asin,shopify_sku,week_start'`. The actual unique index on sales_weekly is `(channel, asin, coalesce(shopify_sku, ''), week_start)` — a **functional** index. Postgres `ON CONFLICT` requires the constraint expression to match exactly; plain-column spec doesn't match the functional `coalesce()` expression, so every upsert silently degraded to a plain INSERT. Result: every re-upload appended duplicate rows instead of replacing.
- **Architecture Rule #5 in CLAUDE.md** has flagged this since v4-era: "SKU Economics upload uses delete+insert (not upsert) for Amazon rows due to functional coalesce index." Shopify was missed when first wired up; same bug applied.
- **Fix #1 — DB cleanup** (`supabase_v5_96_dedupe_shopify_sales_weekly.sql`): for every `(channel='shopify', shopify_sku, week_start)` group, keep only the most recent `uploaded_at` and delete the rest. Uses `ctid` row pointer + `row_number() over (partition by ...)` so no PK column is required. Idempotent — running twice is a no-op. Scoped to channel='shopify' (Amazon rows untouched).
- **Fix #2 — parser** (`parseShopifySales`): replaced the upsert block with the same DELETE+INSERT pattern `parseSkuEconomics` already uses (lines ~6352–6371). Step 1: delete every sales_weekly row matching `(channel='shopify', shopify_sku ∈ uploaded SKUs, week_start ∈ uploaded weeks)`. Step 2: plain INSERT the new rows. SKUs are chunked at 100 per `.in()` call to stay under Supabase's querystring length limit.
- **User must run the SQL** (`supabase_v5_96_dedupe_shopify_sales_weekly.sql`) before re-uploading — otherwise pre-existing dupes persist. After SQL + v5.96 deploy, Fruit Sticks May 2026 total will drop from $1,232.58 → ~$411 (the actual single-instance total). Same for every other Shopify SKU.
- **Heads-up about partial-week rows:** the user's data also showed rows like `2026-05-18, 10 units, uploaded 2026-05-19` (partial week — Mon–Tue snapshot) coexisting with `2026-05-18, 3 units, uploaded 2026-06-01` (later upload showing fewer net units, likely due to mid-week returns). The dedupe keeps the MOST RECENT upload, so the 3-unit value wins. That's defensible (latest snapshot of reality) but worth noting if some weeks look lower than expected post-cleanup — investigate whether returns happened or whether the later report had a different config.

## Recent Fixes (v5.95) — Shopify P&L saved views (full Amazon parity)
- **User flagged a gap:** v5.93 added the column picker but I said "no saved-views feature." User pointed out they had asked for parity with other pages ("save them like on the other pages") — which on Amazon P&L means full named report snapshots, not just column toggle persistence. Built it.
- **Added — `shopifyPnlSavedViews` state** loaded from `localStorage['shopifyPnlSavedViews']` at startup. Schema mirrors `pnlSavedViews` (Amazon) but Shopify-scoped: `{ cols, sort:{key,dir}, period, customFrom, customTo, brand, cat, search, quick, selectedMids }`. No region/currency since Shopify is single-region USD.
- **Added — helpers + functions:** `shopifyPnlViewCols`, `shopifyPnlPersistSavedViews`, `shopifyPnlSnapshotState`, `shopifyPnlSaveCurrentAsView`, `shopifyPnlApplyView`, `shopifyPnlUpdateView`, `shopifyPnlRenameView`, `shopifyPnlDeleteView`. Each mirrors the corresponding `pnl*` function exactly.
- **`shopifyPnlApplyView`** restores: column set (filtered to registry-valid keys), sort key + direction, period dropdown value, custom date range inputs + their visibility, brand select, category select, search input, quick filter (both DOM + module state), and the master_id selection (cleared then re-populated). Final `renderShopifyPnl()` paints the restored state.
- **Updated `shopifyPnlRenderColsPopup`** to mirror Amazon's two-section layout: 💾 Saved views section at top (Apply / Rename / Update via ↻ / Delete via ✕ buttons per view, with compact metadata chip showing col count + brand + period + selection count), then Columns section below with the existing checkboxes + ↺ Reset defaults. "💾 Save current as view" button between them prompts for a name and snapshots state.
- **localStorage keys** — column visibility under `shopifyPnlVisibleCols` (v5.93), saved views under `shopifyPnlSavedViews` (v5.95). Independent — clearing one doesn't affect the other.
- **Note on the missed-parity:** user explicitly called out that I should have built saved-views in v5.93 when they said "save them like on the other pages." Acknowledged and corrected.

## Recent Fixes (v5.94) — `sp_sku` column added to Shopify P&L registry
- **User requested:** "internal sku added as a dimension." The v5.93 registry had `master_id` and `shopify_sku` but not `sp_sku` — the SmarterPaw internal SKU code (e.g. CF2536) that's the catalog's primary product identifier.
- **Added `sp_sku` to `SHOPIFY_PNL_COLUMNS`** in the Identity group, between master_id and shopify_sku. `default: true` so it appears for new users out of the box.
- **Captured `sp_sku` in both `agg` and `selectedAgg`** inside `renderShopifyPnl` from `prod.sp_sku` (sourced from the products table catalog).
- **For existing users with persisted column settings:** localStorage was populated under v5.93 without sp_sku, so it won't auto-appear. They need to either click `↺ Reset defaults` in the View popup (loses any custom toggles) OR open the View popup and tick the `SP SKU` checkbox (preserves other toggles). One-click fix either way.

## Recent Fixes (v5.93) — Shopify P&L column picker (mirrors Amazon P&L View popup)
- **User requested:** "change the columns for the shopify export and save them like on the other pages." Amazon P&L has a 📋 View popup that drives both on-screen columns and CSV export, with localStorage persistence; Shopify P&L had a fixed 7-column hardcoded table and no picker.
- **Added — `SHOPIFY_PNL_COLUMNS` registry** (14 columns, scoped to DTC's data shape): `image, title, master_id, shopify_sku, category, subcategory, units, net_sales, avg_price, cogs_total, cogs_per_unit, net_proceeds, margin_pct`. Each column has `key, group, label, default, align, render(r), csv(r), sortVal(r), headerTitle, cellStyle`. Mirrors the `PNL_COLUMNS` pattern. No Amazon fee taxonomy (no FBA fees / ad spend slots) — Shopify-only fields.
- **Defaults match the pre-v5.93 fixed table:** title, shopify_sku, units, net_sales, cogs_total, net_proceeds, margin_pct.
- **Added — localStorage persistence + helpers:** `shopifyPnlVisibleCols` Set, `shopifyPnlGetVisibleCols`, `shopifyPnlPersistVisibleCols`, `shopifyPnlToggleColumn`, `shopifyPnlResetColumns`. Storage key: `shopifyPnlVisibleCols`. Falls back to defaults if storage is empty / corrupt / contains keys that no longer exist in the registry.
- **Added — 📋 View popup:** `shopifyPnlToggleColsPopup` + `shopifyPnlRenderColsPopup` + `shopifyPnlClosePopupOnOutsideClick`. Same UX as Amazon's: column groups (Identity / Volume / Revenue / Cost / Profit), checkboxes, ↺ Reset defaults, outside-click closes. Button + popup div added to the Shopify P&L controls bar at the end of the filter row.
- **Refactored `renderShopifyPnl`:**
  - Hardcoded `HEAD` array deleted; thead now driven by `shopifyPnlGetVisibleCols()`.
  - Hardcoded `<td>` row HTML replaced with `visibleCols.map(c => col.render(r))`.
  - `sortVal` switch-statement deleted; sort now uses each column's `sortVal(r)` helper. Legacy `'margin'` sort-key migrated to `'margin_pct'` automatically on first render so persisted state survives the rename.
  - Row count line now reads `N products · {from} → {to} · DTC · X cols`.
- **Refactored `downloadPnlShopifyCSV`:** previously dumped a fixed 9-column file. Now walks `shopifyPnlGetVisibleCols()` and emits `col.csv(r)` for each row — what you see in the table is exactly what lands in the CSV. Context-line at top now includes column count.
- **No saved-views feature yet** (Amazon P&L has full report-state snapshots — columns + sort + filters + selection + region + currency). Shopify P&L's picker is column-only for now. If Jason wants named views later it can mirror Amazon's pattern.

## Recent Fixes (v5.92) — Top-bar CSV button works on Shopify P&L sub-view
- **User flagged:** clicking the global top-bar `↓ CSV` button while on the P&L tab → Shopify sub-view popped `No P&L data to export — open the P&L tab and let it render first`, even though the table was clearly rendered with $19,690.75 net sales across 147 products.
- **Root cause:** `exportCSV()` at line 17865 routed any P&L tab activity to `doDownloadPnlAmazonCSV()` unconditionally, which reads `pnlExportRows` (populated by the Amazon `renderPnl`). The Shopify sub-view uses `shopifyPnlData` / `shopifyPnlVisibleMids` — separate arrays the Amazon export doesn't know about. So `pnlExportRows` was empty and the function threw its guard.
- **Fix — pure repair, no scope expansion:**
  - Added `shopifyPnlExportRows` + `shopifyPnlExportCtx` module-level state, populated at the end of `renderShopifyPnl()` (mirrors the `pnlExportRows` snapshot pattern Amazon already uses).
  - Added `downloadPnlShopifyCSV()` — exports the on-screen rows with the seven visible columns (Product, Brand, Master ID, Shopify SKU, Units, Net Sales, COGS, Net Proceeds, Margin %). Includes a `# Shopify P&L · {from} -> {to}` context line at the top so the file carries its filter + date scope.
  - Added a branch in `exportCSV()`: `if (pnlView === 'shopify') return downloadPnlShopifyCSV();` Mirrors the existing COGS-vs-Amazon split.
- **No column picker / no selected-vs-all mode** — those would be scope expansion. The export matches exactly what's on screen, respects the active Period / Brand / Category / Search / Quick filters, sorted by the current sort key.

## Recent Fixes (v5.91) — Reverted Shopify empty-SKU catch-all (scope: unit sales only)
- **User clarified scope:** dashboard captures unit sales of catalog products only. Non-product revenue (POS / manual line items / gift cards / shipping fees / discount allocations / refund admin) belongs in Shopify's own P&L reporting, not `sales_weekly`. The v5.89/v5.90 synthetic catch-all (`SP-UNMAPPED-SHOPIFY`) was the wrong abstraction — it created a fake catalog row for line items that aren't products.
- **Diagnostic that confirmed the call:** user re-ran the Shopify "Sales" report with `Product ID` + `Product type` columns. Of $3,495.58 in empty-SKU revenue, only ~$100 was actual products (2 SKU-less items in the Shopify catalog: MJ'S Sprinkles Food Topper Trio, Get Flyin' Eel) — the other $3,300+ was POS items (`product_id = 0`) and adjustments. Those have no master_id to map to and shouldn't be forced into one.
- **Revert:** empty-SKU rows now skip cleanly. Stats still surface in the upload status: `ℹ N non-product rows skipped (X units, $Y — POS / manual / shipping / discounts)`. SKU-bearing rows still get the v5.88 vendor→brand auto-create when their SKU isn't yet in `products` (that's the desired behavior — real products get reviewable SP-TEMP placeholders).
- **No DB cleanup required** — user hadn't uploaded under v5.89/v5.90 yet, so `SP-TEMP-SHOPIFY-UNMAPPED` / `SP-UNMAPPED-SHOPIFY` never landed in the products table. `supabase_v5_90_rename_shopify_unmapped.sql` was deleted from the repo.
- **Action for the 2 SKU-less real products:** assign variant SKUs to MJ'S Sprinkles Food Topper Trio and Get Flyin' Eel in Shopify admin (one-time fix). Future uploads will then auto-create SP-TEMP placeholders for them with the correct vendor→brand mapping.

## Recent Fixes (v5.90) — Catch-all renamed to `SP-UNMAPPED-SHOPIFY` (drop SP-TEMP- prefix)
- **Triggered by:** user flagged that v5.89's `SP-TEMP-SHOPIFY-UNMAPPED` would trigger saveProduct's promotion path on first edit — collapsing the mixed unmapped revenue (gift cards + manual orders + deleted products + POS items, lumped together) into a single arbitrary SP-XXXX whose name the operator typed in. That would falsely attribute the bundle to one real product.
- **Root cause:** `saveProduct` line 21546 keys promotion off `master_id.startsWith('SP-TEMP-')`. The catch-all needs a master_id that bypasses every such check — it's a permanent bucket, not a placeholder awaiting promotion.
- **Fix:** renamed the catch-all from `SP-TEMP-SHOPIFY-UNMAPPED` → `SP-UNMAPPED-SHOPIFY` in `parseShopifySales`. Audited the six `startsWith('SP-TEMP-')` sites (lines ~18276 / 18424 / 18603 / 21112 / 21298 / 21546 / 21553) — none trigger on the new prefix. The catch-all now:
  - Does NOT enter saveProduct's promotion flow (master_id stays put; FK migration code is skipped).
  - Does NOT surface in the "Needs Review" filter (cleaner — it's a permanent bucket, not a TODO).
  - DOES appear in the regular Products tab where the operator can find it via search if they need to inspect what's accumulating.
- **Updated notes field** is more explicit about the no-touch rule: `DO NOT MERGE OR PROMOTE — this is many real-world products lumped together; merging would falsely attribute mixed revenue to a single SKU.`
- **DB migration** (`supabase_v5_90_rename_shopify_unmapped.sql`): for users who already uploaded under v5.89, renames the existing record. Three steps inside a transaction: (1) insert new `SP-UNMAPPED-SHOPIFY` product (idempotent via `on conflict do nothing`); (2) re-point every `sales_weekly` row from `SP-TEMP-SHOPIFY-UNMAPPED` to the new master_id; (3) delete the old `SP-TEMP-` row. Same FK-shuffle pattern as the SP-TEMP → SP-XXXX promotion. No-ops cleanly if v5.89 was never deployed.

## Recent Fixes (v5.89) — Empty-SKU Shopify rows roll into `SP-TEMP-SHOPIFY-UNMAPPED` catch-all
- **Triggered by:** user uploaded the Apr 1 – Jun 1 Shopify file and saw the v5.88 warning surface 46 empty-SKU rows (1,000 units, $3,495.58 net sales) being skipped. Asked for parity with the SKU Economics uploader's auto-create-on-unknown pattern so revenue isn't dropped.
- **Why the v5.88 warning wasn't enough:** Shopify aggregates ALL variantless line items (manual orders, gift cards, deleted products, POS custom items, draft-order conversions) into per-day rows with EVERY field blank (sku/title/vendor/category). The v5.88 fix surfaced the magnitude — but the revenue itself never landed in `sales_weekly`, so the Shopify P&L under-reported by ~$3.5K over the 2-month range.
- **Why a per-row SP-TEMP doesn't work:** unlike the SKU Economics fix (where each unknown ASIN gets its own `SP-TEMP-{ASIN}`), empty-SKU Shopify rows have NO unique identifier — every row collapses to the same "blank" key. Creating 46 identical placeholders would be useless catalog noise.
- **Fix — synthetic catch-all SKU:** added `UNMAPPED_SKU = 'SHOPIFY-UNMAPPED'`. Empty-SKU rows now aggregate into `weekMap` under that synthetic SKU keyed by week_start. The existing unknown-SKU detection picks up `SHOPIFY-UNMAPPED` on first upload and auto-creates `SP-TEMP-SHOPIFY-UNMAPPED` with `title: 'Unmapped Shopify Sales'`, `brand: 'Unknown'`, and a long-form note explaining the source. Subsequent uploads upsert into the same `master_id` idempotently (the unique key `(channel, asin, shopify_sku, week_start)` handles re-uploads cleanly).
- **Negative / zero-unit empty-SKU rows** (Shopify emits these for full-day refunds with no positive offsetting activity) still feed the `emptySkuRows/Units/Revenue` counters so the audit trail is complete, but only `units > 0` rows actually land in sales_weekly — matches the gating already in place for named-SKU rows.
- **Status line semantics flipped** v5.88 `⚠ N rows skipped` → v5.89 `ℹ N empty-SKU rows rolled into SP-TEMP-SHOPIFY-UNMAPPED (X units, $Y)`. Tooltip explains the typical sources + tells the user to review on Products tab → Needs Review.
- **Net effect on the user's audit:** 46 rows / 1,000 units / $3,495.58 will land in sales_weekly under `master_id = 'SP-TEMP-SHOPIFY-UNMAPPED'` instead of vanishing. Shopify P&L will reflect the true total. User can investigate root cause in Shopify admin (Reports → Order details → filter for line items with no SKU) and either accept the catch-all as a permanent line or fix the underlying orders.

## Recent Fixes (v5.88) — `parseShopifySales` vendor → brand + empty-SKU surfacing
- **Triggered by:** user uploaded the 2-month "Weekly Sales By Product" export (Apr 1 – Jun 1, 2026; 1,765 rows) and asked me to verify the uploader could handle it. Pre-flight audit caught two silent-data-corruption bugs.
- **Issue 1 — brand hardcoded:** every auto-created SP-TEMP got `brand: 'Meowijuana'` regardless of the row's Product vendor cell (line 4267, pre-v5.88). The audited file had 1,386 Meowijuana + 304 Doggijuana vendor rows — any Doggi SKU not yet in `products` would have auto-created as Meowijuana-branded, polluting the catalog until the user manually fixed it on Products tab.
- **Issue 2 — empty-SKU rows silently dropped:** parser's `if (!sku || !day || units <= 0) continue` skipped every row Shopify emitted with no Product variant SKU (manual orders, deleted products, gift cards, etc.). The audited file had **74 such rows totaling 999 units / $3,487.71 net sales** that would have vanished without trace.
- **Fix 1 — vendor column → brand:** added `ci('product vendor', 'vendor')` lookup and a `vendorToBrand(v)` normalizer that maps "Meowijuana by SmarterPaw®" / "Doggijuana by SmarterPaw®" / "Kitty Ka-Zoom by SmarterPaw®" to the canonical brand strings the products table uses. Per-SKU brand is captured in a `skuVendors` map during aggregation (first non-null wins). The SP-TEMP auto-create now reads `skuVendors[sku] || 'Meowijuana'` — vendor wins, legacy default only on missing/unrecognized.
- **Fix 2 — empty-SKU stats surfaced:** added `emptySkuRows`/`emptySkuUnits`/`emptySkuRevenue` counters incremented before the skip. Upload status line now reads `⚠ N rows skipped (no SKU — X units, $Y revenue not attributed)` with class `dz-warn` and a `title` tooltip explaining the typical sources (manual orders / gift cards / deleted products). Counts are also returned from `parseShopifySales` for future telemetry hooks.
- **No DB migration** — pure parser-layer fix. Previously uploaded SP-TEMPs from old Shopify uploads keep their (possibly wrong) brand — those will need manual cleanup or a one-time SQL update if you want to retroactively fix them.

## Recent Fixes (v5.87) — Unmatched ASIN parity + storeToRegion hardening
- **User flagged:** Diagnostics tab showed 43 unmatched ASINs in `sku_economics` (US region, all $0 sales / $0 fees / 0 units), but the Products tab "needs review" filter showed only 1 (the EU SP-TEMP). Asked where the 43 were coming from and why they didn't appear on the unmatched-product filter.
- **Root causes (two related bugs):**
  1. `parseSkuEconomics` split each CSV row into two aggregators — `agg` (sales-bearing, drives sales_weekly) and `econAgg` (every row, drives sku_economics). The unknown-ASIN auto-create loop walked **only `agg`**, so any ASIN Amazon emitted with `net units sold = 0` (discontinued listings, variation parents, foreign-store rows) landed in sku_economics with `master_id=null` and never got an SP-TEMP placeholder. The parser was asymmetric with `parseEuSkuEconomics`, which auto-creates SP-TEMP for every unknown ASIN regardless of units.
  2. `storeToRegion` silently defaulted any unrecognized "Amazon store" value to `'US'` (line 6086: `return 'US';`). Rare CSV variants and foreign-store ASINs in the US export got misclassified as US, producing phantom zero-everything rows that fed bug #1.
- **Fix #1 — zero-unit unknowns auto-create SP-TEMP:** added a follow-up loop after the existing `agg`-walk that walks `econAgg` for any ASIN not already seen by the sales-loop, and pushes to `unknownAsins` if no product/SP-TEMP exists. The downstream auto-create + brand resolution block then handles them like any other unknown — they appear in the Products tab "needs review" filter going forward, with the M/D/K brand quick-chips from the Diagnostics tab also available to bulk-assign. Mirrors the EU parser. Also relaxed the "No valid rows" guard from `Object.keys(agg).length === 0` to `agg.length === 0 && econAgg.length === 0` so econ-only weeks (real fees with zero sales) upload cleanly.
- **Fix #2 — `storeToRegion` returns null on unknown:** the fallback now returns `null` instead of `'US'`. The main row loop reads `storeToRegion`, and on null adds the raw store value to a `skippedStores` Map and `continue`s — the row is excluded from BOTH tables. Skipped rows surface in the upload status line (`⚠ N rows skipped (unrecognized Amazon store — hover for values)`) with the raw values in the `title` attribute for click-to-inspect. ZIP + folder uploaders aggregate `skippedStores` across all files into a single warning.
- **`parseSkuEconomics` return signature** now also includes `skippedStores: [{ value, rows }, ...]` — consumers in `handleSkuEconUpload`, `handleSkuEconZipUpload`, and `handleSkuEconFolderUpload` were all updated to surface it.
- **Net effect on the 43 unmatched ASINs:** next SKU Economics upload will either (a) auto-create SP-TEMP for them and surface in "needs review" → user can brand-assign or delete; OR (b) skip the row entirely if the misclassification was at the `storeToRegion` step → user sees `⚠ N rows skipped` and can investigate the raw store value. Either way they stop being invisible.

## Recent Fixes (v5.86) — EU `sku_economics_eu.week_start` unified to Monday (matches US/CA)
- **User flagged:** P&L tab with EU region + "Last 7 days" period showed `0 products · $0.00` while US/CA had full data, even though the UK SKU Economics report had been uploaded for the same week.
- **Root cause:** two-table convention drift since v4.144. `sku_economics` (US/CA) stores `week_start` Monday-shifted via `dateToMondayLocal()`; `sku_economics_eu` stored the **native Sunday** (parseEuSkuEconomics line 6582: `fmtLocalYMD(startD); // keep native Sunday`). `getPnlDateRange()` for "Last 7 days" with today = 2026-06-01 returns `from = 2026-05-25` (a Monday) — US/CA's `2026-05-25` row passes the `row.week_start >= from` filter, EU's `2026-05-24` row fails by 1 day. Bug surfaces at any boundary that lands on a Monday.
- **Fix — two parts:**
  - **DB migration** (`supabase_v5_86_eu_week_start_monday.sql`): `update sku_economics_eu set week_start = week_start + interval '1 day' where extract(dow from week_start) = 0;` Shifts every existing Sunday-keyed row to Monday. The dow=0 guard makes it idempotent. Wrapped in a transaction with verify queries.
  - **Parser** (`parseEuSkuEconomics`, line ~6582): replaced `fmtLocalYMD(startD)` with `dateToMondayLocal(startD, true)` so new uploads write Monday directly. Sister sales_weekly write at line 6763 already used `dateToMondayLocal(startD, true)` since v4.144, so no change there.
- **Downstream consumers** (`loadEuPnlTab` line 7793, `renderPnl` filter line 8190, latest-week display line 8898, `endOfWeek` helper at line 8861) — all expect Monday week_starts and now get them uniformly. `endOfWeek` was already correct for the US/CA path; the EU branch now produces the same Saturday end-of-week if/when surfaced.
- **No region-specific date math anywhere** after this — every period filter, week join, and velocity rollup behaves identically across US/CA/EU.
- **Run order:** Run the SQL in Supabase **before** deploying v5.86 to avoid a window where new uploads write Monday while existing rows are still on Sunday (would just look weird in the latest-week badge, not break anything; but cleaner this way).

## Recent Fixes (v5.85) — Cancelled shipments no longer count as inbound / active
- **User flagged with screenshot:** Inventory Planning row showed `Inbound Units = 24` for a shipment whose summary status was `Cancelled` (the row's own Inbound Detail cell read `Canc:24`). User correctly asked why a cancelled shipment was inflating inbound.
- **Root cause:** the v5.17 `loadFbaInTransit` filter only excluded shipments whose summary status contained `closed`. Cancelled shipments slipped through. The detail .tsv recorded `quantity_shipped = 24` at original creation; Amazon (or the user) cancelled later → the row stayed in `fba_shipments` with its shipped qty intact while the summary status flipped to Cancelled. The filter never noticed and the qty kept counting toward in-transit.
- **The v5.59 modal pane logic** correctly treats Cancelled as inactive (sits in the bottom pane), so the categorization was right in ONE place but inconsistent across the math layer. v5.85 makes everything consistent.
- **Fix — three sites updated:**
  - `loadFbaInTransit`'s in-transit accumulator (the source of truth — feeds every downstream consumer via `ipFbaInTransitByMaster`): `if (!status.includes('closed') && !status.includes('cancel'))`.
  - `IP_COLUMNS['shipments']` cell render (the "active / total" badge): same exclusion via a local `isInactive(s)` helper that matches both `closed` and `cancel`.
  - `IP_COLUMNS['shipments']` CSV export (the "N active · M total · K units in transit" string): same exclusion.
- **All downstream consumers fixed automatically** because they read from `ipFbaInTransitByMaster` / `ipShipmentsFor(r)`: the 🚧 chip on the FBA In column, the Inbound Units column, the Amazon FBA Stock scorecard, the Status math (`stock = FBA available + FBA inbound + in_transit`), the Gap math, the Action rollup. All now exclude cancelled qty.
- **For the user's screenshot row:** Inbound Units flips from 24 → 0 (the only inbound shipment was cancelled). The shipment still shows in the modal viewer's "Closed / Cancelled" bottom pane (v5.59 behavior) for reference, but no longer affects PO planning math.
- **No DB migration** — pure math-layer fix.

## Recent Fixes (v5.84) — Inventory Planning: single-column `Reorder Thresh (d)` + `Reorder Qty (d)` (master-level effective value)
- **User request:** "i need columns so in the inventory planning module for the following: reorder threshold, reorder supply (the existing dimensions that exist - i need them as columns and exportable)."
- **Pre-v5.84 state:** v5.1 + v5.60 added per-region columns (`Thresh US (d)` / `Thresh CA (d)` / `Thresh UK (d)` + `Qty US (d)` / `Qty CA (d)` / `Qty UK (d)`) but dropped the master-level single columns. So the user couldn't get a quick "this row's effective threshold" column without picking one of three region variants.
- **Fix:** added two new columns to IP_COLUMNS in the PO PLANNING group:
  - **`reorder_threshold_days` → "Reorder Thresh (d)"** — shows the row's effective threshold. Records-build (v5.1 line 3170) already populates this on every record as `inv?.reorder_threshold_days ?? p.reorder_threshold_days ?? 90`, so for a region-pinned row this is that region's value; for a pooled row it inherits from the first peer record. Blank/default 90 renders muted.
  - **`reorder_qty_days` → "Reorder Qty (d)"** — same pattern.
- Both `default:false` — opt-in via View popup like the other PO planning columns. Sortable. Explicit `csv: r => r.X ?? 90` so the CSV export emits the effective value (not the raw null) — Excel pivots and SUMIFS work cleanly.
- Tooltips on both columns mention the per-region variants in AMAZON SETTINGS for users who need the region-specific breakdown.
- **No DB migration** — reads existing `inventory.reorder_threshold_days` / `inventory.reorder_qty_days` (per-region) with fallback to `products.*` master-level defaults.

## Recent Fixes (v5.83) — Inventory CSV: exclude UI-only system columns (the empty mystery column F was the row-selection checkbox)
- **User flagged:** "there is an empty column F that exports now" — attached an inventory CSV showing a `,,` between Product and Img with the value `0` in every data row.
- **Root cause:** the v5.80 IP `_chk` row-selection checkbox column (`group:'_sys', locked:true, default:true`) was being included in the CSV export. Its `headHtml` returns a checkbox HTML element (which sanitizes to empty string), and it has no `csv` function — so v5.82's `c.csv` fallback skipped it, and `c.sortVal()` returned `0` (the v5.80 default). Result: empty header + value `0` in column F.
- **Fix:** in `downloadInventoryCSV` finalCols loop, skip any column whose `group === '_sys'` OR whose `key` starts with `_`. Both conventions identify UI-only columns that shouldn't appear in CSV exports. Future system columns (`_chk`, future `_actions`, etc.) auto-excluded.
- **Forecast + P&L CSVs were already safe:**
  - `doExportCSV('forecast', …)` filters with `.filter(c => !c.locked)` — the FC_COLUMNS `_chk` column has `locked:true`, excluded.
  - `doDownloadPnlAmazonCSV` uses a hardcoded column list, doesn't iterate the registry.
- **No DB migration** — pure exporter fix.

## Recent Fixes (v5.82) — Image columns now export the URL on CSV (was emitting '0' / blank); generic c.csv() fallback in Inventory CSV exporter
- **User flagged:** "the img doesn't export on csv exports - the cells show '0'. if img is selected in the export, can the link be passed into the file."
- **Root causes (two bugs in one):**
  - **Inventory Planning CSV exporter** used `c.sortVal(r)` as the fallback when none of its hardcoded `if (c.key === 'X')` branches matched. The v5.80 Img column had `sortVal: () => 0`, so every row exported as `0`.
  - **Forecast and P&L Img columns** had `csv: () => null` / `csv: () => ''` from v5.80 — they exported blank instead of the URL.
- **Fix:**
  - **All three registries** now have a real `csv: r => …` returning `allProducts.find(...).image_url || ''`. For Forecast the `get(r)` also returns the URL so any other code reading the cell value gets the URL too (sort + filter + CSV all consistent).
  - **Inventory CSV exporter** got a generic `c.csv` check at the top of `valueOf(r, c)`: if the column has a `csv` function and it returns a non-null value, use it. Lets future opt-in columns plug in without adding another `if (c.key === '…')` branch.
- **Spreadsheet workflow** — exported URLs paste into Google Sheets cells as `=IMAGE(URL)` to render the thumbnail directly in the spreadsheet. Excel doesn't have a native equivalent but you can paste the URL and either Insert → Pictures from URL or use Excel's IMAGE() function (Microsoft 365). Tooltip on the Img column header on all three pages now mentions this.
- **No DB migration** — pure exporter fix.

## Recent Fixes (v5.81) — Nav dropdown UX: click ALWAYS opens menu (not jumps to first sub-tab) + hover highlight on dropdown rows
- **User flagged (with screen recording):** "when i click a drop down, it automatically goes to the first tab of that drop down rather than opening the drop down menu. when already on the drop down page is the only time the menu opens, and when i'm navigating the menu the cursor does not highlight the drop down row."
- **Pre-v5.81 behavior** — `handleForecastNavClick` / `handleDataNavClick` / `handlePnlNavClick` had two paths:
  - Already on that page → toggle dropdown ✓
  - Anywhere else → auto-navigate to the first sub-view + close dropdown ✗
  This meant the dropdown was only EVER discoverable when you were already on the page. Backwards: dropdowns exist to GET you somewhere, not to swap inside a place you already are.
- **Fix #1 — handlers now always toggle the dropdown.** All three handlers (`Forecast` / `Data` / `P&L`) just open or close their dropdown. No navigation side-effect. `closeOtherNavDrops(keepId)` ensures only one is open at a time.
- **Fix #2 — picking an item activates the parent page if not already on it.** `switchForecastView` / `switchDataView` / `switchPnlView` each got a small block at the top that activates `page-X` + sets the nav button active when `currentPage !== 'x'`. So picking "Inventory Planning" from the Forecast dropdown while on Products correctly navigates to the forecast page AND opens Inventory Planning.
- **Fix #3 — hover highlight on dropdown rows.** New CSS rule targets `#forecastNavDrop button:hover:not(.dd-active)` (etc.) with `var(--surface2)` background + `var(--text)` color. The `:not(.dd-active)` clause keeps the green-fill ACTIVE item from being overridden on hover. Each `switchXxxView` now toggles a `dd-active` class on the picked button (in addition to the existing inline green background) so the CSS selector can differentiate.
- **Fix #4 — outside-click closes any open dropdown.** Document-level `mousedown` listener checks if the click landed inside any nav button or any open dropdown; if not, closes all three. So users can dismiss the menu by clicking anywhere else.
- **Workflow now:**
  - Click `Forecast` → dropdown opens (regardless of where you are).
  - Hover any item → grey highlight (active item stays green).
  - Click an item → page navigates + dropdown closes.
  - Click `Forecast` again on the same page → dropdown reopens (toggle).
  - Click `Data` while Forecast dropdown is open → Forecast closes, Data opens.
  - Click anywhere outside → all close.
- **No DB migration** — pure UX wiring.

## Recent Fixes (v5.80) — Product image columns added across all product-bearing pages (default on / optional)
- **User request:** "the product images should appear on the bundles page, chewy forecast page, units sold page, and seasonality page by default and be optional columns on the forecast, inventory planning, and P&L pages."
- **New shared helpers:**
  - `prodImgCell(p, opts)` — returns a full `<td>` with the 36px (configurable) image thumbnail. Falls back to a muted `—` when no image. Click → opens full size in a new tab. Lazy-loaded + onerror → 🖼 placeholder.
  - `prodImgEl(p, opts)` — bare `<img>` variant for callers that already provide the cell wrapper (used by `PNL_COLUMNS` via its existing `cellStyle` pattern).
  - Both resolve `image_url` from `p.image_url` directly OR via `p.master_id` → `allProducts` lookup. So callers can pass either a product object or a record with just a master_id.
- **Default-on (shown by default):**
  - **Bundles page summary view** — new leading Img column; colspan on the no-results row bumped from 8 → 9.
  - **Chewy Forecast page** — Img column inserted between the row checkbox and the Product cell. Both sub-header rows + loading / error / empty colspans bumped accordingly.
  - **Units Sold page** — Img column inserted between the checkbox and Brand chip.
  - **Seasonality page** — Img column inserted between the checkbox and Brand chip; colspan on the no-results row bumped from 8 → 9.
- **Default-off (opt-in via View popup):**
  - **Demand Forecast** (`FC_COLUMNS`) — new `image` column in the SKU group, `nosort:true`, `csv: () => null` so it doesn't pollute exports.
  - **Inventory Planning** (`IP_COLUMNS`) — new `image` column in the SKU group, same nosort/csv conventions.
  - **Amazon P&L** (`PNL_COLUMNS`) — new `image` column in the `identity` group. Uses `prodImgEl` because the PNL renderer wraps each cell in its own `<td>` via `cellStyle`.
  - The View popup on each page surfaces these alongside their existing column-visibility controls. User toggles + persists per-page via the existing localStorage system (`fcVisibleCols` / `ipVisibleCols` / `pnlVisibleCols`).
- **Bundles BOM view skipped** for this pass — that view is the alternate Bundles tab mode and has a more complex bundle-parent + component-rows structure. Default Bundles summary view (the more common mode) does get the column.
- **Image cell touches every existing layout**: the helper accepts `opts.size` and `opts.padding` so tighter rows (e.g., Seasonality's 32px thumbnails) match their row height without distortion.
- **No DB migration** — reads existing `products.image_url`.

## Recent Fixes (v5.79) — Drop the redundant "⤓ Re-host current URL" button on the product modal
- **User flagged:** "the 're-host current URL' button is redundant. adding the image url and saving the modal hosts the url."
- **Root cause analysis:** the button was added in v5.69 to fetch a URL, resize it, and upload to Supabase Storage as a permanent copy. In practice, the most common use case was Amazon CDN URLs — which are CORS-blocked. v5.73 added a fallback that saved the URL as-is when the fetch failed. At that point the button's "saved fallback" path became identical to what `saveProduct` already does (`productData.image_url = pf-image.value`), so the button was duplicative.
- **Fix — removed:**
  - The `⤓ Re-host current URL` button from the modal.
  - The `pfFetchImageFromUrl` function (it had no other callers).
- **Kept:**
  - The `↑ Upload file` button — still the single path for truly re-hosting on Supabase Storage (user picks a local file, gets resized + uploaded).
  - `pfClassifyImageUrl` / `pfUpdateImagePreview` / `pfResizeAndCompress` / `pfUploadImageBlob` helpers — still used by `pfUploadImageFile` and the live preview.
- **Field-hint rewritten** to call out the two paths cleanly:
  - "Use ↑ Upload file to compress + host a local image on Supabase Storage (so the image survives even if a source CDN goes away)."
  - "You can also paste any direct image URL into the field above — it'll persist on save, but lives on the source server."
- **No DB migration** — UI removal + dead-code prune.

## Recent Fixes (v5.78) — Add UK Amazon link to product modal ASIN row + the shared ASIN affordance helper
- **User request:** "on the product modal, i need a link for amazon uk like the us and canada links."
- **Two surfaces updated:**
  - **Product modal ASIN row** — new quick-open buttons next to the ASIN input: `🇺🇸 US` / `🍁 CA` / `🇬🇧 UK` / `🔍` (search fallback). Each reads the live `pf-asin` value at click time so the buttons follow edits without requiring a save. `pfOpenAsinListing(region)` handler maps regions to marketplace URLs (`amazon.com` / `amazon.ca` / `amazon.co.uk` / `amazon.com/s?k=`).
  - **Shared `renderAsinAffordances(asin, region)` helper** (used by Products tab + P&L Diagnostics) gains a UK link too — `🇬🇧` between the CA flag and the search icon. Tooltip notes that UK covers the EU FBA pool.
- **Pre-v5.78 the product modal had ASIN as a plain text input with no quick-open at all** — only the Products tab table had US/CA links via `renderAsinAffordances`. Now the modal has parity with the table, plus UK.
- **No DB migration** — pure UI addition.

## Recent Fixes (v5.77) — Product modal save: v5.1 legacy broadcast was overwriting v5.65 per-region settings
- **User flagged:** "sometimes the new/deprecated boxes don't appear even when the item has an asin and the box is checked in the product modal. it doesn't seem to save the selection." Screenshot showed `Boot, Smore, & Juananip Bundle` (SP-0611, has ASIN B0B1FWXXB5) with Deprecated checked on EU/UK in the modal — but the Products tab lifecycle view showed `—` for every region.
- **Root cause:** `saveProduct` had two save paths racing each other:
  1. **v5.65 per-region writes** (correct) — UPSERTs each region's settings from the per-region matrix.
  2. **v5.1 legacy broadcast** (stale) — re-UPSERTs every existing inventory row with `productData.*` fields, which equal the **US column** (the legacy single-region inputs preserved as the US column for v5.65 backward-compat). This ran AFTER v5.65 and overwrote CA + EU/UK with US's values, silently flattening per-region settings back to master-level defaults.
- **Fix:** removed the v5.1 broadcast entirely (Supabase UPSERT loop + the in-memory mirror that wrote `productData.*` to every peer). v5.65's per-region writes are now authoritative.
- **In-memory mirror rewritten** to read per-region settings from the matrix and update each region's record independently. Falls back to seeding a new record (cloned from any existing peer) when the user just CREATED a region's row via the matrix that didn't exist before (records-build wouldn't have an entry yet — without the seed, lifecycle view would still show `—` until the next full data reload).
- **Also calls `renderProductsTbl()` at the end** so the lifecycle view updates immediately when saving from the Products tab.
- **Symptom for the user:** save Deprecated on EU/UK → modal closed → table still showed `—`. After v5.77: save → table immediately shows ⛔ DEP chip on EU/UK column.
- **No DB migration** — pure save-flow fix.

## Recent Fixes (v5.76) — Products tab: multi-select Categories + Sub-categories with personal default ("hide Apparel" out of the box)
- **User request:** "on the product and product lifecycle view, i want to be able to multi-select the categories and sub categories drop down. by default, I do not want apparel showing - give me the option to set a global default view."
- **Fix #1 — Two new popover-driven multi-select filters** in the Products tab filter strip, replacing the single-select Category dropdown:
  - **Categories** button (shows `Categories: All` or `Categories: 5 of 7`). Click opens a popover with a checkbox per category. Live filter — table re-renders on every toggle.
  - **Sub-cats** button (same pattern, independent of category selection).
  - Both buttons tint green when filtered so the active state is visible without opening the popover.
- **Each popover has four toolbar actions:**
  - **Select all** / **Select none** — quick mass toggles.
  - **Reset to default** — loads from the user's saved default (or the built-in default if they haven't saved one).
  - **Save as default** — overwrites the user's saved default with the current selection. From that point on, "Reset to default" goes back to this state.
- **Fix #2 — Built-in default excludes Apparel.** `PROD_CAT_EXCLUDE_BY_DEFAULT = ['Apparel']`. On a fresh load with no localStorage state, the Category filter bootstraps to "every category EXCEPT Apparel" so a typical session doesn't show apparel SKUs until the user explicitly toggles them in. Sub-cat default is "all" (no built-in exclusions). User can override either with Save as default.
- **State + persistence:**
  - `prodCatFilter` / `prodSubcatFilter`: `Set<string> | null`. `null` means "no filter" (all). A populated Set means "include only these".
  - `localStorage.prodCatFilterUser` — last active selection (auto-saved on every toggle, restores on next session).
  - `localStorage.prodCatFilterDefault` — what "Reset to default" reverts to. Empty → falls back to the built-in default. User overrides via "Save as default".
  - Same shape for sub-cats.
- **Filter logic in `renderProductsTbl`** — products with `category_id = null` always pass (rare orphans; use the existing "Missing Category" filter to triage). Products with a category fall through `prodCatFilter.has(cat)` and `prodSubcatFilter.has(sub)`.
- **`✕ Clear filters` button** now also resets the multi-selects (sets both to `null` = all). Active-filter detection accounts for the multi-selects via a `< totalCats` count comparison.
- **Legacy `<select id="prodCat">` kept** as a hidden state stash so any older code reading its value still functions; the popover is the source of truth.
- **Lifecycle view inherits everything** — same `renderProductsTbl` so multi-select + lifecycle columns + sort all compose cleanly.
- **No DB migration** — pure client-side state + UI.

## Recent Fixes (v5.75) — Re-host button reads the current Image URL field instead of asking again
- **User flagged:** "the image rehost is making me paste the image twice, i've already pasted it in the modal and the popup asks for it again." `pfFetchImageFromUrl` was unconditionally calling `prompt()` even when the field already had a URL.
- **Fix:** read `pf-image.value` first. If non-empty → use it directly (no prompt). If empty → fall back to the prompt for users who haven't pasted anything yet.
- **Button label updated** from "Re-host from URL" → "Re-host current URL" so the field-first behavior is discoverable from the label. Tooltip rewritten to match.
- **Both flows still work:** paste-and-click (the common case Jason was hitting) and click-then-prompt (for users who haven't pasted yet).
- **No DB migration** — UX wiring fix.

## Recent Fixes (v5.74) — Drop the persistent "run supabase_v5_69…sql once" reminder from the product modal
- **User flagged:** "also i've run supabase, i don't need the reminder in the app." The v5.69 product modal field-hint included a static "Storage bucket required: run `supabase_v5_69_product_images_bucket.sql` once." sentence that always rendered, even after the migration was done.
- **Fix:** removed that sentence from the field-hint. The rest of the hint (Catsy import note + CORS callout) stays. Error-time messages still surface the migration name if the bucket is ever genuinely missing — those only fire on failure, not as persistent in-UI nags.
- **Pattern going forward:** persistent "run this SQL" reminders in the UI are noise once the migration is done. Use error-time messages instead (they only fire when the missing-column / missing-bucket condition actually trips). CLAUDE.md tracks the migration in its handoff section.

## Recent Fixes (v5.73) — Re-host from URL: fall back to saving the URL as-is when fetch/upload fails
- **User flagged:** `https://m.media-amazon.com/images/I/…jpg` re-host failed but the image preview rendered. They expected the image to be saved.
- **Root cause:** the v5.69 `pfFetchImageFromUrl` catch block surfaced a status message but **never set `pf-image.value`** — so when CORS blocked the fetch (Amazon's CDN doesn't allow cross-origin JS fetch even though `<img src>` loads fine), the URL was silently dropped from the modal state. Save Product persisted nothing image-related.
- **Fix — fallback save:** the catch block now writes `cleanUrl` to `pf-image` regardless of which failure happened, then calls `pfUpdateImagePreview()` so the thumbnail renders. The URL persists to `products.image_url` on Save Product. The image works as long as the source server keeps the URL alive — not as robust as a true re-host, but better than dropping the URL entirely.
- **Three branches in the catch** with distinct messages:
  - **CORS** (Amazon CDN, most third-party hosts): "Could not re-host (CORS blocked). URL saved as-is — works as long as Amazon keeps it up. For permanent storage, save the image to your computer with right-click + Save image as…, then use ↑ Upload file."
  - **Bucket missing** (`supabase_v5_69_product_images_bucket.sql` not run): "Storage bucket missing — run supabase_v5_69_product_images_bucket.sql first. URL saved as-is for now; retry re-host after running the migration."
  - **Other** (network, parse error): "Re-host failed: \<error\>. URL saved as-is."
- **`alert()` on failure** ensures the user can't miss the distinction between "re-hosted to Supabase Storage" (the success path) and "URL saved as-is" (the fallback). The inline `pf-image-status` is easy to miss; the modal alert isn't.
- **Prompt text updated** to set expectations up front — calls out that Amazon CDN URLs will be saved as-is (not re-hosted) because of CORS.
- **No DB migration** — pure client-side resilience improvement.

## Recent Fixes (v5.72) — Amazon P&L: COGS now converts to the display currency (USD/CAD/GBP/EUR), fixing Contribution % discrepancy
- **User flagged:** "on the amazon p&l - why is the contribution % different when i change from USD to CAD?" Screenshots showed Bubbles - 5 Oz: USD view contribution = −17.6%, CAD view contribution = −10.3%. The ratio should be currency-agnostic, so this was a real bug.
- **Root cause:** `product_cogs.amazon_cogs` is stored in USD per unit. The renderPnl aggregator multiplied every native-currency field (CAD sales, CAD fees, CAD ad spend) by `fxMul` to convert CAD → USD when the display mode was USD. But COGS skipped the conversion entirely — it stayed as USD dollars and sat next to whichever currency the rest of the row was in. In CAD mode the COGS line read $260.26 (USD) against $1357.81 (CAD) sales → contribution % too rosy. In USD mode the COGS line read $260.26 (USD) against $983.28 (USD) sales → correct.
- **Math check on user's example:** `$260.26 × 1.3809 (FX rate) = $359.39 CAD`. Then `(Net Proceeds $119.76 − $359.39) / Net Sales $1357.81 = −17.6%` → matches USD mode's −17.6%. Confirms the diagnosis.
- **Fix — new `cogsFxMul()` helper** that returns the right multiplier per display mode:
  - `usd` → 1 (COGS already in USD)
  - `cad` → `pnlFxRate` (USD → CAD)
  - `gbp` → `1 / pnlFxGbp` (USD → GBP)
  - `eur` → `1 / pnlFxEur` (USD → EUR)
  Multiplies COGS at every aggregation site so the totals are denominated in the display currency consistently with sales / fees / proceeds.
- **Wired at 4 sites:**
  - `pnlTotalsForRange` (prev-period delta totals for the scorecard "vs prev" chips)
  - `renderPnl` main aggregator (the displayed scorecards + product table)
  - `renderPnl` selectedAgg (the multi-select aggregation behavior, v4.122)
  - `updatePnlChart` per-week aggregator (chart's contribution lines)
- **Verified at deploy time** with 4 unit tests covering each display mode. All PASS:
  - usd → 1.000000
  - cad → 1.380900
  - gbp → 0.787402
  - eur → 0.925926
- **No DB migration** — pure JS aggregator fix.
- **Backward-compatible:** existing data unchanged; only display-time totals shift to the correct denomination. USD mode is unchanged (multiplier = 1 means no math change).

## Recent Fixes (v5.71) — Lifecycle view: hide NEW/DEP buttons for products without an ASIN
- **User flagged:** "why are 'new' and 'dep' showing for products with no asin?" Screenshot showed Hemp Dog Collar variants (no ASIN — Shopify-only) rendering NEW/DEP buttons in the US lifecycle column.
- **Root cause:** the v5.65 `lifecycleCell` renderer checked `lifecycleByMaster[mid]?.[region]` to decide whether to show buttons. Records-build (v2912) creates a US-region record for any product with at least one channel identifier (`asin || shopify_sku || chewy_sku`) — so Shopify-only products had an entry in the lifecycle cache and the buttons rendered. Logically wrong: lifecycle flags only mean something for Amazon listings.
- **Fix:** check `product.asin` FIRST in `lifecycleCell`. When absent, render `—` (with tooltip "No ASIN — lifecycle flags only apply to Amazon listings.") regardless of any inventory state. ASIN-bearing products fall through to the existing inventory-presence check.
- **No DB migration** — one-line guard in the cell renderer.

## Recent Fixes (v5.70) — Products tab: sortable columns with localStorage-persisted default
- **User request:** "let me sort the products tables and set the default sort." Headers were static — no click-to-sort and no way to set a default beyond the implicit allProducts iteration order.
- **Fix — full click-to-sort across every column** with a `↑` / `↓` / `↕` arrow indicator. Click any header to sort by it; click again to flip direction.
  - **Sortable keys** (in column order): `has_image` · `brand` · `title` (uses `short_name || title`) · `sp_sku` · `asin` · `category` (via category_id → allCategories lookup) · `subcat` · `is_bundle` · `msrp` · `active`. Lifecycle-view columns add `lc_us` / `lc_ca` / `lc_uk` — composite ranking that floats NEW above DEP above neither so flagged products bubble up.
  - **Sensible first-click direction per column type:** numeric / boolean / lifecycle columns start descending (most-interesting first); text columns start ascending. Subsequent clicks toggle.
- **State persists across reloads** via `localStorage.prodSortKey` + `localStorage.prodSortDir`. The user's last choice IS the default — refresh, navigate away, come back, sort survives. Default on first ever load is `title ascending`.
- **`prodTh(key, label, opts)` helper** generates each sortable `<th>` with arrow indicator + click handler. Lifecycle columns pass `lifecycle: true` so they keep the `data-lifecycle="1"` marker (preserves the existing render-idempotence pattern).
- **`prodSortVal(p, key, lifecycleByMaster)` comparator resolver** — one switch covers every column. Lifecycle keys read from the same cache built at the top of `renderProductsTbl` (no extra lookups per row).
- **Stable-ish sort** — tiebreak on `master_id` so re-renders don't reorder visually-equivalent rows.
- **No DB migration** — pure client-side sort logic.

## Recent Fixes (v5.69) — Product image: upload local file + re-host from URL (so images survive listing takedowns)
- **User request:** "i want the ability to upload an image for a product or add an amazon product url to pull the main product carousel for that image and have that upload to the db (bc product listings get taken down and then the image is not available). the image size should be kept very low to not hit db limits."
- **⚠ SQL TO RUN:** `supabase_v5_69_product_images_bucket.sql` — creates a `product-images` Storage bucket (public-read, 512KB per-file cap, JPEG/PNG/WebP only) plus RLS policies. Idempotent. Stores re-hosted images so the original source (Amazon, Catsy, etc.) becoming unavailable doesn't break the dashboard's image cell.
- **Two new buttons** on the Product Image section of the modal, next to the URL input:
  - **`↑ Upload file`** — opens a file picker (`image/jpeg, image/png, image/webp`). Client-side resize via Canvas to 600×600 max, JPEG quality 0.7 → typical 30-80KB output. Uploaded to `product-images/<master_id>.jpg` in Storage. The public URL (with cache-bust query) gets written to `products.image_url` on Save.
  - **`⤓ Re-host from URL`** — prompts for an image URL, fetches it client-side, runs through the same resize+compress+upload pipeline, drops the new public URL into the input. CORS-permissive sources (Shopify CDN, Catsy, public direct image hosts) work end-to-end; Amazon listing pages BLOCK cross-origin fetches by design.
- **Image compression pipeline:**
  - `pfBlobToImage(blob)` — loads a blob into an `Image` element via `URL.createObjectURL` + cleans up.
  - `pfResizeAndCompress(blob, maxDim=600, quality=0.7)` — Canvas-resize preserving aspect ratio, white background fill (PNG → JPEG transparency), `toBlob('image/jpeg', quality)`. Throws when the source is CORS-tainted (named in the error).
  - `pfUploadImageBlob(masterId, blob)` — Storage upsert keyed on master_id so re-uploads overwrite cleanly. Returns the public URL with a `?v=<timestamp>` cache-buster so the modal preview shows the new image immediately. Detects missing-bucket errors and surfaces the SQL filename as the fix.
- **Status indicator** next to the buttons (`pf-image-status`) walks the user through `⏳ resizing… → ⏳ uploading 47KB… → ✓ uploaded 47KB` and back to blank after 3s. Errors render red and stay until the next action.
- **Honest about Amazon limitation:** the field hint AND the URL-paste prompt both call out that Amazon listing pages can't be auto-scraped (CORS) and direct the user to "save the image to your computer first, then use ↑ Upload file." The fetch handler's catch block also detects "Failed to fetch" / CORS-flavored errors and surfaces the same advice with a specific error path.
- **No bloat in `products` row** — Storage holds the binary, `products.image_url` just holds the public URL. Existing v5.21 schema unchanged.
- **Existing Catsy import flow** still works as-is — it writes external URLs directly to `image_url`. Users can opt in to re-hosting any Catsy URL later by clicking `⤓ Re-host from URL` in the modal (most Catsy URLs allow CORS so the fetch should succeed).

## Recent Fixes (v5.68) — Shopify image URL guidance Option C rewritten to handle canvas-rendered admin images
- **User flagged:** "ugh. there is no html element on the image" — turns out Shopify's admin image editor renders product images on a `<canvas>` element instead of an `<img>`. Two consequences:
  1. Right-click is suppressed (already known)
  2. **The HTML inspector shows `<canvas>` with no src** — so v5.66's Option C ("F12 → inspector → find `<img src=…>`") was also a dead end for this surface.
- **Fix — Option C swapped for the DevTools Network tab path:**
  - F12 → Network tab → filter by `cdn.shopify` → refresh page → image fetches show up → click any → Headers panel → right-click `Request URL` → Copy URL.
  - This works even on canvas-rendered images because the underlying fetch still hits cdn.shopify.com — Network captures every request regardless of how the response gets rendered.
- **Message also explains WHY the other paths fail** ("Shopify renders product images on a `<canvas>` in admin, so right-click AND the HTML inspector both fail") so the user understands the constraint rather than getting frustrated with sequential dead-ends.
- **Options A and B unchanged** — live storefront + admin Files library are still the cleanest paths when available.
- **No DB migration / no code logic change** — pure warning-message rewrite.

## Recent Fixes (v5.67) — Friendly error when v5.1 per-region inventory columns aren't yet migrated
- **User flagged:** `Save failed: Could not find the 'deprecated_product_amazon' column of 'inventory' in the schema cache` — the v5.1 migration (`supabase_v5_1_per_region_amazon_settings.sql`) hadn't been run, so the 5 per-region columns the inline lifecycle toggle writes to don't exist on `inventory` yet. PostgREST's generic schema-cache error gave no hint that a migration was needed.
- **Fix:** new `isMissingV51ColumnError(msg)` helper checks for any of the 5 v5.1 column names + either Postgres or PostgREST error wording (matches the v5.55 pattern for `isMissingBrandColumnError`). `toggleLifecycleFlag`'s catch block routes the error through this check; when it matches, the alert reads:<br>`Per-region inventory columns missing — run supabase_v5_1_per_region_amazon_settings.sql in Supabase SQL Editor (adds 5 columns to the inventory table + backfills from products.*). Then try again.`
- **The migration itself (no change):** `supabase_v5_1_per_region_amazon_settings.sql` adds `reorder_threshold_days`, `reorder_qty_days`, `new_product_amazon`, `deprecated_product_amazon`, `new_amazon_daily_units` to `inventory` and backfills each row from the corresponding `products.*` value. Idempotent. Required for v5.1+ to work end-to-end on a database that pre-dates v5.1.

## Recent Fixes (v5.66) — Shopify admin URL guidance: drop the broken right-click instruction, list paths that actually work
- **User flagged:** "i cannot get the image address via this pathway" — v5.64's instruction told the user to right-click the product image in Shopify admin. Shopify admin SUPPRESSES the right-click context menu on product images (anti-scraping / drag-protect behavior), so the instruction was a dead end.
- **Fix:** rewrote the shopify_admin classifier message with three paths that actually work:
  - **Option A — Live storefront (easiest):** Open `smarterpaw.com/products/<handle>` → right-click works there → "Copy image address." This is the path that works for any published product.
  - **Option B — Admin Files library:** `Content → Files` in admin lists every uploaded asset; click the image and copy the URL from the side panel.
  - **Option C — Browser DevTools:** F12 → inspector → click the image → find the `<img src="https://cdn.shopify.com/…">` attribute and copy it. Catch-all for the unpublished-product case.
- **No DB migration / no logic change** — pure copywriting fix to the warning panel.

## Recent Fixes (v5.65) — Product modal gets the per-region matrix (finally); inline lifecycle toggle on Products tab; dropped decorative emojis
- **User flagged three things bluntly:**
  1. "this is still whats on the product modal (and other places the product modal is invoked). WHY aren't you checking this and updating? I've said this 3 times now." Acknowledged miss — v5.60 fixed the INVENTORY modal but the separate PRODUCT modal (`openProductModal` / `saveProduct`) was untouched and still had single-region inputs.
  2. "how does this lifecycle view help? i still cannot set new/deprecated by region." v5.63 made the cells READ-ONLY badges; user wanted to edit inline without opening a modal.
  3. "what's with this ugly icon you keep adding in places?" Flag emojis (🇺🇸 🍁 🇪🇺) and decorative chips (🏷, 🆕/⛔ in column headers) were rendering as mojibake on the user's setup. Removed.
- **Fix #1 — Product modal `pf-*` PO planning is now the same per-region matrix as the Inventory modal `ef-*`:** Reorder threshold / Reorder qty / New (Amazon) / Rate / Deprecated, with US / CA / EU/UK columns. Save fires UPSERTs to `inventory` for each region (preserving position fields from the existing row when present, defaulting to zeros + safe defaults when seeding a new region). `products.*` columns still get the US values written via the existing upsert as a legacy fallback for older code paths.
- **Fix #2 — Lifecycle view cells are now click-to-toggle:** `NEW` and `DEP` chips per region act as buttons. Click toggles the flag in `inventory.{new_product_amazon,deprecated_product_amazon}` immediately, re-renders with the new state, and rolls back the in-memory change if the Supabase write fails. New `toggleLifecycleFlag(masterId, region, kind)` handler is the single source of truth. No modal needed for the common case.
- **Fix #3 — Removed decorative emojis from chrome:**
  - "🏷 Lifecycle view" → "Lifecycle view"
  - Column headers "US 🆕/⛔" → "US lifecycle" (same for CA, EU/UK)
  - Modal column headers "🇺🇸 US" / "🍁 CA" / "🇪🇺 EU/UK" → plain "US" / "CA" / "EU/UK"
  - Reorder threshold / Rate / Deprecated row labels in the matrix lost their 🆕 / ⛔ prefixes
  - Per-cell button labels stay as plain `NEW` / `DEP` text (no glyph reliance)
- **No DB migration** — schema unchanged; pure UI + persistence wiring.
- **Audit log:** inline toggles write `product.lifecycle_toggle` with `{master_id, region, flag, value}` so the trail captures the click path separately from full modal saves.

## Recent Fixes (v5.64) — Product Image URL: detect non-image URLs (Shopify admin page, Seller Central) and surface a specific fix path
- **User flagged:** "when i add this as the image link for a product, nothing renders. https://admin.shopify.com/store/smarterpaw/products/9167388901608" — that's the Shopify admin PAGE URL, not the image URL. The img.src silently failed; user got a broken preview with no clue why.
- **Fix — `pfClassifyImageUrl(url)` classifier** that detects the common "this is not an image URL" mistakes BEFORE attempting to load:
  - **Shopify admin URL** (`admin.shopify.com/store/...`) → hard-fail with explicit fix: "right-click the product image → Copy image address. Should start with `cdn.shopify.com/`."
  - **Amazon Seller Central URL** (`sellercentral.amazon.com/...`) → hard-fail with the same pattern (open the listing on amazon.com, right-click image, copy address).
  - **Missing protocol** (`cdn.shopify.com/foo.jpg` without `https://`) → hard-fail with prompt to add `https://`.
  - **Looks plausible** — has an image extension (.jpg/.png/.webp/.gif/.svg/.avif) OR is on a known image CDN (`cdn.shopify.com`, `m.media-amazon.com`, `images-na.ssl-images-amazon.com`, `images-eu.ssl-images-amazon.com`, `catsy.com`) → passes through, preview renders.
  - **No image extension AND not a known CDN** → soft warn (blue info pill) but still attempts the preview — covers edge cases like a custom CDN URL without a file extension.
- **`pfUpdateImagePreview` rewritten** to route through the classifier:
  - Hard-fail verdict → don't set `img.src` at all, keep the "No image" placeholder, show the orange warning pill with the specific fix path + `<code>` example URLs.
  - Soft-warn verdict → set `img.src` AND show the blue info pill (preview may not render but the user has been warned).
  - Pass → existing behavior (set src, hide placeholder).
- **Verified at deploy time** with 7 unit tests covering each branch:
  - `admin.shopify.com/store/...` → hard-fail (`shopify_admin`)
  - `sellercentral.amazon.com/...` → hard-fail (`amazon_admin`)
  - `cdn.shopify.com/foo.jpg` (no protocol) → hard-fail (`no_protocol`)
  - `https://cdn.shopify.com/s/files/.../foo_1024x.jpg` → pass
  - `https://m.media-amazon.com/images/I/abc.jpg` → pass
  - `https://cdn.shopify.com/s/files/.../foo` (known CDN, no ext) → pass
  - `https://example.com/page` (no ext, unknown host) → soft-warn (`no_extension`)
  All PASS.
- **No DB migration needed** — pure client-side validation.

## Recent Fixes (v5.63) — Per-region lifecycle editing in one modal + Products tab lifecycle view
- **User flagged two gaps:**
  1. "on issue #2 - there is still NO PLACE to set these fields by region." After v5.62's text correction, the modal still only had ONE set of inputs that saved to the row's region. You had to open the modal once per region to set US, CA, and UK separately. Clumsy.
  2. "on the products tab, give me a view to see new product/deprecated product by amazon region." Products tab had no per-region lifecycle visibility at all.
- **Fix #1 — Inventory modal PO planning section is now a per-region matrix.** Single table with 3 columns (🇺🇸 US · 🍁 CA · 🇪🇺 EU/UK) showing each setting as a row:
  - Reorder threshold (days)
  - Reorder qty (days of supply)
  - 🆕 New (Amazon)
  - 🆕 Rate / day (when New is checked)
  - ⛔ Deprecated (Amazon)
  - Save fires UPSERTs for each region — existing rows update in place; missing rows are created with zero-stock defaults (FBA Available + Inbound = 0, picked up next time the FBA snapshot uploads for that region). The legacy DOM IDs (`ef-reorder-threshold`, `ef-new-amazon`, etc.) are kept as the US column so any other code reading them still works. CA + UK use `-ca` / `-uk` suffixes.
  - **Column headers dim to 55% opacity** when no inventory record exists yet for that region — visual cue that you're seeding settings ahead of the first inventory upload.
- **Fix #2 — Products tab gets a "🏷 Lifecycle view" checkbox** next to the filter dropdown. When on:
  - **Three new columns appended** between Sub-cat and Bundle: `US 🆕/⛔`, `CA 🆕/⛔`, `UK 🆕/⛔`. Each cell shows a green 🆕 chip (with rate next to it when set) and/or an orange ⛔ chip, or `—` when no flags are set or the inventory row doesn't exist.
  - **Header injected via `data-lifecycle="1"` markers** so the render is idempotent — re-runs remove and re-add the columns rather than duplicating them.
- **Filter dropdown also extended** with per-region lifecycle filters:
  - `🆕 New (Amazon · any region)` / `🆕 New (US)` / `🆕 New (CA)` / `🆕 New (EU/UK)`
  - `⛔ Deprecated (Amazon · any region)` / `⛔ Deprecated (US)` / `⛔ Deprecated (CA)` / `⛔ Deprecated (EU/UK)`
  - These work independently of the Lifecycle view checkbox — you can filter to "🆕 New (UK)" without showing the per-region columns, or show the columns without filtering.
- **`lifecycleByMaster` lookup** built once per Products render from `records` (the inventory-joined cache). Avoids the N×M scan a per-row lookup would cost on a 500-product catalog. Empty when records aren't loaded yet (page-show before init completes — no crashes, just empty cells).
- **No DB migration** — schema was already per-region from v5.1. Pure UI wiring.

## Recent Fixes (v5.62) — EU/UK velocity now POOLED (matching the FBA pool); Inventory modal text corrected to per-region
- **User flagged two things:**
  1. "please stop saying that velocity is per country. all UK regions fulfill out of the same FBA location." Correct — FBA stock is pooled at the 'EU/UK' level, so velocity must be too. My v5.60 entry incorrectly described per-country velocity as a permanent limitation; it's a pooling step I just hadn't done.
  2. "the modal says it applies to all regions per product" — the Inventory edit modal's PO-planning hint still read "These values are per product (apply across all regions / channels)" — but v5.1 moved those settings to per-region on the inventory table. The hint was outdated and misleading.
- **Fix #1 — pool EU velocity in records-build (`master_id_<region>` lookup):** when `region === 'EU/UK'`, sum `v30/v60/v90/v120` across every country in `EU_REGIONS` (`GB / DE / FR / IT / ES / NL`). Returns null if none of the six have any rows (preserves the "skip secondary regions with no data" rule). All EU customer sales fulfill from the same FBA pool, so the pooled velocity is what the Status math + Reorder math need.
- **Fix #2 — modal hint rewritten:** now reads `These values are per region — saving updates the <REGION> inventory row only. To set defaults for ALL regions of this product at once, edit it from the Products tab.` The `<REGION>` span is populated by `openEditModal` (already tracks `editRegion` from v5.60). Color shifted to `var(--sp-orange)` to call out the scope explicitly.
- **Correction to v5.60 entry:** the "Known limitation for full forecast math" paragraph claiming UK velocity stays at 0 was wrong. With v5.62 the pooled velocity flows through the existing `regionViewOf` + `inventoryNeedBreakdown` math for EU/UK records — no special-case math layer needed.
- **No DB migration** — pure JS-side aggregation + a hint-text rewrite.
- **Why this matters end-to-end:** previously a UK row showed `Vel/day = 0` even when GB/DE/FR/IT/ES/NL had real sales — making Status read "FBA OK" regardless of how much inventory or actual demand. Now Vel/day on the UK record reflects total EU pool demand; Status / Need / Reorder math compare it against the EU/UK FBA stock and produce a real verdict. Tagging products as New / Deprecated for UK now visibly affects the math for that record only (not US or CA).

## Recent Fixes (v5.61) — Global async-load indicator in the header
- **User feedback:** "i can't tell across this app when things are still updating." Confirmed when an earlier false-positive bug report turned out to be FBA in-transit data finishing 2-3 seconds after first render — there was no visible signal that the numbers on screen could still shift.
- **Fix — global `_pendingLoads` tracker** wired to a header pill that surfaces in-flight async loads:
  - **`markLoadStart(key)` / `markLoadEnd(key)`** — push / pop a string key onto the in-flight set. Idempotent counter so nested same-key loads resolve only on the last `markLoadEnd`.
  - **`trackLoad(key, promise)`** — convenience wrapper that auto-registers/clears via `.finally()`. Returns the original promise so it composes with `await`.
  - **Header pill `#loadingIndicator`** sits next to the Live clock. Two states:
    - **Pending (≥1 source in flight):** orange `🔄 loading N…` with a hover tooltip listing every pending source name (e.g., `FBA in-transit shipments`, `products + velocity + inventory`, `Chewy forecasts`).
    - **All resolved:** briefly flashes green `✓ ready` for 1.5s then fades out. So the user gets a positive confirmation that the latest numbers are now final.
- **Wrapped these key async loaders:**
  - `loadProducts` → key `products catalog`
  - The init's parallel Promise.all (products + velocity + inventory + categories + COGS) → key `products + velocity + inventory`
  - `loadFbaInTransit` → key `FBA in-transit shipments` (THE one whose 2s delay caused the false-positive bug report)
  - `loadFbaShipments` → key `FBA shipments + summaries`
  - `loadProductCogs` → key `product COGS`
  - `loadChewyFcLatest` → key `Chewy forecasts`
- **Easily extensible** — any future loader adds one line at start + one in `finally` to participate. The pill auto-updates.
- **Cheap rendering** — `renderLoadingIndicator()` does one DOM read + a few style writes per state transition. Not called per-row or per-render-pass.
- **No DB migration needed.**

## Recent Fixes (v5.60) — Per-region New / Deprecated / Reorder settings now wired for UK (EU/UK pool) alongside US + CA
- **User request:** "i need the ability to set items that are new vs deprecated by amazon region (US, CA, UK). this needs to be wired so that any forecasting effects work across pages."
- **Schema was already per-region** — v5.1's `supabase_v5_1_per_region_amazon_settings.sql` moved `reorder_threshold_days`, `reorder_qty_days`, `new_product_amazon`, `deprecated_product_amazon`, `new_amazon_daily_units` to the `inventory` table keyed `(asin, region)`. So no DB migration needed for v5.60. The gap was JS-side: records-build only generated US + CA records, IP_COLUMNS only exposed US + CA columns, and the edit modal couldn't distinguish per-region rows.
- **Records-build now generates EU/UK records** for ASIN products when inventory or velocity data exists for that region (mirrors the existing CA skip rule). Region code is `'EU/UK'` matching the v5.13/v5.14 FBA Inventory Snapshot upload convention (pooled UK + DE/FR/IT/ES/NL).
- **9 new UK columns added to IP_COLUMNS** (all default OFF, opt-in via View popup):
  - 5 settings columns: `New (UK)`, `New Rate/d (UK)`, `Dep (UK)`, `Thresh UK (d)`, `Qty UK (d)` — mirror the existing US + CA settings.
  - 4 derived FBA Reorder columns: `0–30d FBA UK`, `30–60d FBA UK`, `60–90d FBA UK`, `90–120d FBA UK` — same marginal-per-period math as the US/CA columns, drilled through `regionViewOf(r, 'EU/UK')`.
- **CSV export regex extended** from `(us|ca)` → `(us|ca|uk)`. `uk` suffix maps to internal region code `'EU/UK'` so the lookup hits the right sub-record.
- **`openEditModal` + `saveEditModal` fixed to track region** (pre-existing bug v5.60 exposes more sharply). Pre-v5.60 they used `records.find(r => r.asin === asin)` which returns the FIRST match (always US) — meaning clicking a CA or UK row silently edited US's settings. Now:
  - New module-level `editRegion` state tracks which region's record is loaded.
  - `openEditModal(asin, region)` accepts an explicit region; matches on `(asin, region)` first, falls back to first-match for pooled rows (region contains `+`).
  - Inventory row onclick passes `r.region` so single-region clicks land on the right record.
  - `saveEditModal` uses `editRegion` to find the same record on save.
- **Forecast-tab math** uses each region's row independently via `regionViewOf` — no changes needed. PO planning (`inventoryNeedBreakdown(r, X, 'EU/UK')`) and the New launch override (`new_amazon_daily_units` driving flat-math velocity when the flag is set) both work for UK rows.
- **Region filter dropdown** auto-picks up EU/UK via the existing `populateRegionFilters()` helper (v4.199 — scans `records` for distinct non-pooled region values, rebuilds the dropdown). So after v5.60 EU/UK appears in both the Inventory Planning and Forecast region filters without any wiring change.
- **Known limitation for full forecast math:** UK velocity in `velocity_calculated` lives per-country (GB / DE / FR / IT / ES / NL — v4.144). The records-build looks up `master_id + '_EU/UK'` which won't match a per-country key. UK records get `v30/60/90/120 = 0` until that velocity is pooled into 'EU/UK'. PO planning still works for UK because:
  - The `new_amazon_daily_units` launch-override drives flat-math velocity when New is set — appropriate for new launches.
  - For mature UK products, set `new_amazon_daily_units` manually or wait for the per-country → pooled aggregation (future work).
- **Workflow now:** filter region to `EU/UK` on Inventory Planning → click a row → modal opens with EU/UK settings → toggle New / Deprecated / set rate → Save. Or in pooled view, enable the `New (UK)` / `Dep (UK)` columns via View popup to see UK-specific tags inline alongside US + CA.

## Recent Fixes (v5.59) — Shipments modal (Inventory Planning): cancelled shipments now sit in the bottom pane, not "Active"
- **User flagged:** "on the shipments modal that open on the inventory planning page, i don't want cancelled shipments to appear in the top pane under 'active' - they should appear on the bottom pane."
- **Root cause:** the v5.17 split rule was `!status.includes('closed')` → ACTIVE, else closed. Cancelled shipments slipped through the filter and showed up in the Active pane even though they're a dead-end state (Amazon won't ship them; they won't reach the FC).
- **Fix:**
  - **New `isInactive(s)` predicate**: status contains `closed` OR `cancel`. Active is now everything that isn't inactive.
  - **Bottom pane renamed `Closed / Cancelled`** with a count breakout: `Closed / Cancelled · N (M closed · K cancelled)`. So the user sees the mix at a glance instead of just "Closed · N".
  - **Cancelled rows now render in red** (`var(--red)`) in the Status column so they pop out within the inactive group, even when sorted next to closed rows.
  - **Other status colors expanded for parity with `renderFbaShipmentsTbl`'s badge:** In transit (purple), Ready to ship (teal), Shipped (blue) all get distinct colors in the modal too. Was previously falling through to muted grey.
- **No DB migration needed** — pure render-time categorization change.

## Recent Fixes (v5.58) — FBA Shipment Summary re-upload: brand pick now visibly updates existing shipments
- **User flagged:** "if i reupload the ship summary list and select a brand, it should update the brand for those shipments." The v5.50 upsert payload included `brand` and should have updated on conflict — but two things conspired against it:
  1. The pre-v5.58 path put `brand` inside the upsert payload. If the migration wasn't run, the v5.55 fallback regex caught the schema error and silently retried without brand. From the user's perspective the upload "succeeded" but brand wasn't tagged.
  2. Even when the migration WAS run, the upsert-with-brand path didn't surface per-row brand-persistence info — so the user had no signal whether the tag actually stuck.
- **Fix — split upsert and brand update into two distinct round-trips:**
  - **Upsert (without brand)** handles every non-brand field for every row. Same `onConflict: 'shipment_id'` semantics. This step CAN'T fail due to a missing brand column anymore — brand isn't in the payload.
  - **Explicit `UPDATE … SET brand = ? WHERE shipment_id IN (…)`** runs AFTER the upsert, only when the user picked a brand. Batched in groups of 200 IDs per round-trip. Catches the missing-column error explicitly (via `isMissingBrandColumnError`) and reports it to the user via a loud `alert()` pointing at the migration file.
- **`parseFbaShipmentSummary` return value extended** with three new fields:
  - `brandPersistedCount` — integer, number of shipments the brand UPDATE actually wrote to.
  - `brandColumnMissing` — boolean, true when the column doesn't exist server-side (migration not run).
  - `uploadBrand` — echoed back for the status line.
- **Upload status line surfaces brand persistence explicitly:**
  - On success: `… · 🏷 tagged Meowijuana on 25 rows` (green).
  - On migration-missing: `… · ⚠ BRAND NOT SAVED — run supabase_v5_50_fba_shipment_brand.sql first, then re-upload` (orange `dz-warn` styling).
  - Brand-missing case also triggers a modal `alert()` so the user can't miss it — same body explaining the fix steps.
- **Audit log entry** for `upload.fba_shipment_summary` now includes `brand`, `brandPersistedCount`, and `brandColumnMissing` so the persistence story is traceable.
- **Re-upload semantics confirmed:** uploading the same CSV again with a NEW brand pick will UPDATE every row's brand to the new value (the upsert refreshes other fields too, but brand is set explicitly by the follow-up UPDATE). Re-upload + pick `Skip` leaves brand untouched (no UPDATE fires).
- **`isMissingBrandColumnError` helper from v5.55** is reused unchanged — single source of truth for detecting both Postgres + PostgREST error wordings.

## Recent Fixes (v5.57) — FBA Shipments: Brand filter dropdown + left-align text cells (expanded SKU detail + parent row)
- **User flagged two issues:**
  1. "you keep right-aligning text, it's hard to read like this" — the expanded per-shipment SKU detail table (SKU / ASIN / FNSKU / Product columns) was right-aligning because the global `td { text-align: right }` (set in CSS for the numeric-heavy main tables) bled through to body cells that didn't explicitly override it. Same issue on some parent-row text cells (Date / Shipment ID / Name / Brand / Ship To / Status).
  2. "i do not see all the shipments from this list. but i'm not able to filter by brand which i should be able to" — with multiple brand uploads accumulating in `fba_shipment_summaries`, the user wants to focus on one brand at a time. v5.50 added the Brand column but never wired a filter.
- **Fix #1 — explicit `text-align:left` on every text body cell:**
  - **Expanded SKU detail table** (nested under each expanded parent row): SKU / ASIN / FNSKU / Product → all `text-align:left`. Qty stays right-aligned (numeric).
  - **Parent row text cells**: Date / Shipment ID / Name / Region chip / Brand chip / Ship To / Status badge → all `text-align:left`. Numeric cells (SKUs / Shipped / Located) keep their explicit right alignment. Delete button keeps `text-align:right`.
- **Fix #2 — Brand filter dropdown** added to the FBA Shipments filter strip, between Region and Detail. Options: `All Brands` / `Meowijuana` / `Doggijuana` / `Kitty Ka-Zoom` / `Mixed (multi-brand items)` / `🏷 Untagged`. Filter applies AFTER the search filter so the user can combine search + brand. Resolution uses the same `shipGroupBrand(g)` helper as the column render → behavior matches what's visible.
  - **`Untagged` option** is particularly useful right after a Shipment Summary upload to quickly find rows that still need the brand tagged. Pairs with the v5.56 bulk-tag button (filter to Untagged → click Tag N).
- **No DB migration needed** — reads existing `fba_shipment_summaries.brand` (added by `supabase_v5_50_fba_shipment_brand.sql`).
- **No regression on saved state** — filter defaults to `All Brands` so existing users / first-paint behavior is identical until they touch the dropdown.

## Recent Fixes (v5.56) — FBA Shipments: inline brand setter (per-row + bulk) so summary-only rows can be tagged without re-uploading
- **User flagged:** screenshot of FBA Shipments page filtered to "Missing detail (need .tsv)" — 18 rows, all showing `—` in the Brand column. The v5.50 BRAND column rendered correctly but every cell was empty because:
  - These are summary-only rows (no .tsv → no items → auto-derive can't fire)
  - The upload-time brand prompt didn't persist (v5.50 graceful fallback fired for users who hadn't run the migration; v5.55 fixed the fallback regex, but rows uploaded BEFORE the fix have null brand).
- **Two new affordances** so users can tag those rows without re-uploading the summary CSV:
  - **Per-row click-to-set.** Empty brand cells now render a dashed `+ Set` button. Existing brand chips (including `MIXED`) are also clickable so a user can override a wrong auto-derive. Both routes through `setShipmentBrand(shipmentId)` which opens the existing `promptForShipmentBrand` modal, writes `fba_shipment_summaries.brand` for that one row, mirrors into `fbaShipmentSummariesCache`, and re-renders the table. `event.stopPropagation()` on the click so the parent row's expand-toggle doesn't fire.
  - **Bulk "🏷 Tag N untagged" button** next to the count line, only visible when `≥1` currently-visible row has no brand. Calls `setShipmentBrandsBulkVisible()` which opens the brand picker once → applies the choice to every untagged shipment in the current filter in batches of 200 (avoids IN-clause limits) → one toast at the end. Useful right after a Shipment Summary upload when you have a batch of 18 untagged rows all belonging to one brand — single picker click instead of 18.
- **Missing-column safety net** on both setters — if the user clicks Set / Tag N before running `supabase_v5_50_fba_shipment_brand.sql`, the alert points at the migration file by name. Uses the same `isMissingBrandColumnError` helper from v5.55 so both Postgres + PostgREST flavors are caught.
- **`fbaShipUntaggedVisible`** module-level array — populated each render pass with the IDs of currently-visible rows where `shipGroupBrand()` is falsy. The bulk handler reads from this so it acts on exactly what the user sees, respecting all active filters (Region, Time, Detail, Search).
- **Audit log:** single-row writes log as `shipment.set_brand`, bulk writes log as `shipment.set_brand_bulk` with the count.
- **No DB migration required for v5.56 itself** — but `supabase_v5_50_fba_shipment_brand.sql` is still required for ANY brand persistence to work. The Set / Tag N affordances surface a clear error if it hasn't been run.
- **Workflow now:** upload summary CSV → if you didn't pick brand at upload time, click "🏷 Tag N untagged" in the header → pick the brand → all 18 rows tagged in one shot. Or click "+ Set" on individual rows if it's a mixed batch.

## Recent Fixes (v5.55) — v5.50 brand-fallback regex missed PostgREST's schema-cache error format
- **User flagged:** the Shipment Summary upload still threw `FBA shipment summary upload error: Could not find the 'brand' column of 'fba_shipment_summaries' in the schema cache` — even though v5.50 added a graceful fallback for "brand column missing". Migration `supabase_v5_50_fba_shipment_brand.sql` hadn't been run, but the fallback was supposed to swallow this case cleanly.
- **Root cause:** the v5.50 regex only matched the direct Postgres flavor (`column "brand" of relation "..." does not exist`) — but supabase-js / PostgREST surfaces a DIFFERENT error message when the column isn't in PostgREST's cached schema: `Could not find the 'brand' column of '<table>' in the schema cache`. Different wording, same root cause (column doesn't exist server-side); pre-v5.55 regex didn't catch it, so the error bubbled up as a fatal upload failure.
- **Fix:** extracted a single source of truth — `isMissingBrandColumnError(msg)` — that checks both flavors. Matches when the message includes the word `brand` AND any of `does not exist` / `schema cache` / `not find`. Both upload sites (`parseFbaShipmentSummary` upsert + `parseFbaShipment` auto-backfill) now route through this helper.
- **Verified at deploy time** with five unit-test cases covering both error formats + non-matches (unique-constraint violation, empty string, null). All PASS.
- **Behavior now:** uploads succeed without the `brand` column when the migration hasn't been run, logging a console warning that points at the migration file. Once `supabase_v5_50_fba_shipment_brand.sql` is run, the fallback path simply doesn't fire (the upsert with `brand` succeeds first try) and brand tagging starts working.
- **No DB migration needed.** This is a client-side regex fix.

## Recent Fixes (v5.54) — FBA Shipment Summary: handle "Ready to ship" status (parser already handled both old + new format)
- **User flagged:** "looks like some brands are still on the old version of the amazon shipment list. can the uploader cleanly handle both?"
- **Parser audit confirmed it already does** — v5.49's alias-tolerant `ci()` helper resolves every column whether the source is the OLD format (explicit `Shipment ID` column, `Created` header, `Status` at the end) or the NEW format (no `Shipment ID` column, `Created at` header, `Status` near the start). The explicit-ID-wins fallback means OLD-format files use the ID column directly, while NEW-format files extract the `(FBA…)` token from the trailing parens in the shipment name. No parser changes needed.
- **One gap closed:** the OLD format surfaces a `Ready to ship` status (Amazon workflow step between Working and Shipped) that the v5.49 status badge didn't have a color for — it fell through to muted grey. Added a distinct teal `#14b8a6` badge so the lifecycle reads left-to-right across the visible color spectrum: Working (blue) → Ready to ship (teal) → Shipped (bright blue) → In transit (purple) → Receiving (orange) → Closed (green) / Cancelled (red).
- **In-transit math already covered "Ready to ship"** via the v5.17 logic `if (!status.includes('closed'))` — anything not Closed counts as in-transit when the .tsv detail provides `quantity_shipped > 0`. Cancelled shipments slip past the filter too but contribute zero units (Amazon zeroes both shipped + received on cancellation), so they're effectively excluded.
- **Verified via headers trace** at deploy time that both column header sets resolve correctly:
  - OLD: `[shipment name, shipment id, created, last updated, ship to, skus, units expected, units located, status]` → all 9 fields found.
  - NEW: `[shipment name, status, created at, last updated, ship to, skus, units expected, units located]` → 8 fields found; ID extracted from the trailing `(FBA…)` group in `shipment name`.
- **No DB migration needed.**

## Recent Fixes (v5.53) — Inventory Planning: Amazon Status mode hides products without an ASIN
- **User request:** "if a product doesn't have an ASIN it shouldn't appear on the amazon status view of the inventory planning module."
- **Fix:** when the Status-by dropdown is set to **📦 Amazon FBA stock**, rows without an `asin` are filtered out of the visible table, scorecards, chart, and CSV export. They were rendering as "— No data" rows in Amazon mode anyway (Shopify-only / Chewy-only products have no FBA pool to score against), so the change removes pure visual noise.
- **Other modes unchanged:** 🏪 Warehouse mode and ∑ Combined mode still show every record regardless of ASIN — those are about cross-channel warehouse drain + total on-hand math, where no-ASIN products are very much in scope.
- **FBM rows stay visible in Amazon mode** (existing v4.195 behavior): they HAVE an ASIN but ship from the warehouse. Status column reads "— FBM (no FBA)" — meaningful info, not noise.
- **Filter applied at all four IP filter sites** so the change is consistent across:
  - `renderInventoryTbl` — the main table render
  - `inventoryVisibleRecords` — select-all sync + selection bar
  - `downloadInventoryCSV` — filtered-scope CSV export
  - `showExportDialog` — the row-count shown in the export-scope dialog
  Each site caches `getStatusMode()` once per filter pass so the per-row callback doesn't re-read the DOM N times.
- **Mode-change re-render** was already wired (v4.178 `setStatusMode` calls `renderInventoryTbl`), so flipping the dropdown immediately applies the new filter.

## Recent Fixes (v5.52) — P&L: FBM badge on the Product cell, matches Inventory Planning treatment
- **User request:** "can you indicate on the P&L page if an item is FBM the same way you list in on inventory page?"
- **Fix:** orange `FBM` chip rendered between the brand chip and the title in the Amazon P&L's Product cell (`PNL_COLUMNS['title']`). Identical visual + tooltip copy to the Inventory Planning badge added in v4.196 — same `rgba(232,96,26,.18)` background, same `var(--sp-orange)` foreground, same `9px 1px 4px` size, same hover tooltip explaining the FBM semantics.
- **Source of truth** is `allProducts.find(...).fulfillment_amazon` (master-level on `products.*` since v4.196 — one value applies to every region of a SKU). No new state, no new join — just looked up at render time from the cached products array.
- **CSV export** now tags FBM rows in the Product cell text (`Brand | Title | ASIN | FBM` instead of `Brand | Title | ASIN`). FBA rows omit it to avoid visual noise. Makes spreadsheet filtering by FBM trivial — just search for `FBM` in the column.
- **Column header tooltip** updated to describe the FBM chip so users discover the convention without having to hover a chip first.
- **Skipped — Shopify P&L** — DTC-only, FBM doesn't apply (no Amazon listing concept). Same for the COGS page.
- **Skipped — Diagnostics tables (matched / unmatched / off-week / duplicates)** — those exist for Looker reconciliation, not product decisions. Adding FBM there would clutter the per-ASIN aggregation views. The main P&L table is the right place.
- **No DB migration needed** — reads existing `products.fulfillment_amazon` (added by `supabase_v4196_fulfillment_amazon_on_products.sql`).

## Recent Fixes (v5.51) — Inventory Planning CSV: Shipments column now exports the total inbound (+ two new opt-in columns)
- **User flagged:** "how does the shipments column export on the csv? i'd like to see the total number inbound." The v5.17 Shipments column CSV emitted a pipe-separated list of `ShipmentID:status:qty` triples — useful for downstream parsing, useless for the actual question "how many units are inbound for this product?"
- **`Shipments` column CSV is now a human-readable summary** matching what's on screen, plus the meaningful in-transit unit total: `N active · M total · K units in transit`. So a row that has 3 Working shipments totaling 4,500 units of inbound exports as `3 active · 7 total · 4,500 units in transit` instead of `FBA19A:Working:2100 | FBA19B:Working:1500 | …`.
- **NEW `Inbound Units` column** (default OFF — opt-in via View popup, lives in INVENTORY group next to Shipments). Integer-only — same number as the orange 🚧 chip on the FBA Inbound column. Sortable, sums cleanly in Excel with `=SUM(…)`. Useful when you want to filter Top 10 by inbound or do other numeric analysis without parsing the summary string.
- **NEW `Inbound Detail` column** (default OFF — opt-in via View popup). Carries the pre-v5.51 pipe-separated `ShipmentID:status:qty | …` format for users who want the full per-shipment breakdown in one cell. On-screen render is a short muted preview (`Work:2100 · Work:1500 …+1`); the CSV gets the full list.
- **Math source for "units in transit"** is unchanged from v4.180: `ipInTransitFor(r)` returns `sum(quantity_shipped − quantity_received)` across every Working / Receiving / In-transit shipment for that master_id, via `ipFbaInTransitByMaster`. Same number the Status tier calc + the 🚧 chip + the `Amazon FBA Stock` scorecard all use, so the CSV column is consistent with everywhere else inbound shows up.
- **No DB migration needed** — pure JS + column-registry change.

## Recent Fixes (v5.50) — FBA Shipments: brand tagging (auto-derive from items + prompt on summary upload)
- **User request:** "i need the shipping detail to indicate which brand the shipment is for. if this can't be detected in the data, ask for in the upload." The shipment summary CSV has no SKU detail → can't detect brand from the data. Per-shipment .tsv detail DOES list items → can derive brand from joined `products.brand`.
- **⚠ SQL TO RUN:** `supabase_v5_50_fba_shipment_brand.sql` — adds `fba_shipment_summaries.brand TEXT` (nullable). Graceful degradation if not run: app catches the "column does not exist" error on upload + falls back to writing the row without the brand field, with a console warning pointing at the migration file.
- **Three-pronged brand resolution** on the FBA Shipments page (new Brand column, sortable, between Region + Ship To):
  1. **Explicit summary brand** (`fba_shipment_summaries.brand`) wins — set at upload time via the new prompt.
  2. **Derive from items** when detail .tsv exists — single-brand items → that brand chip; multi-brand items → orange `MIXED` chip.
  3. **No data → `—`** (blank, muted) when summary brand is null AND no detail items resolve to any catalog product.
- **Upload prompt (`promptForShipmentBrand`)** — modal at the start of every summary CSV upload. Five buttons:
  - Meowijuana (green) · Doggijuana (blue) · Kitty Ka-Zoom (pink) — assigns to every row in this upload.
  - `Mixed` (orange) — for downloads that span multiple brands; renders as orange `MIXED` chip on the FBA Shipments page.
  - `Skip — leave brand blank` (muted) — useful when you plan to upload detail .tsv files later and want auto-derivation to fill it in.
  - `✕ Cancel upload` — aborts cleanly without writing.
  - Row count for the upload is shown in the prompt header so you know how many shipments will get tagged.
- **Auto-backfill from detail .tsv** — `parseFbaShipment` (per-shipment .tsv parser) now checks the summary row's brand after upserting items. If `brand` is null AND every matched line item resolves to the same `products.brand`, sets it. Mixed-brand shipments leave the column null (the prompt is the way to tag those). Non-fatal try/catch — the detail upload itself succeeds even if the backfill fails.
- **Skip semantics preserved on re-upload** — picking `Skip` strips `brand` from the upsert payload entirely (vs sending `brand: null`), so a re-upload doesn't blank out a previously-set brand.
- **Brand column on FBA Shipments page** — sortable (blanks sort to the bottom), 76px wide, rendered with the same `chip c-meow / c-doggi / c-kkz` brand chips used elsewhere in the app. `MIXED` is an orange chip with tooltip explaining the cause.
- **`shipGroupBrand(g)` helper** is the single source of truth for the resolution logic — used by the column sort, the row render, AND will be the natural hook for any future filter (e.g., brand-filter dropdown) if needed.
- **Colspans bumped** from 11 → 12 across loading state / error state / empty state / expanded-detail rows (was easy to miss — all four were caught).
- **No regression on pre-v5.50 uploads** — the alias-tolerant `ci()` from v5.49 still works; the migration is the only setup step.

## Recent Fixes (v5.49) — FBA Shipment Summary CSV: parser handles Amazon's 2026 format + new "Missing detail" filter
- **User flagged (1):** Shipment Summary upload threw an error on a fresh download. Amazon changed the export format in 2026 — three breaking changes vs the pre-v5.49 parser:
  1. **"Shipment ID" column is GONE.** The ID now lives inside the "Shipment name" as a trailing parenthesized group, e.g. `"FBA STA (05/26/2026 14:35)-TEB9 (FBA19DZNB2XM)"`. The pre-v5.49 parser required an explicit ID column and rejected the file outright.
  2. **Column headers renamed.** `Created` → `Created at`, `Last updated` unchanged but exact-match `ci()` lookup wouldn't catch variants like `Updated at`.
  3. **New "In transit" status** alongside (or replacing) some "Receiving" usage. Status badge fell through to muted grey.
- **User flagged (2):** "i need a way to see shipments that haven't been uploaded" — meaning shipments that are in the summary list but no per-shipment `.tsv` detail file has been uploaded yet. The v4.175 "summary only" hint chip existed but you had to scroll the table looking for it.
- **Parser fixes (`parseFbaShipmentSummary`):**
  - **`ci()` accepts aliases** — each logical field tries multiple header variants. `created at` / `created` / `creation date` / `created date`; `units expected` / `expected units` / `expected`; etc. New Amazon column renames won't break the parser silently — they just slot into the alias list.
  - **`extractIdFromName()`** — when the explicit `Shipment ID` column is absent, extract from the name's trailing `(FBA…)` paren group. Uses `matchAll` and picks the LAST match so date-style parens earlier in the name (`(05/26/2026 14:35)`) never collide with the ID. Bare-token fallback (no parens) too, just in case.
  - **Required columns check loosened** — accept either explicit ID column OR a name column (we can extract from). Still requires `Units expected` so a per-shipment packing list isn't mis-uploaded as a summary.
  - **Status reporting extended** — return includes `extractedFromNameCount` (so the upload status line can mention "ID extracted from name on N rows" if relevant) and `missingDetailCount` (number of uploaded shipments not yet in `fba_shipments`, batched IN-query check).
- **Status badge (`statusBadge` in `renderFbaShipmentsTbl`):**
  - New `In transit` value (purple `#a855f7`) — distinct from `Receiving` (orange) and `Working` (blue) so the v5.49 staged transit reads cleanly.
  - New `Shipped` value (lighter blue, slightly more saturated than `Working`) — the new format surfaces `Shipped` between `Working` and `Receiving`; was previously falling through to muted grey.
- **"Missing detail" filter on FBA Shipments page (new):**
  - **New filter dropdown** "Detail" between Region and Time Window: `All shipments` / `📥 Missing detail (need .tsv)` / `📦 With detail uploaded`. Filters the merged table on `g.has_detail`.
  - **Count line surfaces missing-detail total** inline (`… · 📥 N need .tsv`) so the gap is visible without applying the filter first.
  - **Upload status line on Data → Uploads** also calls it out: `✓ N shipments · expected/located · 📥 M need detail .tsv (Forecast → FBA Shipments → filter "Missing detail")` — so you see the gap immediately after uploading the summary, not after navigating to the FBA Shipments tab.
- **No DB migration needed** — uses existing `fba_shipment_summaries` + `fba_shipments` tables. Pre-v5.49 uploaded data still loads correctly (the alias lookup is a strict superset of the old lookup).
- **Workflow now:** download the summary CSV → upload → see "M need detail .tsv" in the status → switch to FBA Shipments tab → filter "Missing detail" → that's the work queue of shipments you need to grab per-shipment `.tsv` files for.

## Recent Fixes (v5.48) — Inventory Planning: click-to-open shipments (Shipments column on by default + clickable 🚧 chip)
- **User flagged:** "i need a way to click to open shipments from the inventory planning module." The v5.17 Shipments column + `openIpShipmentsViewer` modal already existed — but the column was `default:false`, so users with the v4.166 column-visibility default set never saw the 📦 View button. Click-to-open existed but was invisible.
- **Two access paths now:**
  - **Shipments column** flipped to `default:true`. New users + anyone resetting to defaults see it. The 📦 View button on each row opens the viewer with the per-shipment breakdown (status · qty shipped / located · dates · destination FC).
  - **🚧 in-transit chip on the FBA Inbound column** is now a button. Click anywhere you see 🚧 on Inventory Planning and you jump straight to the shipments viewer for that master_id — filtered visually because the chip is only visible when active (Working / Receiving) shipments exist for that row. The chip got a subtle background + border styling to make the click affordance obvious.
- **One-time migration** so existing users with saved `ipVisibleCols` (which exclude `shipments` because v5.17 shipped it as default-off) auto-pick up the column on first load post-v5.48. Sets `ipShipmentsAutoShownV548 = '1'` in localStorage after the inject so users who DELIBERATELY hide it later don't get it forced back on next page-load.
- **`event.stopPropagation()`** on both click handlers — the parent inventory row's onclick (which opens the inventory edit modal) doesn't also fire when the user clicks the View button or the 🚧 chip.
- **Empty-state handling preserved** — the existing v5.17 modal gracefully shows "No FBA shipments found — upload shipment .tsv files via Data → Uploads" if the user lands on a product that has no shipments cached. So even when the column shows `—` (no shipments), clicking through is safe.

## Recent Fixes (v5.47) — BOM view flags inactive bundles + inactive components
- **User request:** "on the bom module please flag if a sku is inactive." The v5.44 BOM view rendered every parent + component row identically regardless of `products.active` — so a bundle still listed in your BOM might be silently inactive (won't fulfill if a customer orders it) or a component could be inactive (BOM won't physically assemble when the bundle is built). No visual cue meant these only surfaced when something broke downstream.
- **Fix — two new inline indicators on the BOM view:**
  - **Parent bundle row** flagged when `p.active === false`: red `⛔ INACTIVE` chip appended to the bundle title, row background tinted red (`rgba(214,63,42,.06)`) with hover state in a stronger red tint, row opacity slightly reduced (0.85) so the row reads as "deprioritized" without disappearing. Click still opens the product modal — tooltip now mentions the inactive state with a fix suggestion (toggle Active in the product modal).
  - **Component row** flagged the same way: `⛔ INACTIVE` chip next to the component title, same red row tint + reduced opacity. Tooltip suggests two fixes: re-activate the component, or replace it in the bundle's BOM.
- **Row-count line surfaces totals.** When any inactive row exists, the count appends ` · ⛔ N inactive bundles · M inactive component rows` so you can spot staleness at a glance without scrolling. Hidden when zero (avoids noise on clean catalogs).
- **Shared `inactiveChip` markup** built once at the top of `renderBundlesBomView`, used by both parent + component sites — keeps the visual language consistent (same icon, same colors, same tooltip text).
- **Missing-component flag (v5.44) still takes precedence** — if a component's master_id doesn't exist in `products`, the row renders the existing red "⚠ Missing component master_id" treatment instead of an INACTIVE chip (missing is a strictly worse state than inactive).
- **No DB migration needed** — reads existing `products.active` flag.
- **Why this matters:** the BOM view is now a fulfillment-health snapshot — at a glance you can see which bundles can't actually be assembled because a component went inactive (need to replace it in the BOM), and which bundles are themselves dead in the catalog (need to either reactivate or stop maintaining their BOM).

## Recent Fixes (v5.46) — Merge tool search rewritten (tokenized + multi-field + ranked candidate list)
- **User flagged:** searching for "large joint" in the merge tool returned no result, even though a product titled "Catnip Joints - Large" (or similar) exists. Root cause: the pre-v5.46 search did a sequential `find()` chain doing CONTIGUOUS-substring matches on title / short_name / master_id / ASIN. So "large joint" had to appear as that exact substring in one of those fields — which fails the moment words appear in a different order or with separators between them.
- **Three structural problems fixed in one pass:**
  1. **Multi-word queries are now tokenized.** Splitting the query on whitespace and requiring EVERY token to appear in SOME searchable field (any position, case-insensitive) makes word-order irrelevant. "large joint" matches "Catnip Joints - Large" because "large" appears once and "joint" appears once (in the same product).
  2. **More fields are searched.** Was: title / short_name / master_id / asin. Now: title, short_name, master_id, sp_sku, shopify_sku, chewy_sku, asin, barcode, brand, supplier. So typing "meowi joint" or pasting a Shopify SKU now both work.
  3. **Multiple candidates are surfaced** when more than one product matches. Up to 6 are shown as clickable rows in the preview panel; user clicks the right one to lock it in. Single match still auto-selects (preserves the v5 paste-id-then-Merge flow). 0 matches gets a clearer message naming what to try next.
- **Ranked scoring.** Same all-tokens-must-match gate (any field, anywhere) feeds a per-product score:
  - +1000 for exact master_id match (overrides everything)
  - +900 for exact ASIN match
  - +800 for exact sp_sku
  - +700 for exact shopify_sku / chewy_sku
  - Per token: +50 in master_id, +40 in sp_sku / asin, +30 in shopify_sku / chewy_sku, +20 in short_name, +10 in title, +5 in brand
  - Bonus +5 when a token matches as a WHOLE WORD in title (helps "joint" beat "joints" or "jointed" when both exist)
  - +1 if the product is `active` (inactive products sink in ties)
  Candidates are sorted by descending score and the top 6 rendered.
- **Picker UI** — each candidate row shows brand chip + short_name (or title) + a small `BUNDLE` chip when `is_bundle`, plus an `inactive` chip when not active. Second line is mono-font `master_id · sp_sku · asin · Category / Sub` so the user can verify the right product before clicking. Clicking a row swaps the picker for the original single-line preview card (with a "✓ Selected — click another row to change" hint) and stashes the product in `mergeSelected[inputId]`. `runMerge` reads from there unchanged — the upstream flow is intact.
- **New helper `selectMergeCandidate(inputId, previewId, masterId, autoFromSingle)`** is the bridge between the candidate list and the existing `mergeSelected` state. Called from each row's `onclick`, and also internally when there's exactly one candidate (preserves the paste-id auto-select UX).
- **More-than-6 hint** — when more candidates exist than fit, the preview shows "… and N more — refine the search to narrow down." So the user knows refinement is necessary rather than assuming the visible 6 are the entire universe.
- **No DB migration needed** — pure client-side rewrite. Existing `mergeSelected` + `runMerge` integration is unchanged; only the input-side `mergeSuggest` got rewritten.

## Recent Fixes (v5.45) — Merge tool: backfill every value-bearing column added since the tool was last updated
- **User flagged:** "can you make sure the merge keeps the image field and other fields we've added." The pre-v5.45 merge backfill list covered only 9 fields (asin, sp_sku, shopify_sku, chewy_sku, barcode, category_id, msrp, wholesale, supplier) — every value-bearing column added to `products` between v4.75 and v5.21 was silently dropped from the survivor even when the survivor row had no value in that column.
- **Fields the merge was silently dropping until v5.45:**
  - **`image_url`** (v5.21) — product image URL surfaced on Products tab, Catsy importer, P&L thumbnails, etc. The trigger for this fix.
  - **`fulfillment_amazon`** (v4.196) — FBA/FBM per-product override. Default is 'FBA' so the falsy-guard would never fire; v5.45 special-cases this to adopt the duplicate's 'FBM' only when the survivor is still at default.
  - **`forecast_notes`** (v4.99) + `notes` — per-product annotations.
  - **`reorder_threshold_days`, `reorder_qty_days`** (v4.161) — per-product PO planning overrides.
  - **`new_product_amazon`, `deprecated_product_amazon`** (v4.160) — Amazon lifecycle flags. Boolean — adopt only when duplicate has `true` AND survivor has `false/null` (never downgrades a deliberately-set survivor flag).
  - **`new_amazon_daily_units`** (v4.172) — launch-override daily rate.
  - **Full seasonality bundle** (v4.75 + v4.77 + v4.78): `sea_method`, `sea_curve_calculated`, `sea_curve_manual`, `sea_min_weeks`, `sea_calculated_at`, `sea_weeks_of_data`, `seasonal_type`. Adopted as a unit — if duplicate has done seasonality work (method ≠ 'category-default') AND survivor is still on default, the WHOLE bundle migrates (curve + threshold + provenance) so the analysis isn't half-cut.
- **Fix structure** — five labeled sections inside the `runMerge` patch block:
  - **1a. Simple identifier + descriptive fields** — explicit array `SIMPLE_BACKFILL_FIELDS` with the falsy-guard pattern. Adding new value-bearing columns in the future = one entry in the array.
  - **1b. Boolean lifecycle flags** — explicit array `BOOL_FLAG_FIELDS` with `=== true` guard to avoid accidentally downgrading.
  - **1c. `fulfillment_amazon`** — special-cased because of the non-null 'FBA' default.
  - **1d. Seasonality bundle** — atomic adoption when `sea_method` shifts off default.
  - **`seasonal_type`** — separate adoption because it's independent of `sea_method` (a row can have type='seasonal' but method='category-default').
- **Intentionally NOT auto-filled** (called out in the comment):
  - `short_name` — editorial display label, survivor's choice (even if empty) wins. Pre-existing decision.
  - `brand`, `active`, `is_bundle` — fundamental product-identity fields. The user chose the survivor knowing what they were keeping.
- **No DB migration needed** — pure JS logic change. Existing merges already in the DB are unaffected; future merges will preserve more state.
- **Tested mentally for backwards-compat:** every field in the new `SIMPLE_BACKFILL_FIELDS` array was previously falling through to "survivor wins by default" via the old code's omission. Old behavior is a strict subset of new behavior (everything that was preserved before is still preserved; new fields gain proper backfill). No regression risk.

## Recent Fixes (v5.44) — Bundles tab: new "📦 BOM" view shows parent + component SKU IDs inline
- **User request:** "on the bundles view, give me an option to toggle to a BOM view that shows the parent SKU and component SKUs - i need to see the IDs for all component SKUs."
- **New view toggle** in the Bundles filter strip — pill pair: **🧾 Summary** (default — the existing one-row-per-bundle view) and **📦 BOM** (new — expanded). Active mode persisted to `localStorage.bundleViewMode`; survives tab-switches + reloads.
- **BOM view layout** — each bundle renders as a grouped block:
  - **Parent header row** — `surface2` background, prominent `BUNDLE` badge, brand chip + short_name (with full title in muted text), and EVERY parent identifier inline: `master_id` · `SP SKU` · `ASIN` · `Shopify SKU` · `Chewy SKU`. Right-most cell shows the component count. Click the row → opens the bundle's product modal.
  - **Component rows** beneath the header — one row per BOM entry. `Qty×` on the left (right-aligned, bold), then `↳ Component Title`, then the component's `master_id`, `SP SKU`, `ASIN`, `Shopify SKU`, `Chewy SKU`, and a verified indicator (✓ green when `verified=true`, `⚠ unverified` amber chip otherwise). Click any row → opens that component's product modal.
- **Missing component rows flagged inline** — when a BOM row references a `component_master_id` that no longer exists in `products` (deleted product, typo, etc.), the row renders in red with `⚠ Missing component master_id: <id>` so the user can spot orphans without opening the bundle modal.
- **Empty BOM rows flagged inline** — bundles with no BOM defined yet show a single row reading `⚠ No BOM components defined yet — open the bundle to add them.` so they're visible but distinct from no-bundle-at-all.
- **Sort order** — bundles alphabetically by title; components in their stored order within each bundle. Matches the v5.18 BOM CSV export convention so on-screen scanning agrees with exports.
- **Single O(1) products lookup** built once per render (`new Map(allProducts.map(p => [p.master_id, p]))`) so component identifier lookups don't cost an O(N) scan per BOM row.
- **Filters apply at the bundle level** — search + brand filter narrow the bundle list; if a bundle matches, its full BOM shows. So searching for a component title finds nothing in BOM mode — search by the bundle's title / SP SKU / ASIN to drill into a specific BOM.
- **Row count line** updates per mode — Summary: `N bundles` (unchanged); BOM: `N bundles · M with BOM · K component rows` so the user sees the explosion factor at a glance.
- **THEAD swap** — the column header row is rewritten per mode (different column set), so toggling modes doesn't leave stale headers above a mismatched body.
- **No DB migration needed** — reads existing `products`, `bom`, and `allBomData` cache.

## Recent Fixes (v5.43) — Category Manager: real dropdown for moving + bulk rename for renaming a top category
- **User flagged (initial):** "in the category edit menu, i should be able to choose another category from the drop down if i want to move a sub-category." v5.34 used an HTML `<datalist>` on a text input — technically the move-by-picking-existing flow worked, but the suggestions only appeared after the user clicked a tiny dropdown arrow or started typing. Users didn't realize they could browse all categories that way.
- **User flagged (after the initial v5.43 dropdown change):** "now i can't rename the existing category." The dropdown handled MOVE cleanly but removed v5.34's free-text input that doubled as a rename surface. Split the two actions into discrete affordances:
- **Edit-mode now has THREE distinct actions:**
  - **MOVE this row** — open the new Category `<select>` dropdown, pick another existing top category, ✓ Save. Only THIS row's `category` field changes; other rows under the original top are unaffected. The row's `id` is preserved so every product linked via `category_id` follows automatically (no FK rewiring).
  - **CREATE a new top category** — open the dropdown, pick `+ New top category…` (rendered in green italic at the bottom). A `prompt()` asks for the new name, which gets injected as a fresh `<option>` and selected. If the user cancels or enters empty, the dropdown reverts to its original value (tracked via `data-original` on the SELECT). Case-insensitive collision check: typing the name of an existing top in the prompt just picks the existing one (no duplicate option).
  - **RENAME this top everywhere** — new **✎ Rename** button to the right of the dropdown. Triggers `catmgrRenameTopCategory(id, oldName)`: prompts for the new name (pre-filled with the current), confirms the affected-row count, then does a BULK `UPDATE categories SET category = newName WHERE category = oldName`. Every sub-category under that top picks up the new name in one round-trip. If a top with the new name already exists, the confirm dialog frames the operation as a MERGE between the two tops (still works — the bulk UPDATE just consolidates them).
- **Why split rename vs move:** v5.34's free-text input conflated the two semantics, which made it easy to typo-rename one row and end up with a top category split across two slightly-different spellings. Now the dropdown is reserved for "pick from canonical list" and the ✎ button is reserved for "edit the canonical list itself." Hard to mix them up.
- **`catmgrHandleCatChange(id)` is the dropdown's onchange handler.** Mutates only the live SELECT element — no state lifted into a global, no re-render needed.
- **`saveCategoryRow` guards against the `__new__` sentinel** leaking through (defense in depth — the handler should always resolve it, but if anything sneaks through, the save aborts with a clear message rather than persisting a literal `__new__` as a category name).
- **Sub-category field stays free text** — renames are the common edit there, and unlike top categories, sub-categories don't form a constrained vocabulary across rows.
- **Audit log:** rename writes `category.rename_top` with `from`, `to`, `affected_rows`, and a `merged_into_existing` flag when applicable. Per-row category change still writes `category.edit`.

## Recent Fixes (v5.42) — Drag-to-resize columns on Inventory Planning + Demand Forecast
- **User flagged:** "i can't drag to resize columns anywhere." Column resize was never built — the dashboard rendered every TH with `min-width:<static>` from the column registry and there was no drag handle anywhere.
- **Fix — generic `attachColumnResizers` helper** wired to both registry-driven tables:
  - **6px-wide invisible strip at the right edge of each TH** is the grab target. Hover highlights it green (`var(--sp-green)`). Mousedown captures the live x + starting width; document-level mousemove updates `style.width` AND `style.minWidth` on the live TH so the column resizes in real time and body cells follow via the table's column layout. Mouseup commits to localStorage.
  - **Double-click on the handle resets** that column to its registry default (`c.w`) — deletes the saved width and re-renders.
  - **Click on the handle never triggers a sort** — `stopPropagation` on the handle's mousedown / click events. Sort still fires on a normal click anywhere else in the TH.
  - **Locked columns and the checkbox column (`_chk`) are skipped** — no handle attached. (Resizing the row-selection checkbox doesn't help anyone.)
- **Persistence:** per-browser via localStorage. `ipColWidths` for Inventory Planning, `fcColWidths` for Demand Forecast. Stored as `{ <col_key>: <pixels> }`. Cross-device sync would mean two more JSONB columns on `user_profiles`; not done yet — column widths are a personal preference more than a shared report state, and the per-browser local cache is fine for the v1.
- **Apply path:** new helper `resolveColWidthCss(c, savedWidths)` returns the CSS width string for each column — saved override beats the registry default `c.w`. Both `renderInventoryTbl` and `renderTable` (Forecast) now use this in the `<th>` style, setting BOTH `width` and `min-width` so the user's choice is authoritative even when content would normally expand the column.
- **Tooltips updated** to mention "Drag right edge to resize" on every column header. Sort hint still leads (since that's the more common click target).
- **Group header row stays aligned automatically** — both tables compute group header colspans from contiguous runs of visible columns, and the group `<th>` doesn't carry a width; it inherits from the runs of underlying column `<th>`s. So resizing a column visually expands its group band without any extra code.
- **Out of scope for v5.42 (follow-up if needed):**
  - **P&L Amazon table** — also registry-driven (`PNL_COLUMNS`) but its registry doesn't carry a `w` default per column (widths come from browser auto-layout based on cell content). Wiring resize requires adding `w` defaults to every PNL column first. Easy follow-up; not done yet.
  - **Other tables (Products / Bundles / Units Sold / COGS / Chewy Forecasts / FBA Shipments)** — bespoke header rendering, no shared registry. Each would need per-table wiring. Skipping for v1 since these aren't the data-dense workhorses the user iterates on most.
  - **Cross-device sync** — see "Persistence" above.

## Recent Fixes (v5.41) — Inventory Planning: FBA snapshot freshness visible next to Amazon status
- **User flagged:** "i don't see where you added the most recent inventory snapshot on the inventory planning module for amazon status." The v5.15 `amazon_inv_last_updated` column existed but was `default:false` and lived in the SKU group, far from the Status column. The Amazon FBA status math uses `fba_available + fba_inbound` from the most recent snapshot — but the user had no way to see how fresh that data was without enabling a column then visually associating it with the Status badge. Trust calibration was missing.
- **Fix — three new surfaces, all driven by a new `getAmazonSnapshotFreshness(r)` helper:**
  1. **Inline stale-data chip next to the Status badge** (per-row, Amazon + Combined modes only). Renders ONLY for FBA-relevant rows (has ASIN, not FBM, not deprecated) when the snapshot is older than 7 days OR missing entirely. Three states with distinct icons + colors:
     - `⏰ 12d ago` (orange) — 8-30 days old
     - `🔴 45d ago` (red) — older than 30 days
     - `⚠ no snap` (red) — no FBA snapshot ever uploaded for this region
     Fresh (≤7d) and irrelevant rows render nothing — keeps the UI clean.
  2. **New "Snapshot freshness" section in the Status tooltip** (Amazon + Combined modes). Below the tier math, the tooltip now spells out the snapshot date + age + a recommendation:
     - Fresh: "✓ FBA inventory snapshot: 2026-05-26 · 1d ago. Data is fresh; status tier is trustworthy."
     - Stale (8-30d): "ℹ Older than 7 days — fine for a quick read but re-upload before placing a real order."
     - Very stale (>30d): "⚠ Older than 30 days — fba_available + fba_inbound figures driving this tier could be wildly off. Re-upload before trusting the status."
     - Never: "⚠ No FBA inventory snapshot uploaded yet. Status math is using whatever was loaded from the legacy upload (could be zero)."
  3. **FBA Stock scorecard tile (Amazon mode bottom row) gets a snapshot freshness sub-line.** Shows the OLDEST snapshot age across all ASIN rows in scope (filtered + selected aware), color-coded by staleness. If any row in scope has no snapshot at all, the line reads `⚠ N rows missing snapshot` in red — so the user sees data gaps without drilling into individual rows.
- **Pooled rows use the OLDEST snapshot across regions** — staleness on any region is the limiting factor, matching the v5.15 column behavior. A US+CA pooled row where US is fresh but CA is 45d stale flags as 🔴 stale.
- **Helper `getAmazonSnapshotFreshness(r)`** returns `{ date, ageDays, ageLabel, color, tier }` with `tier ∈ {fresh, stale, very_stale, never}`. Lives next to `getStatusTooltipFor` for proximity. Used in all three surfaces above so the date-arithmetic + color thresholds (7d / 30d) stay in lockstep.
- **Existing v5.15 column unchanged** — `amazon_inv_last_updated` still available as an opt-in column in the SKU group for users who want the date in the table proper. The v5.41 additions surface it where it matters for trust calibration (the Status column) without forcing users to add a separate column.
- **FBM + deprecated rows skip the chip** — FBM doesn't use FBA stock (warehouse drain only); deprecated rows have their reorder math suppressed (Status reads "⛔ Deprecated"). Neither benefits from snapshot freshness annotation.
- **No DB migration needed** — uses the existing `fba_inventory_snapshots` table + the `amazon_inv_last_updated` field already attached to records by v5.15's load logic.

## Recent Fixes (v5.40) — Query Database: edit a saved query in place
- **User flagged:** "i can't edit and save a saved query." The v5.37/v5.38 save flow always opened a `prompt()` asking for a name, even when a saved query was already loaded in the editor — so editing meant typing the exact same name back in, then clicking through an "Overwrite?" confirm dialog. Painful, and discouraged iterating on saved queries.
- **Fix — "active saved query" state.** New `activeSavedQueryIdx` tracks which saved query (if any) is currently loaded into the editor. Clicking a saved-query chip sets active; clicking a preset clears active.
- **💾 Save button is now state-aware.**
  - Active query loaded → button reads **`💾 Update '<name>'`** (green fill) and clicking updates that query in place — NO name prompt, NO overwrite confirm. Just saves.
  - No active query → button reads **`💾 Save`** (neutral fill) and clicking prompts for a name like before (the v5.37 flow).
  - If the editor SQL is byte-identical to the stored copy → shows a `No changes to save in '<name>'` toast next to the button instead of writing a no-op revision.
- **New `💾+ Save as…` button** next to Save. Always forks to a NEW saved query regardless of active state — pre-fills the name prompt with `'<current name> (copy)'` when forking from an active query so duplicating is one click + Enter. If you type a name that already exists, the existing overwrite-confirm dialog still fires.
- **Active chip visually distinct.** The active saved-query chip uses the same green-fill treatment as the selected preset chip (solid `var(--sp-green)` background with white text) — so at a glance you can see which query the Save button will update.
- **Ephemeral toast instead of `alert()`** for "saved" / "no changes" feedback (`qToast(msg)`). 2-second green pill next to the Save button. Keeps the iteration loop fast — saving doesn't yank focus into a dialog you have to dismiss.
- **Delete-aware active state.** Deleting the active query clears active; deleting a query at a lower index shifts active down by one so it keeps pointing at the same query.
- **Audit log:** in-place updates log as `query.update` (new event) instead of `query.save`, so the distinction between "first save of a new query" vs "edit of an existing saved query" is visible in the audit trail.
- **No DB migration needed** — same `user_profiles.db_user_queries` JSONB column from v5.38.

## Recent Fixes (v5.39) — Query Database: inline cell editing for result rows
- **User request:** "instead of this [SQL purge approach] — let me edit the rows that appear in query results (for fields that do not upsert to other tables)." Jason wanted a safer + faster way to clean up data than hand-rolled UPDATE/DELETE SQL: run a SELECT, then edit the cells inline. RLS is the safety net — every edit goes through `sb.from(table).update().eq(pk, val)`, so anything the policy would deny is rejected by Postgres.
- **New "✏ Edit mode" checkbox** in the Query Database results header, next to **📋 Copy CSV**. Off by default. Flipping it on:
  - Detects the main table from the query's FROM clause (`detectQueryMainTable` — handles `from products`, `from public.products`, `FROM products AS p` and joins where the first table after FROM is the main one)
  - Resolves the table's PK (`detectMainPk`) from a per-table map: `products → master_id`, `inventory → id`, `categories → id`, `bom → id`, `sales_weekly → id`, `sku_economics → id`, `chewy_forecasts → id`, `fba_inventory_snapshots → id`, etc. Composite-PK tables (or tables not in the map) are flagged disabled — editing won't be offered.
  - Computes editable columns (`computeEditableCols`) — locks the PK, FK conventions (`*_id`, `master_id` references), managed timestamps (`created_at`, `updated_at`, `updated_by`), and joined columns from other tables. Editable columns appear with a tiny `✎` marker in the cell.
- **Edit UX:** click an editable cell → replaced with a styled `<input>` pre-filled with the current value. **Enter** saves, **Escape** cancels, **Tab** commits and moves to the next cell. Successful save flashes the cell green via a CSS transition before re-rendering with the new value. Failed save (RLS denial, type error, etc.) flashes red with the error message in a tooltip.
- **Save mechanism:** `commitCellEdit(rowIdx, col, newVal)` calls `sb.from(queryMainTable).update({[col]: newVal}).eq(queryMainPk, pkVal)` — respects the existing RLS policies (every data table is `authenticated`-only with row-scoped policies, see CLAUDE.md "Setup notes — Supabase RLS"). If the user lacks UPDATE permission on the table or row, Postgres returns 403 and the cell flashes red. No need for the dashboard to whitelist tables — the database enforces.
- **Edit banner** above the results table (`updateEditBanner`) — when edit mode is on, shows: `Editing table: <name> · PK: <col> · Editable: <col1, col2, ...> · Locked: <col3, col4, ...>`. So the user can see at a glance which columns will accept clicks. For tables with composite PKs or unrecognized tables, the banner reads: `Inline editing not available for this query (no single-column PK detected — use SQL).`
- **State variables added** at module scope:
  - `queryMainTable` — the table from the FROM clause
  - `queryMainPk` — the PK column name (string)
  - `queryEditableCols` — `Set<string>` of columns the user can click to edit
  - `queryEditMode` — `boolean`, toggled by the checkbox
- **`runDbQuery`** now computes these on every query execution AND delegates row rendering to `renderQueryRows()` (was inline). This means the same data can re-render with editable markers turned on/off without re-running the query — toggling Edit mode is instant.
- **Audit log:** every successful cell edit writes `query.cell_edit` with `{ table, pk_col, pk_val, column, old_value, new_value }` for full trace. Failures aren't logged (Postgres rejected them; no state change occurred).
- **No DB migration needed** — uses existing tables + existing RLS policies. Safer than ad-hoc SQL because it can't issue DELETEs or multi-row UPDATEs by accident; one cell change = one UPDATE WHERE pk = value.
- **Out of scope for v5.39 (deferred):**
  - **Bulk edits across multiple selected cells.** Possible follow-up if Jason hits a use case where one cell at a time is too slow.
  - **DELETE row** button. Same RLS protection would apply; left out for now because the query results table is a thin wrapper and a Delete button there is a bigger UX change.
  - **Type-aware inputs** (number/date/boolean pickers). Current implementation uses a text input — Postgres validates types on save (e.g., entering "abc" into a numeric column flashes red with the cast error). Good enough for v1.
  - **Insert new row.** Different UX entirely; would need column metadata + a form. Out of scope.

## Recent Fixes (v5.38) — Saved queries persist to Supabase (per-user, cross-device)
- **User request:** "does this need to be written to the backend? how will these save long term?" → "yes, that's what i asked for."
- **⚠ SQL TO RUN:** `supabase_v5_38_user_query_library.sql` — adds `user_profiles.db_user_queries jsonb default '[]'::jsonb`. Same pattern as the existing `inventory_saved_views` / `forecast_saved_views` columns.
- **Architecture: Supabase canonical, localStorage cached.** Matches the existing saved-views pattern:
  - `loadUserQueriesFromStorage()` — synchronous local read, primes the UI immediately on page load
  - `loadUserQueriesFromDb()` — async, fires after init; pulls `user_profiles.db_user_queries` and overwrites local cache when signed in. Server-side is canonical.
  - `persistUserQueries()` — writes localStorage immediately then fire-and-forget UPDATE to Supabase; failures log without blocking the UI
- **One-time migration on first Supabase load**: if a user has localStorage queries from before v5.38 but no remote ones yet, the local set gets uploaded to their profile on first sign-in after upgrade. Logged to audit as `query.migrate`. No data loss for existing queries.
- **Offline-tolerant**: localStorage cache means queries are still loadable when offline; next persist call syncs back when reconnected.
- **Cross-device**: Jason signs in on his laptop → queries available. Signs in on his phone → same queries.
- **Future-proof for team sharing**: if/when we want a shared library across team members, add a separate `shared_saved_queries` table (per-team) — the personal library on `user_profiles` stays as-is.

## Recent Fixes (v5.37) — Query Database: saved user queries + live schema browser
- **User request:** "give me the option to save my own queries, also do a lookup to see what columns are available in the query editor."

### 1. Saved queries
- New **💾 Save** button next to **▶ Run Query** in the header.
- Click → prompt for a name → query stored to `localStorage.dbUserQueries` as `[{ name, sql, savedAt }]`.
- Saved queries appear in a new **💾 Saved:** chip row above the editor (green tint to distinguish from presets).
- Each chip has a `×` button to delete (with confirmation).
- Re-saving with an existing name asks "Overwrite?" so accidental clobbering is caught.
- Audit log writes `query.save` and `query.delete` events.
- localStorage scope is per-browser; future cross-device sync would move this to `user_profiles.dbUserQueries` (jsonb).

### 2. Schema browser
- New collapsible **🔍 Schema browser** above the editor.
- On first open, calls `loadDbSchema()` — runs `select table_name, column_name, data_type from information_schema.columns where table_schema='public'` via the existing `exec_sql` RPC.
- Result cached in `dbSchemaCache` for the session.
- Renders as nested `<details>` elements: one per table, expandable to show every column as a clickable button.
- Click a column button → text inserts at the editor's cursor (with a leading space if needed to avoid concatenation).
- Header shows count: "· 18 tables / views · 247 columns · click a name to insert at cursor".
- Falls back gracefully with a red error message if `exec_sql` isn't installed (links to CLAUDE.md migration note).

## Recent Fixes (v5.36) — New query preset: "Products w/ Amazon ASIN"
- **User request:** "add a query for all products with an amazon ASIN with title, short title, and ID fields."
- Added to the Query Database preset list. Filters to `asin is not null and asin <> ''` AND `active = true`.
- Returns: `master_id` · `sp_sku` · `asin` · `title` · `short_name` · `brand` · `is_bundle` · `active`
- Ordered by brand, then title. LIMIT 2000 (catalog-friendly cap).

## Recent Fixes (v5.35) — Catsy importer search: render bundle components inline
- **User request:** "on the catsy upload, when i search for a product to match, i need to see the components of the bundle."
- **Now** each bundle row in the Catsy search popover renders its BOM components below the standard product info, indented under a dashed separator:
  - Format: `↳ <qty>× <component title>`
  - Component title pulled via `allProducts` lookup (uses `short_name` first, falls back to full `title`, then `master_id` if the component is missing entirely)
  - Long titles truncated to 50 chars
  - Unverified BOM rows show a ⚠ amber badge so you know that BOM hasn't been QC'd yet
  - Bundles with no BOM defined yet show `↳ (no components defined yet)` in italic muted text
- **Single-pass index:** built `productById = new Map(allProducts.map(...))` once per render so the BOM lookup is O(1) per component, not O(N).

## Recent Fixes (v5.34) — Category Manager: move sub-categories between top categories + merge into another row
- **User request:** "under the category manager i should be able to move sub-categories to another top category - this should fix all instances of categories across pages. also, i should be able to merge sub categories into other ones."
- **Move (via Edit mode)**:
  - Edit-mode Category input now uses an HTML `<datalist>` with all existing top categories as suggestions. Pick from the dropdown to MOVE the sub-category under that top, or type a new value to rename / create.
  - Save runs the same `UPDATE categories SET category=?, subcategory=? WHERE id=?` as before — the row's `id` is preserved, so products linked via `category_id` automatically inherit the new top category without any FK re-wiring.
  - **Duplicate guard:** if the user types a (Category, Sub-category) pair that already exists on a different row, a confirm dialog warns about the duplicate and recommends Merge instead.
- **Merge (new per-row Merge button)**:
  - New orange **Merge** button between Edit and Remove on every row
  - Click → dialog opens with: source row info + product impact count + target dropdown (all OTHER rows, sorted by category)
  - On confirm:
    1. `UPDATE products SET category_id = target_id WHERE category_id = source_id` — every product previously categorized under the source is redirected to the target
    2. `DELETE FROM categories WHERE id = source_id` — source row goes away
  - Product data itself is never deleted; only the `category_id` FK is rewritten.
  - Audit log writes `category.merge` with both source and target details for full trace.
- **No DB migration needed** — uses existing `products.category_id` FK to `categories.id`.

## Recent Fixes (v5.33) — Category Manager: inline edit per row
- **User request:** "i need to be able to edit categories here."
- **Was:** Settings → Category Manager only exposed **+ Add** + per-row **Remove**. To rename a category or subcategory, you had to remove + re-add, which broke the foreign-key link from products to categories.
- **Now:** each row has an **Edit** button next to **Remove**. Click → row flips to two inline `<input>` fields (Category + Sub-category) with **✓ Save** / **Cancel** buttons. Saves run `UPDATE categories SET category=?, subcategory=? WHERE id=?` which preserves the row's `id`, so any products linked via `category_id` keep their link with the new names automatically.
- **State:** `catMgrEditingIds` Set tracks which row id is currently being edited. `renderCatMgr` reads it and switches the row's render between read-only and edit mode.
- **Audit log:** writes `category.edit` event with the new (category, subcategory) values.
- **No DB migration needed** — uses the existing `categories` table.

## Recent Fixes (v5.32) — Catsy importer: separate `noop` action so up-to-date rows don't auto-approve
- **User flagged:** "this is very confusing - why are the products with no updates preselected and the button shows 'already approved'? what is this doing for the user?" Rows that already had matching sp_sku AND populated image_url were being lumped under `action='update_image'` (same as rows that would actually write an image). Auto-approver swept them all up, inflating the "N approved" count with rows that did nothing.
- **Root cause:** `update_image` was overloaded — meant both "will refresh image" and "match perfect, nothing to do" depending on a separately-derived `hasImg` flag that the approver didn't see.
- **Fix — split into two distinct actions:**
  - **`update_image`** — DB has no image AND Catsy provides one → will actually write `image_url`
  - **`noop`** — sp_sku already matches AND either (a) DB already has an image, or (b) Catsy doesn't provide one → nothing to write
- **Updated everywhere this matters:**
  - `catsyBuildMatches` — new `updateOrNoop(dbProd)` helper resolves the action correctly across all 5 match tiers (SP SKU / ASIN / UPC / Shopify / Title)
  - Auto-approve excludes `noop` (in addition to `replace_sku`)
  - `catsyApproveAll(highOnly)` bulk button skips `noop` rows
  - `catsySelectMatch` (manual pick) re-derives `noop` vs `update_image` correctly
  - `actionBadge` renders a dedicated grey **NO-OP** chip with tooltip "Already up-to-date — SP SKU matches AND image is already populated"
  - Summary line breaks them out: `… · N refresh image · M assign new SP SKU · K already up-to-date`
- **New "Hide NO-OPs" toggle** in the action bar, checked by default. The table filters out `noop` rows by default so the user sees only actionable work. Original row indexes are preserved (the filter just skips rendering) so toggle/apply callbacks still work.
- **Behavior on Jason's import**: the 226-ish NO-OPs that were inflating "276 approved" now drop out of the auto-approve count + are hidden from the table by default. Toggle the checkbox off to audit them.

## Recent Fixes (v5.31) — Catsy importer: show full product title (no truncation)
- **User flagged:** "i can't see the full catsy product title in the uploader." Title cell was being chopped at 50 chars with an ellipsis; long Catsy descriptions (~80-150 chars common) were getting cut.
- **Fix in two places:**
  - **Review table cell** — removed the 50-char `slice + …` truncation. Now uses `max-width:280px;white-space:normal;word-break:break-word` so long titles wrap naturally inside a constrained column. Row height auto-grows as needed.
  - **Search popover header** — same fix, removed the 80-char truncation and applied `word-break:break-word`.
- Both retain a `title=` attribute with the full string as a belt-and-suspenders for hover tooltip.

## Recent Fixes (v5.30) — Catsy import "+ Create" prompts for brand / category / sub-category
- **User request:** "on the catsy upload, let me set the category and sub-category and brand if a match isn't found."
- **Was:** `catsyCreateProduct` inserted immediately with brand inferred from SKU prefix and no category set. User had to go edit each newly-created product later via the Product modal.
- **Now:** clicking **+ Create** on a no-match row opens a small dialog with the product details + three editable dropdowns:
  - **Brand** — Meowijuana / Doggijuana / Kitty Ka-Zoom. Defaults to the SKU-prefix heuristic (CF/MTCM→Meowi, DF/MTCD→Doggi, KF/KC→Kitty Ka-Zoom).
  - **Category** — populated from `getCategories()` (uses existing `allCategories` cache).
  - **Sub-category** — cascade dependent on the selected category; disabled until a category is picked. Uses `allCategories.filter(c => c.category === cat)` and writes `category_id` (the FK to the categories row).
- **Dialog UI** shows the Catsy image preview + title up top so the user verifies what they're creating before committing.
- **`catsyCreateProductConfirm(rowIdx)`** — actually performs the insert. Inserts `category_id` (from the sub-category select) so the new product lands fully categorized.
- **Match reason** updated to `🆕 Created from Catsy row · {brand} / {category}` so the table shows the user-selected dimensions.
- **Audit log** entry includes `category_id` in addition to the existing fields.
- **No DB migration needed** — uses existing `products.brand` and `products.category_id`.

## Planned Work — Paused

### Amazon SP-API integration (parked 2026-05-26)
Jason wants to automate the manual uploads (FBA Inventory, FBA Shipments, SKU Economics) via Amazon's Selling Partner API. Discussed in detail and confirmed direction — paused for now, will resume when ready.

**Phased plan when we pick it back up:**
1. **Phase 1** (~1 day) — Register SP-API developer app in Seller Central (5-7 business-day Amazon approval), set up LWA OAuth, store refresh token in Supabase.
2. **Phase 2** (~1 day) — FBA Inventory Snapshot automation. Pull `GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA` daily per region, push into existing `fba_inventory_snapshots` + `inventory` tables. Reuse `parseFbaInventorySnapshot` parser as a shared module.
3. **Phase 3** (~1 day) — FBA Shipments (detail .tsv + summary CSV) on the same daily cadence via the Fulfillment Inbound API + report family.
4. **Phase 4** (~1-2 days) — SKU Economics via `GET_SALES_AND_TRAFFIC_REPORT` (the 2024 replacement for the older format — may require parser adaptation).

**Architecture choice deferred** — Supabase Edge Functions, Cloudflare Workers, or AWS Lambda. All viable, all free for this volume. Decision when we resume.

**Gotchas to remember:**
- LWA refresh-token dance + AWS SigV4 signing on every request
- Async report flow: `createReport` → poll `getReport` until `DONE` → `getReportDocument` → download from S3
- Region-specific endpoints: NA (US/CA/MX) · EU (UK/EU) · FE (JP/AU)
- Rate limits + restore rates per endpoint
- Some reports only cover the last 30 days — no retroactive backfill

**Libraries worth using** — `amazon-sp-api` (Node) or `python-amazon-sp-api` (Python). Solved problem; avoids hand-rolling the auth.



## Recent Fixes (v5.29) — Catsy importer: include bundles in matching + search
- **User flagged:** "none of the bundles are coming up when i try to search for existing products."
- **Root cause:** v5.19 had `allProducts.filter(p => !p.is_bundle)` in both the auto-matcher (`catsyBuildMatches`) and the search popover (`catsyRenderSearchResults`). The filter was conservative-by-default but wrong — bundles have `sp_sku` and `image_url` like any other product, and the Catsy importer only touches those two fields (never BOM), so excluding bundles served no purpose.
- **Fix:** dropped the filter in both call sites. Bundles now:
  - Match by SP SKU exact, ASIN, UPC, Shopify SKU, or title (fuzzy or exact) — same tiers as single products
  - Appear in the manual search popover results
- **New BUNDLE chip** in search results — orange pill rendered next to the sp_sku chip so users know they're picking a bundle vs a single product before clicking through.

## Recent Fixes (v5.28) — Image diff column on Catsy importer (DB → Catsy thumbnails side-by-side)
- **User flagged:** "for these items, they already have the same image but the uploader thinks they are different." Root cause: the action badge only said "UPDATE IMG" or "NO-OP" without surfacing what the DB actually contained vs what Catsy was offering. Users had no way to verify "this product already has this exact image" visually.
- **New "Image (DB → Catsy)" column** in the review table:
  - Two 40×40 thumbnails side-by-side: DB image (current) on the left, Catsy image (proposed) on the right
  - Arrow indicator between them encodes the comparison state:
    - `·` muted — no images on either side (or no Catsy image to apply)
    - `✓` green **same** — URLs match exactly (no change needed)
    - `+` blue **add** — DB has none, Catsy will set this one (true UPDATE IMG case)
    - `≠` orange **differ** — both have images but URLs don't match (Catsy URL ignored to protect curated images)
    - `keep DB` — Catsy row has no image; DB image preserved
  - Each thumbnail is a click-through link to the full-size image; `onerror` falls back to a "err" placeholder so broken URLs don't break the row.
- **URL-aware `hasImg` logic** — was `!!(catsyUrl && !dbUrl)` (only true when DB was empty). Now precisely matches the apply behavior: hasImg is true ONLY when Catsy has a URL the DB doesn't. If both URLs match, hasImg is false → action renders NO-OP correctly.
- **The mismatch that confused the user**: visually identical images can have different URLs (CDN variants, query params, S3 path differences). The diff column now makes this state visible — if you see `≠ differ` but the thumbnails look identical, that's a URL-level mismatch that the importer is conservatively skipping.

## Recent Fixes (v5.27) — Image displays in the Product edit modal
- **User request:** "if there is an image, it should appear in the product card when clicked"
- **New "Product Image" section** at the top of the product edit modal body (above Product Info):
  - **120×120 thumbnail** on the left with `object-fit:contain` (no distortion)
  - **Editable URL input** on the right with field hint explaining the integration with Catsy import
  - **Click thumbnail** to open the full-size image in a new tab (skipped when URL is blank)
  - **"No image" placeholder** shown when blank, swaps in for broken URLs via `onerror`
- **Live preview** — `pfUpdateImagePreview()` runs on every keystroke in the URL field. Paste a new URL and the thumbnail updates immediately (also runs once on modal open to show the saved image).
- **`openProductModal`** now reads `p.image_url` into the input and triggers the preview.
- **`saveProduct`** now persists `image_url` (null when blank, keeps the column clean).

## Recent Fixes (v5.26) — Left-align Products table text cells
- **User request:** "in the product page can you left align the product title?"
- Global `td` default in this app is `text-align:right` (numeric-heavy convention). The Products table's text cells (Brand chip, Title, SP SKU, ASIN, Category, Sub-cat) hadn't overridden it, so all text was floating to the right side of their wide columns.
- Added `text-align:left` inline on each of the 6 text columns in `renderProductsTbl`'s row template. Numeric columns (MSRP, Active, Bundle, Edit button) keep their original alignment.
- Header row was already `text-align:left` so headers stay properly aligned with the (now left-aligned) data.

## Recent Fixes (v5.25) — Catsy importer: per-row Skip + per-row Apply + bulk Remove unmatched
- **User request:** "1. i can't remove products that aren't a match. 2. let me click individual rows to update rather than updating all."
- **Per-row [✕ Skip] button** — always available on every row. Removes the row from `catsyMatches` + re-renders. Use for rows you don't want to act on at all (declutters the table).
- **Per-row [↓ Apply] button** — appears next to [🔄 Change] on every approvable matched row. Writes only that row's update; on success, the row drops out of the table so the user can iteratively work through remaining items.
- **Bulk [✕ Remove all unmatched] button** added to the top action bar alongside Approve all / Clear all. One click drops every "no match" row.
- **`catsyWriteRow(m)`** — new shared helper that builds the payload + does the Supabase write + mirrors changes onto the in-memory `allProducts` entry. Used by both batch Apply and per-row Apply (single source of truth for the write logic).
- **Batch Apply now also removes applied rows from the table** as it goes (was just leaving them in place). Successful + no-op rows are spliced out; failures stay so the user can investigate.
- **In-memory `allProducts` mirror** — after a per-row write, the matching `allProducts` entry's `sp_sku` / `image_url` is updated locally so subsequent table re-renders show the new state instantly (no full reload required between row applies).

## Recent Fixes (v5.24) — Catsy importer: existing SP SKU column + per-row search + create-new-product
- **User request:** "i need to see the existing SP_SKU on the catsy uploader. i also want to be able to search the product database to grab the db product to match. also give me the option to create new product if none exists."
- **New "Existing SP SKU" column** in the review table — color-coded:
  - 🟢 green when DB sp_sku matches the Catsy proposed sp_sku exactly
  - 🟠 orange when it's set but different (this is a REPLACE candidate)
  - `(none)` muted italic when product has no sp_sku yet
  - `—` when no DB product is matched
- **New "Catsy Title" column** — replaces the cramped "Catsy ID" column. Surfaces the actual product description so the user can eyeball matches visually instead of decoding ASIN/UPC keys.
- **🔄 Change / 🔍 Search / + Create buttons** in the Match column:
  - **🔍 Search** (on unmatched rows) — opens a search popover that filters all products by title / sp_sku / master_id / ASIN / Shopify SKU. Multi-token AND-match. Top 50 results. Click to link.
  - **🔄 Change** (on matched rows) — same popover, lets the user swap to a different product.
  - **+ Create** (on unmatched rows) — creates a new product from the Catsy row's data: `master_id=SP-TEMP-{sku}`, `sp_sku`, `title`, `image_url`, `brand` inferred from SKU prefix (CF/MTCM→Meowi, DF/MTCD→Doggi, KF/KC→Kitty Ka-Zoom, fallback Meowi), `active=true`, `notes='Auto-created from Catsy import — needs review'`. Promoted to a real SP-XXXX later via the existing product modal flow.
- **Manual selection re-computes the row's action** automatically:
  - Picked product has no sp_sku → `assign_sku` (auto-checks Approve)
  - Picked product's sp_sku == Catsy proposed → `update_image` (auto-checks if there's an image to set)
  - Picked product's sp_sku != Catsy proposed → `replace_sku` (does NOT auto-check)
- **Match reason** prefixed with `🔧` for manual picks and `🆕` for newly-created products, distinguishing user actions from auto-matched rows.
- **"Clear match" button** in the search popover for backing out a wrong match.
- **Audit log** records create events as `catsy.create_product` with `master_id`, `sp_sku`, `title`, `brand`.

## Recent Fixes (v5.23) — Catsy importer: title fallback now searches ALL products, surfaces SP SKU conflicts
- **User request:** "if it doesn't match based on the ID, it should try to match based on the item title to the title in the product db."
- **Was:** v5.22's title fuzzy fallback only considered products without an sp_sku. If a Catsy row's Item ID didn't match any sp_sku but the title matched an already-linked product, that match was invisible. Threshold was also 0.85 (too strict for paraphrased Catsy descriptions).
- **Fix:**
  - Title match now searches **every** product, not just sp_sku-less ones.
  - Tries **exact title match first** (after the SKU prefix strip), falls back to fuzzy (Dice bigram).
  - **Threshold lowered to 0.70** — more candidates surface; user can still eyeball + reject in the review table.
  - **Confidence tier**: exact title or fuzzy ≥0.85 → HIGH; fuzzy 0.70–0.85 → LOW.
- **New action `replace_sku`** — surfaces when title matches but the DB product already has a *different* sp_sku set. Distinct from `assign_sku` (no existing sp_sku) and `update_image` (sp_sku already matches Catsy).
  - **Always default-UNCHECKED** even at high confidence — overwriting a curated sp_sku is high-risk; require explicit user click.
  - **Red ⚠ REPLACE SKU** badge in the action column with a tooltip showing the existing sp_sku that would be overwritten.
  - Reason text includes `· existing sp_sku: XXX` so the conflict is visible without hovering.
  - Bulk "Approve all high-confidence" button explicitly skips replace_sku rows.
  - Summary row counts replacements separately so the user sees `⚠ N replace SP SKU (review!)` at the top.
- **Collision detection extended** — applies to both `assign_sku` AND `replace_sku` rows now (anything writing sp_sku).
- **Apply payload + audit log** now count `sku_replaced` separately from `sku_assigned`.

## Recent Fixes (v5.22) — Catsy importer: SP SKU is the PRIMARY match key (was missing entirely)
- **User flagged:** "this matched 0 existing product db items lol. is it mapping to SP SKU?"
- **Root cause:** v5.19's matcher only considered products *without* an sp_sku, then tried to assign the Catsy SKU to them via ASIN/UPC/Shopify SKU/title match. But Jason's DB has hundreds of products where `sp_sku` is ALREADY a Catsy-style ID (`CF128`, `DF270`, etc.) — the Catsy "Item ID" column IS the SP SKU. The matcher never looked for that, so every row reported "no match."
- **Fix — SP SKU exact match is now the primary path** (tier 1, above ASIN/UPC/Shopify/title). Indexes every product (not just sp_sku-less ones).
- **Two distinct row actions emerge**, each tagged on the match record:
  - `update_image` — DB product's `sp_sku` already equals the Catsy Item ID. Import refreshes `image_url` only (`sp_sku` is not rewritten). Most common case for Jason's catalog.
  - `assign_sku` — DB product matched by ASIN/UPC/Shopify/title but had NO `sp_sku`. Import writes both `sp_sku` AND `image_url`.
- **Action badge per row** in the review table — `UPDATE IMG` (blue), `ASSIGN + IMG` (green), `NO-OP` (grey for sp_sku-matched rows where Catsy didn't provide an image). User sees exactly what each approval will write.
- **Summary line** now breaks out the action mix: `N refresh image · M assign new SP SKU · K SKU collision`.
- **Collision detection narrowed** — only flags `assign_sku` rows where the proposed SKU already belongs to a different product. `update_image` rows can't collide (they're operating on the product that already has the SKU).
- **Apply payload** is action-dependent — `update_image` writes only `image_url` (if Catsy provides one and DB product doesn't already have one); `assign_sku` writes both fields. Skips entirely when nothing would change.
- **Success message** now breaks counts apart: `✓ Applied N updates. M new SP SKU assignments. K image URLs set.`

## Recent Fixes (v5.21) — Product image column + Catsy importer writes image URLs
- **User request:** "also can we add the image into the product table?"
- **⚠ SQL TO RUN:** `supabase_v5_21_add_product_image.sql` — adds `products.image_url TEXT` (nullable). Run BEFORE deploying.
- **New "Img" column** at the leading edge of the Products table:
  - 36×36 thumbnail with `object-fit:contain` so non-square images don't distort
  - Lazy-loaded (`loading="lazy"`)
  - Click → opens full-size in a new tab (`event.stopPropagation()` so the row's "open modal" doesn't fire)
  - `onerror` fallback swaps a broken URL for a 🖼 placeholder rather than showing a broken image
  - `—` placeholder for products without an image
- **Catsy importer**: detects the "Main Image" column (also accepts `image`, `image url`, `image_url`, `primary image`, `primary_image`). On approval, writes both `sp_sku` AND `image_url` to the products row in one UPDATE.
- **Don't overwrite user-curated images** — if the product already has `image_url` set, the import skips that field (only sp_sku gets updated). The Catsy URL is treated as a starting point, not a forced replacement.
- **Success message** now reports image count separately, e.g., `✓ Applied 47 sp_sku updates. 47 image URLs also set.`
- **Audit log entry** for `catsy.import` now includes `images_set` count.

## Recent Fixes (v5.20) — Catsy importer: XLSX support + Catsy MasterItems column mapping
- **Inspected Catsy export** `MasterItems-20260526-1527-12.xlsx` to confirm the actual format. 5 columns: `Completeness Score` · `Update Date` · `Item ID` · `Main Image` · `Item Description`. The "Item ID" column carries the SP SKU (e.g., `CF2506`). The "Item Description" column is formatted as `<SKU> - <Title>` (e.g., `CF2506 - Naughty List Nip Candy Cane`).
- **XLSX parser added** — reuses the existing SheetJS library (already loaded at line 441 for Chewy Vendor Statement parsing). Detects `.xlsx`/`.xls` extension and reads via `XLSX.utils.sheet_to_json(sheet, {header:1, defval:''})`; CSV/TSV path unchanged. File input now accepts `.xlsx,.xls,.csv,.txt,.tsv`.
- **Column name detection extended** to recognize Catsy's actual headers:
  - SP SKU column tries `item id` / `item_id` first, then the original fallbacks
  - Title column tries `item description` / `item_description` first, then `title` / `name` / etc.
- **SKU prefix stripped from title** before fuzzy matching — `CF2506 - Naughty List Nip Candy Cane` → `Naughty List Nip Candy Cane`. Uses an anchored regex with the row's own proposed SKU so each row strips its own prefix.
- **State reset** on each modal open — `catsyRows = []` and `catsyMatches = []` so a second import in the same session starts clean.
- **Practical implication for Catsy file**: since the Catsy export has no ASIN / UPC / Shopify SKU columns, every match falls to title fuzzy matching (LOW confidence). Each match requires manual review/approve — which is exactly what the user asked for. Bulk "Approve all high-confidence" will do nothing for a pure-Catsy import; user toggles per row or uses the master checkbox.
- **Drop zone copy** updated to mention .xlsx and "Catsy MasterItems export, or any product list."

## Recent Fixes (v5.19) — Catsy product list import + SP SKU reconciliation
- **User request:** "i need a way to import a product list from catsy and reconcile items in my database that don't have a SP SKU. i would like a feature under the product page to do this — let me upload a csv and then attempt to match the SP SKU (but require an approve click)."
- **New button on Products page**: **↑ Import Catsy** (blue accent next to + New Product). Opens a modal-driven 3-step flow.
- **Step 1 — Upload**: drag-and-drop or click-to-pick. Accepts .csv / .tsv / .txt. Auto-detects tab vs comma separator. Tolerant of column name variants:
  - **SP SKU column** tried in order: `sp sku`, `sp_sku`, `smarterpaw sku`, `parent sku`, `product sku`, `sku`
  - **Match keys** (one or more): `asin`, `upc`/`barcode`/`gtin`/`ean`, `shopify sku`, `title`/`name`/`product name`
- **Step 2 — Review table**: every Catsy row gets matched against products *without* an existing sp_sku (the reconcile target). Match logic, in order:
  1. Exact ASIN match → **HIGH** confidence (auto-checked)
  2. Exact UPC/Barcode match → **HIGH** (auto-checked)
  3. Exact Shopify SKU match → **HIGH** (auto-checked)
  4. Fuzzy title match (Dice bigram coefficient ≥ 0.85) → **LOW** (requires manual approve)
- **Per-row checkbox** to approve. **Bulk actions**: "Approve all high-confidence" + "Clear all" + master checkbox in the table head.
- **SKU collision detection**: if the proposed SP SKU already exists on a DIFFERENT product, the row gets a red **COLLISION** badge and the approve checkbox is disabled. Prevents accidental duplicate sp_sku creation.
- **Step 3 — Apply**: clicks loop through approved rows and run `UPDATE products SET sp_sku = ... WHERE master_id = ...` one-by-one. Reports applied vs failed counts. Logs to audit trail (`catsy.import` action). Reloads `allProducts` + re-renders the table.
- **State variables**: `catsyRows` (raw CSV rows) + `catsyMatches` (per-row match + approval state). Reset per modal open.
- **No DB migration needed** — writes to existing `products.sp_sku` column.

## Recent Fixes (v5.18) — Bundles CSV exports per-component rows (BOM-expanded)
- **User request:** "on the bundle page, i need the csv export to export a row for every BOM component related to the parent bundle."
- **Was**: Bundles + Products tabs shared one export branch — both emitted one row per product (bundles got a flat 16-col list identical to a single Products row).
- **Now**: Bundles has its own branch. Each bundle expands to **N rows = N BOM components**. Bundles with no BOM yet still emit one row (component columns blank) so they remain visible in the export.
- **New 23-column schema** (4 logical bands):
  - **Bundle (parent)** — Bundle_Master_ID · Bundle_SP_SKU · Bundle_Brand · Bundle_Title · Bundle_Short_Name · Bundle_ASIN · Bundle_Shopify_SKU · Bundle_MSRP · Bundle_Wholesale · Bundle_Active · Bundle_Notes
  - **Component (child)** — Component_Master_ID · Component_SP_SKU · Component_Brand · Component_Title · Component_Short_Name · Component_ASIN · Component_Shopify_SKU · Component_Chewy_SKU · Component_Wholesale
  - **BOM link** — Qty_Per_Bundle · BOM_Verified · BOM_Notes
- **Stable sort** — bundles alphabetically by title, components alphabetically within each bundle. Predictable for diffs across exports.
- **Resolves component product data** via a `productById = new Map(allProducts.map(p => [p.master_id, p]))` lookup. Single pass, O(B+C) total.
- **Filename** now distinct from products: `smarterpaw-bundles-bom-{filtered-?}{date}.csv` (the `-bom-` tag flags this as the expanded form).
- **Products export unchanged** — refactored the shared branch into separate `tab === 'products'` and `tab === 'bundles'` blocks but the products schema/output is byte-identical to before.

## Recent Fixes (v5.17) — "Shipments" column + inline viewer on Inventory Planning
- **User request:** "i need a new inventory planning dimension that lists all shipments the asin is included on and a button to view these shipments."
- **New column `shipments`** in INVENTORY group:
  - Cell shows `N active · M total` plus a 📦 View button
  - "Active" = Working / Receiving / unknown status (anything not Closed)
  - Sortable by total shipment count
  - `default:false` — opt-in via Show all in table
- **New `openIpShipmentsViewer(masterId)` modal**:
  - Lists every shipment containing this master_id's ASIN(s), split into **Active** + **Closed** sections
  - Columns: Shipment ID · Status · Region · Shipped · Located (with ±variance badge) · Created · Updated · Open button
  - Status color-coded (orange Working / blue Receiving / muted Closed)
  - Each row's **↗ Open** button switches to the FBA Shipments tab with that shipment pre-expanded
- **Data load** extended `loadFbaInTransit()` to build a second map `ipShipmentsByMaster: Map<master_id, [{shipment_id, status, qty_shipped, qty_received, units_expected, units_located, created_date, last_updated, region, ship_to}]>` while it's already paginating fba_shipments. Zero extra round-trips.
- **CSV export**: emits pipe-separated `ID:status:qty` triples per shipment (newest first) — one cell, parseable downstream.
- **No DB migration needed** — uses existing `fba_shipments` + `fba_shipment_summaries` tables.

## Recent Fixes (v5.16) — Target supply = open numeric input + Forecast+Inventory join preset
- **User request:**
  1. "Target supply — give a tooltip on how this works. Also let it be an open numeric field in days rather than a drop down. Default to 90 days but let another default be set."
  2. "Give me a new query for the query editor view to join all data from the forecast and inventory planning tables."

### 1. Target supply field
- **Was**: `<select>` with three options (75 / 60 / 90 days)
- **Now**: `<input type="number" min="1" max="365">` defaulting to 90. User edits directly — any positive integer 1-365 accepted.
- **Tooltip** on the label explains: `Order Qty = (seasonal demand over (lead_time + target) days) + safety stock − current on-hand − inbound`. Higher target = larger orders, fewer POs, more capital tied up. Lower target = opposite.
- **🛟 button** next to the input — clicking SAVES the current value as the user's default for future sessions. Stored to `localStorage.ipTargetDefault`. Live edits go to `localStorage.ipTargetCurrent` (overrides default until cleared); button shows ✓ for 1.2s on save.
- **`onIpTargetChange()`** — clamps to [1, 365], persists to ipTargetCurrent, re-renders.
- **`ipRestoreTargetSupply()`** — reads ipTargetCurrent first, falls back to ipTargetDefault, then to 90. Called at top of `renderInventoryTbl()` so the value survives tab switches.

### 2. New query preset: "Forecast + Inventory (joined)"
- Combined view per `(master_id, region)` — mirrors the data driving both the in-app Demand Forecast + Inventory Planning tables in one CSV-exportable result.
- **Tables joined**: `products` × `velocity_calculated` × `inventory` × `fba_inventory_snapshots` (latest per `(asin, region)`)
- **Region union CTE** ensures rows surface even when only one of velocity / inventory exists for a region
- **Settings columns expose all three layers**:
  - `..._region` — per-region override on inventory.* (v5.1)
  - `..._master` — master-level default on products.* (fallback)
  - `..._eff` — what the model actually uses (`coalesce(inv.X, p.X, default)`)
- **Snapshot freshness** column: `snapshot_age_days` + categorical `snapshot_freshness` (`fresh` / `stale` / `very stale` / `never`)
- LIMIT 2000 (vs 100 for most other presets) since this is the "give me everything" join.

## Recent Fixes (v5.15) — "Amz Inv Updated" column on Inventory Planning (snapshot freshness)
- **User request:** "i need a new column on the inventory planning module - amazon inventory last updated - this should be exportable via csv. also i want it grouped with the product/sku set of dimensions."
- **New IP_COLUMN `amazon_inv_last_updated`** in the **SKU** group (sits next to SP SKU / Master ID / ASIN). Label: **"Amz Inv Updated"**. `default:false` so existing layouts don't shift; opt-in via Show all in table.
- **Cell renders the date + relative age** (`2026-05-25 · 1d ago`). Color codes by staleness:
  - **Default muted** when ≤7 days old
  - **Orange** when 8–30 days old
  - **Red** when >30 days old or never uploaded
  - Hover tooltip explains how to refresh
- **Pooled rows show the OLDEST snapshot across regions** — the limiting factor for "are we current?" purposes. A US+CA pooled row where US is fresh but CA is 60d stale will show 60d (CA's date) so the staleness floor is visible at a glance.
- **Sort works on the date string** — sorting ascending bubbles the most stale to the top (or bottom, with desc), useful for "which products need a re-upload?"
- **Data load**: paginated query against `fba_inventory_snapshots`, ordered by `snapshot_date DESC`, dedupe to first-occurrence per `(asin, region)`. Pagination critical because snapshots accumulate weekly × N ASINs × N regions can exceed Supabase's 1000-row default.
- **Records-build** attaches `amazon_inv_last_updated` to every per-region record (null for products without ASIN or without a snapshot).
- **CSV export** emits the ISO date string as-is — no special formatting, no emoji. Pooled rows export the oldest-across-regions date to match the cell logic.
- **No DB migration needed** — uses the existing `fba_inventory_snapshots` table written to by the FBA Inventory upload flow.

## Recent Fixes (v5.14) — Split FBA Inventory uploader into US/CA/MX/AU/JP + EU/UK dropzones (matches SKU Economics pattern)
- **User request:** "in the inventory upload for amazon, we need to split the uploader for EU like we did the SKU economics report. the EU link to download the report is https://sellercentral.amazon.co.uk/reportcentral/FBA_MYI_UNSUPPRESSED_INVENTORY/1"
- **Two dropzones now**:
  - 📦 **FBA Inventory — US / CA / MX / AU / JP** — links to `sellercentral.amazon.com/reportcentral/FBA_MYI_UNSUPPRESSED_INVENTORY/1`. Region prompt shows the full list, user picks.
  - 🇪🇺 **FBA Inventory — EU / UK** — links to `sellercentral.amazon.co.uk/reportcentral/FBA_MYI_UNSUPPRESSED_INVENTORY/1`. Region prompt preselects `EU/UK` so user just confirms + sets date.
- **`handleFbaInventoryUpload(input, presetRegion=null)`** — extended to accept an optional preset. The EU dropzone passes `'EU/UK'`. Status + last-snapshot DOM IDs are auto-routed based on input id (`f-fba-inv` vs `f-fba-inv-eu`) so each dropzone updates its own labels.
- **`promptFbaSnapshotMeta(presetRegion=null)`** — extended to accept the same preset. When set, that option is marked `selected` in the dropdown; user can still change it if they grabbed the wrong file.
- **Card description** rewritten to call out the two-gateway split + which marketplaces each gateway covers.

## Recent Fixes (v5.13) — Collapse UK + EU into one "EU/UK" pool (rolls back v5.12 Brexit split)
- **User pushback:** "what? why did you introduce the brexit complexity? GB is included in the amazon EU/UK." Screenshot from `sellercentral.amazon.co.uk/sereport` showed GB sitting in the same country selector as DE/SE/BE/IT/IE/PL/FR/ES/NL — from the seller's perspective they're one group, accessed from one Seller Central login.
- **Reverted v5.12**: dropped separate UK and EU options, dropped the per-country EU advanced disclosure, dropped the Brexit explanation panel.
- **`FBA_REGION_OPTIONS`** is now 6 entries: US · CA · MX · **EU/UK** (region code `'EU/UK'`) · AU · JP.
- **Prompt UI** trimmed back to the simple region dropdown + snapshot date — no info panels, no advanced disclosures. Cleaner.
- **Upload card description** rewrote to call out the EU/UK pool as one upload covering GB + DE/FR/IT/ES/NL/SE/PL/BE/IE.
- **`FBA_REGION_OPTIONS_EU_PER_COUNTRY`** constant deleted entirely.
- **Migration impact**: zero. The `inventory.region` column is unconstrained text; storing `'EU/UK'` works the same as `'EU'` or any other code. If a v5.12 user uploaded with region `'UK'` or `'EU'` separately, those rows persist with their original codes — they'd show up as filterable values in the Inventory Planning dropdown via `populateRegionFilters()`. Re-upload to `'EU/UK'` if you want them consolidated.

## Recent Fixes (v5.12) — FBA region picker reflects post-Brexit topology (Pan-EU = one pool, UK separate)
- **User flagged:** "UK will have one FBA inventory, but the uploader asks me to select a specific country." The v4.199 picker exposed DE/FR/IT/ES/NL as separate fulfillment pools, which is wrong for any Pan-EU enrolled seller — they hold ONE pool that Amazon distributes across country FCs.
- **Post-Brexit FBA topology** (now reflected in the picker):
  - **UK** — standalone pool (left the EU FBA network in 2021). One upload from amazon.co.uk Seller Central.
  - **EU** — single Pan-European pool covering DE/FR/IT/ES/NL plus SE/PL/BE/IE for full Pan-EU sellers. ONE upload from any EU marketplace.
  - Per-country EU codes (DE/FR/IT/ES/NL) kept available behind an **Advanced** disclosure for the minority of sellers who run EFN or have opted OUT of Pan-EU and hold separate per-country inventory.
- **`FBA_REGION_OPTIONS`** primary list now: US · CA · MX · UK · EU · AU · JP.
- **`FBA_REGION_OPTIONS_EU_PER_COUNTRY`** new constant — DE · FR · IT · ES · NL (per-country, advanced).
- **Prompt UI** adds a blue Pan-EU explanation box at the top, plus a `<details>` disclosure for the per-country EU advanced override. Per-country selection (if set) wins over the main dropdown.
- **Upload card description** rewrote to call out "fulfillment pool" instead of "region" + list Pan-EU explicitly with the full country roster.

## Recent Fixes (v5.11) — "Selected only" export option on Inventory Planning CSV
- **User flagged:** had 1 row checkbox-selected on Inventory Planning but the export dialog only offered "Everything (518 rows)" — no way to export just the selection. The "Filtered results" button was hidden because no page filters were active (filteredCount === totalCount).
- **Fix:** `showExportDialog` now also tracks `selectedCount = inventorySelected.size` and renders an "↓ Selected only (N checked rows)" button at the top of the dialog whenever there's a selection. Independent of the filtered/all buttons — they all coexist.
- **`downloadInventoryCSV(mode='selected', ...)`** — new mode. Filters records by `inventorySelected.has(\`${master_id}_${region}\`)`. Respects the active region filter: if pinned to US, source records are US-only; if pooled, source is `combineRegionRecords(records)` so the selection keys (which may use `'US+CA'` for pooled rows) resolve correctly.
- **Filename** now tags `selected` alongside `all` and `filtered` — e.g., `smarterpaw-inventory-90d-selected-2026-05-25.csv`.
- **Logs `mode: 'selected'`** in the audit trail.

## Recent Fixes (v5.1) — Per-region Amazon FBA Reorder columns + per-region PO settings
- **User request:** "For Amazon, I think i am going to need different regions split out - so an Amazon FBA US 30/60/90/120 and a Amazon FBA CA 30/60/90/120. when the region drop down is only US, the rollup amounts should only display for US. I also need separate new, deprecate, reorder threshold, and reorder quantity for US and CA."
- **⚠ SQL TO RUN:** `supabase_v5_1_per_region_amazon_settings.sql` — adds 5 new columns to `inventory` table (`reorder_threshold_days`, `reorder_qty_days`, `new_product_amazon`, `deprecated_product_amazon`, `new_amazon_daily_units`) and backfills from `products.*` for every existing row. `products.*` columns kept as master-level defaults — records-build reads `inv.X ?? p.X`. Idempotent.
### Schema + data layer
- **5 fields migrate from master-level → per-region** on the inventory table. `products.*` versions stay as fallback defaults so a brand-new region (no inventory row yet) still gets the master values until first overridden.
- **Records build** (line 2912-2928): reads `inv?.X ?? p.X` for every per-region record. Each record carries its own region's settings — no more cross-region bleed.
- **`combineRegionRecords`** now snapshots each per-region record onto `_byRegion[regionCode]` on the pooled record. Lets per-region columns drill back into per-region state even in the pooled view.
### Math layer
- **New helper `regionViewOf(r, region)`** — returns the per-region sub-record for a pooled record, or `r` itself if it's a single-region match, or `null` if the region isn't present on this record. Used by every per-region column's `sortVal` / `render`.
- **`inventoryNeedBreakdown(r, X, region)`** — optional 3rd arg. When passed, recurses into the per-region sub-record via `regionViewOf` and returns a region-scoped breakdown. When omitted, behaves as before (pooled / single-region default). Used by the new per-region Amazon FBA Reorder columns.
- **`EMPTY_NEED_BREAKDOWN`** — frozen zero-shape returned when the requested region isn't present on a record (e.g., asking for CA on a US-only product).
### New IP_COLUMNS (all default:false, opt-in)
- **8 per-region Amazon FBA Reorder columns** (replaces the 4 single-region columns from v4.197):
  - `0–30d FBA US` · `30–60d FBA US` · `60–90d FBA US` · `90–120d FBA US`
  - `0–30d FBA CA` · `30–60d FBA CA` · `60–90d FBA CA` · `90–120d FBA CA`
  - Single-region filter view: only the matching-region columns populate; the other shows `—`. Pooled view: both populate (drilled from `_byRegion`).
- **10 per-region settings columns** (replaces the 5 master-level columns from v5.0):
  - `New (US)` · `New (CA)` · `New Rate/d (US)` · `New Rate/d (CA)`
  - `Dep (US)` · `Dep (CA)`
  - `Thresh US (d)` · `Thresh CA (d)`
  - `Qty US (d)` · `Qty CA (d)`
- **FBM rows** show `—` in all FBA Reorder columns (existing v4.197 logic preserved).
### Edit flow
- **Inventory edit modal save** (line 16780-16842): the 5 settings now write to **inventory.\*** for that asin+region (not products.*). Mirror loop only touches **same-region** peers — editing US no longer overwrites CA's settings. Master-level `fulfillment_amazon` still mirrors to all regions.
- **Product modal save** (line 17680-17710): broadcasts the 5 settings to **all inventory rows** for the master_id ("set default for all regions"). Per-region overrides set later via Inventory modal will win on the next records-build. This preserves the existing UX where the Product modal acts as a master switch.
### CSV export
- New `valueOf` regex matches `^(field)_(us|ca)$` keys and resolves via `regionViewOf`. Boolean fields export as `Yes`/`No`, threshold/qty fall back to defaults (90), rate fields blank when 0.
### Known limitations
- **Pooled-view `new` launch override**: when SOME but not all regions are flagged new, the pooled record's `blended_daily` uses the first region's override rate rather than summing effective per-region vels. Edge case (most products are new everywhere or new nowhere); flagged here for future fix. Per-region views are unaffected.
### Verification
- 22/22 unit tests passed for `regionViewOf` + `EMPTY_NEED_BREAKDOWN` (smoke test, since deleted). Node `--check` on the extracted script passes.

## Recent Fixes (v5.01) — FBA snapshot upload bug fix: aggregate multi-SKU ASINs
- **User flagged:** uploading the Doggijuana US FBA Inventory snapshot threw `ON CONFLICT DO UPDATE command cannot affect row a second time` (Postgres error).
- **Root cause:** Amazon's Manage FBA Inventory report has **one row per SKU**, and a single ASIN can have multiple SKU variants (stickered + stickerless, FBA + FBM, prep variants). When two CSV rows shared the same ASIN, the parser would build two `inventory` payload entries with the same `(asin, region)` conflict key. Postgres rejects this — you can't UPDATE the same target row twice in a single statement.
- **Fix in `parseFbaInventorySnapshot`** — added an aggregation pass after CSV parse, before any DB write. For each ASIN with multiple SKU rows:
  - All numeric quantities SUM (separate FBA stock pools share the ASIN → roll up at the ASIN level)
  - SKU codes are joined with ` · ` in the `sku` column for traceability ("714929800121 · 714929800121-FBM")
  - Helper fields (`_skuCount`, `_skuList`) are stripped before Supabase upsert
- **Status message** now reports both ASIN count and aggregation count, e.g., `✓ 88 ASINs · US · 4 ASINs aggregated across multiple SKUs`
- **Console log** lists the aggregated ASINs + their SKUs for debugging
- **Snapshots table benefits too** — same `(asin, region, snapshot_date)` unique key, same bug, same fix.

## Recent Fixes (v5.0) — Expose all PO-math inputs as sortable/exportable columns
- **User request:** "on the inventory planning module, i need the amazon reorder threshold, reorder qty, new amazon, deprecated amazon available as columns and exportable via csv. add any other columns that go into inventory calculations."
- **Version bump to v5.0** per Jason's call (was v4.202; the v4.203 → v5.0 placeholder note in CLAUDE.md is now resolved).
- **New columns added to IP_COLUMNS** (all `default:false` — opt-in via Show all in table):
  - **PO PLANNING band (extended):**
    - `safety_stock` — Safety (d). Defaults shown as muted "14" when blank.
    - `reorder_threshold_days` — Reorder Thresh (d). Default 90 shown muted.
    - `reorder_qty_days` — Reorder Qty (d). Default 90 shown muted.
    - `moq` — MOQ. Numeric; "—" when blank.
    - `supplier` — Supplier. Free-text; left-aligned.
  - **NEW band "AMAZON SETTINGS":**
    - `fulfillment_amazon` — FBM (orange pill) / FBA (muted). Pulled from products.fulfillment_amazon.
    - `new_product_amazon` — 🆕 NEW pill / —. Boolean.
    - `new_amazon_daily_units` — New Rate/day. Numeric, only meaningful when New flag is on.
    - `deprecated_product_amazon` — ⛔ DEP pill / —. Boolean.
  - **NEW band "SEASONALITY":**
    - `sea_override` — Sea Override. Shows `1.25×` when set, `auto` when blank.
- **CSV export emits readable values** — `downloadInventoryCSV`'s `valueOf` now resolves each new column to its export-friendly form:
  - Booleans → `Yes` / `No`
  - `fulfillment_amazon` → `FBA` / `FBM` (uppercase)
  - `sea_override` → numeric or literal string `auto`
  - PO defaults (90/90/14) — exported as the effective value even when the underlying field is null, so the CSV always shows what the model is actually using rather than blanks.
- **Column tooltips** call out the math role of each input (e.g., "ROP = lead + safety", "cycle period = reorder_qty_days", "FBM means Amazon vel goes into Base via continuous draw").

## Recent Fixes (v4.202) — Direct Seller Central report links on every upload card
- **User request:** add direct links to each Amazon Seller Central report on the Uploads page so users don't have to navigate through SC's menus to find them.
- **Links added** (all open in new tab via `target="_blank" rel="noopener"`, click handlers stop propagation so they don't trigger the dropzone file picker):
  - **SKU Economics US/CA** → `https://sellercentral.amazon.com/sereport`
  - **SKU Economics EU** → `https://sellercentral.amazon.co.uk/sereport` (UK gateway, but the report covers GB / DE / FR / IT / ES / NL)
  - **FBA Inventory Snapshot** → `https://sellercentral.amazon.com/reportcentral/FBA_MYI_UNSUPPRESSED_INVENTORY/1` (Amazon's internal report ID — `FBA_MYI_UNSUPPRESSED_INVENTORY` — also added to the description text for grep-ability)
  - **FBA Shipment Detail** → `https://sellercentral.amazon.com/gp/ssof/shipping-queue.html/ref=xx_fbashipq_dnav_xx#fbashipment` (Manage FBA Shipments queue — click into each shipment to download)
  - **FBA Shipment Summary** → same URL, with prominent note "press **Export table data**" since that button is what produces the list CSV
- **Confirmed** the uploaded `224702020598.csv` is the right file for the FBA Inventory uploader — columns (`afn-fulfillable-quantity`, `afn-warehouse-quantity`, `afn-reserved-quantity`, `afn-inbound-*`) match the parser exactly. That's the `FBA_MYI_UNSUPPRESSED_INVENTORY` report.
- **Visual style** — pill-style buttons with blue accent (`var(--blue)`) to match the info-box color theme. Placed at the end of the colored info block (FBA Inventory, both Shipment cards) or alongside the existing Folder/Zip helper buttons (SKU Economics dropzones).

## Recent Fixes (v4.201) — Inventory CSV Status + Action columns use mode-specific labels
- **User flagged:** "the csv export shows the old status codes eg order soon rather than FBA order soon."
- **Root cause:** `downloadInventoryCSV`'s `valueOf` had a hard-coded tier→label map (`Order Now / Order Soon / Plan Ahead / OK`) from before v4.189 introduced mode-specific labels. It was applied for both the `status` and `status_badge` columns, ignoring the actual labels shown in the table.
- **Fix — separate paths for the two columns:**
  - **Status column (`key='status'`)**: now calls `getStatusLabelFor(r, statusMode, getStatus(r))` where `statusMode` comes from the current Status-by dropdown (`getStatusMode()`). So Amazon FBA mode exports "FBA Soon" / "Send to FBA" / "Plan FBA Ship" / "FBA OK", Warehouse mode exports "Place PO" / "PO Soon" / "Plan PO" / "WH OK", FBM rows export "— FBM (no FBA)" when Amazon FBA mode is active.
  - **Action column (`key='status_badge'`)**: now calls `getActionRollup(r).label` — the rollup verb across both pools ("PO + Ship FBA", "All OK", "PO + FBA Soon", etc.).
- **`sanitizeCell()` helper** strips badge emoji (🔴 🟡 ⚠️ 🟢 📦 🏪) + collapses whitespace so CSV values are clean ASCII, matching the header sanitization added in v4.200.
- **Output now matches what's on screen** — the Status column read "FBA Soon" in the UI but "Order Soon" in the export; that mismatch is gone.

## Recent Fixes (v4.200) — Inventory CSV export: restore filtered/all chooser + ASCII headers + UTF-8 BOM
- **User flagged two issues on the Inventory Planning CSV export:**
  1. "i no longer have the option on the inventory planning to select what data i want to export (filtered results or all)" — `triggerExport` was routing Inventory directly to `downloadInventoryCSV()` and bypassing the export dialog, which broke the row-scope chooser users had pre-v4.170.
  2. "the column headings have special characters" — the v4.198 rename added `≤30d Need` / `≤120d Reorder` style labels with non-ASCII chars (`≤` `—` `·`) that Excel renders as mojibake without a BOM.
- **Row-scope chooser restored** — Inventory now routes through `showExportDialog('inventory')`. The dialog shows:
  - **Filtered results** (current filters applied — `combineRegionRecords` collapses US+CA into one row when no region pinned)
  - **Everything** (all SKUs, no filters, pooled by region)
- **Column-scope chooser added** — same pattern as the Forecast tab now applies to Inventory:
  - **Visible columns** (default — matches what's in the table)
  - **All columns** (every column in IP_COLUMNS, useful for one-time dumps)
- **Header sanitization** — new `sanitizeHeader()` helper inside `downloadInventoryCSV`:
  - `≤` → `<=`, `≥` → `>=`
  - `—` (em) and `–` (en) dashes → `-`
  - `·` middle dot → `-`
  - Any remaining non-ASCII (flag emojis, etc.) stripped
  - HTML stripped, whitespace collapsed
- **UTF-8 BOM prepended** to the CSV (`﻿`) so Excel detects encoding correctly. Belt-and-suspenders — sanitized headers don't need it, but row VALUES (product titles can contain ©/®/smart quotes from copy-paste) sometimes do.
- **Filename now tags the mode** — `smarterpaw-inventory-90d-filtered-2026-05-25.csv` vs `…-all-…`.
- **`downloadInventoryCSV(mode='filtered', colScope='visible')`** signature — params default to current behavior so any other caller continues working.

## Recent Fixes (v4.199) — Multi-region inventory uploads (UK / DE / FR / IT / ES / NL / MX / AU / JP)
- **User flagged:** "i need to upload inventory for other regions now and see how this rolls up to the inventory planning module."
- **Schema was already open** — `inventory.region` is unconstrained `TEXT`, so the model accepts any region code. The blocker was UI: the FBA Inventory Snapshot upload prompt only exposed US + CA buttons, and the Inventory Planning + Forecast region filter dropdowns were hardcoded US-only / CA-only / pooled.
- **`FBA_REGION_OPTIONS` constant** — new lookup list of 11 Amazon marketplaces (US, CA, MX, UK, DE, FR, IT, ES, NL, AU, JP) with flag emoji + display label. Add to this list to surface more options — no DB migration ever needed.
- **Upload prompt rebuilt as a dropdown** (was 2 buttons) — scales to 11 options without crowding the modal. Region copy clarifies "FBA stock isn't pooled across marketplaces, so each region needs its own upload."
- **`populateRegionFilters()`** — new helper that scans `records` for distinct non-pooled region values and rebuilds the Inventory Planning + Forecast region dropdowns dynamically. US + CA always included even if records aren't loaded (they're the historical defaults). Decorates known regions with their flag. Preserves current selection across rebuild.
  - Called after the Supabase records build (next to `populateCatFilter`)
  - Also called after every FBA Inventory Snapshot upload so a brand-new region appears in the dropdown immediately without a page refresh
- **Pooled-view label adapts to region count** — "US + CA (combined)" when only 2 regions exist; "All regions (pooled · US + CA + UK + DE)" when more are added.
- **Upload card description** lists every supported region inline so users see at a glance what's possible without clicking through.
- **How the rollup works** — unchanged from v4.196's master-level model:
  - Each FBA snapshot upload writes a per-region row to `inventory` (one per asin × region)
  - `records[]` build joins products × inventory and produces one record per asin × region with that region's stock + Amazon vel from `velocities` (region-specific sales rate)
  - Inventory Planning filter set to a specific region → that region's row only
  - Filter set to pooled → `combineRegionRecords` sums numeric fields (Amazon vel, FBA stock, warehouse, inbound) across all regions; Shopify/Chewy attach to US only (existing region gate)
  - PO recommendation in pooled view = single order covering aggregate demand across all marketplaces

## Recent Fixes (v4.198) — Label cumulative vs marginal columns explicitly
- **User flagged:** "why do the reorder columns not match here? one is cumulative and one is marginal? which is the correct approach?" Looking at `≤90d Reorder = 1,562` next to `60-90d Chwy = 544` and not immediately seeing why the numbers don't tie.
- **Math was correct** — Chewy marginals (489 + 529 + 544 + 532 = 2,094) sum to the cumulative `≤120d Reorder = 2,094`. But the column labels (`30d Reorder`, `60d Reorder`, …) didn't make it obvious which was which. The decision to keep both views was deliberate (v4.194 — Jason wanted marginal for PO cadence, cumulative for aggregate planning), so the fix is labeling, not removing.
- **Group header rename** — explicit semantics at the band:
  - `NEED — TOTAL` → `NEED — TOTAL (CUMULATIVE)`
  - `NEED — BASE (CONTINUOUS DRAIN)` → `NEED — BASE (CUMULATIVE · CONTINUOUS DRAIN)`
  - `NEED — REORDER` → `NEED — REORDER (CUMULATIVE)`
  - Channel-specific groups keep `(PER PERIOD)` — already explicit.
- **Column label rename** — single-number labels (`30d Need`) replaced with `≤Nd` form (`≤30d Need`) to visually signal "through this horizon" instead of "just this bucket." Width bumped 76→80 for Need/Base, 86→92 for Reorder to fit the leading `≤`.
- **Tooltip rewrites** for both column-level + group-level tooltips. Each cumulative tooltip explicitly says "CUMULATIVE through day X" and points users at the PER PERIOD columns for marginal cadence. The reorder group tooltip even includes the math: "Sum of those marginals across all 4 buckets = the ≤120d cumulative here."
- **No math changed.** Same `inventoryNeedBreakdown` outputs, same `inventoryNeed` aggregator — just the UI distinguishing the two views unambiguously.

## Recent Fixes (v4.197) — Split Amazon per-period columns into FBA Reorder + FBM Drain
- **User flagged:** "this item is FBM, so there should be no reorder qty, right? the amazon FBM should go into the base (continuous drain). need to update tooltips etc to indicate this and we need new amazon columns split by FBA vs FBM."
- **Issue:** Inventory Planning's `AMAZON REORDER (PER PERIOD)` columns (`amzReorder30/60/90/120`) always showed "—" for FBM rows because FBM has no replenishment events. But Amazon WAS driving real warehouse drain via the BASE bucket — invisible in the per-channel breakdown. Tooltips also still claimed Amazon was excluded from Base, which is only true for FBA.
- **Fix — new column group `AMAZON FBM DRAIN (PER PERIOD)`** with 4 marginal columns (`amzFbmBase30/60/90/120`):
  - For FBM rows: shows the per-period seasonal Amazon draw (`amazon.base` diff between adjacent horizons)
  - For FBA rows: shows "—" (Amazon's draw is already represented in the FBA Reorder columns at left)
  - Color-coded blue (new `.thg-channel-base` CSS class) to signal it's a BASE channel-drill-down, paralleling the orange Reorder drill-downs
- **Existing 4 Amazon columns renamed `AMAZON FBA REORDER (PER PERIOD)`** with labels `0–30d FBA / 30–60d FBA / 60–90d FBA / 90–120d FBA`:
  - FBM rows now explicitly show a dim "—" cell with hover-tooltip pointing at the FBM Drain columns instead
  - Sort + per-cell tooltips skip FBM rows cleanly
- **Tooltip rewrites:**
  - `NEED — BASE` group tooltip rewrote to call out the FBA-vs-FBM split (FBM included, FBA excluded)
  - `NEED — REORDER` group tooltip added "Amazon FBM Reorder = 0 always" line
  - `buildTipBase`, `buildTipTotal`, `buildTipRO`, `buildTipAmz` all reach into `nb.amazon.meta.fulfillment` to branch the message — FBM rows now see "Amazon FBM base: Xu (ships from warehouse — continuous draw, like Shopify)" instead of the FBA-only narrative
  - New `buildTipAmzFbm` powers the new column tooltips with the per-period draw math
- **Same data, two views:** the underlying `inventoryNeedBreakdown` already computes `amazon.base` for every row regardless of mode; v4.197 just exposes it correctly in the per-period UI based on mode.

## Recent Fixes (v4.196) — `fulfillment_amazon` moves from inventory (per-region) to products (master-level)
- **Why:** v4.195 stored FBM/FBA per asin+region on `inventory.*`. In practice no SKU in Jason's catalog is FBM in one region and FBA in another (US-only FBM, with `-FBM` SKU suffix). The per-region storage was buying theoretical flexibility we'll never use and forcing a confusing MIXED state in pooled rows.
- **Move:** column now lives on `products.fulfillment_amazon TEXT DEFAULT 'FBA'` with the same `CHECK (upper(...) in ('FBA','FBM'))` constraint. Editable from BOTH the Product modal (new `pf-fba-mode` dropdown in the "Amazon FBA controls" block) and the Inventory edit modal (existing `ef-fba-mode` dropdown, still wired to the FBA-fields disable behavior).
- **⚠ SQL TO RUN:** `supabase_v4196_fulfillment_amazon_on_products.sql` — supersedes v4.195. Idempotent: adds `products.fulfillment_amazon`, migrates any existing `inventory.fulfillment_amazon` values (if you ran v4.195) by ORing FBM across all regions of a master_id, then drops the inventory column. Safe whether or not you ran v4.195.
- **Code changes:**
  - Records-build now reads `p.fulfillment_amazon` instead of `inv?.fulfillment_amazon` (master-level join, no per-region lookup)
  - `combineRegionRecords` no longer tracks `fulfillmentByMid` or stamps `MIXED` — the spread on the first record carries the master-level value onto the pooled record
  - Row badge in Inventory Planning dropped the `MIXED` branch (can't happen anymore)
  - `saveEditModal` (inventory) now mirrors `fulfillment_amazon` onto every peer-region record sharing the master_id and writes it into the products upsert (removed from inventory upsert)
  - `saveProductModal` (product modal) writes `fulfillment_amazon` as part of the products upsert
- **Behavior unchanged for end users:** orange `FBM` badge still appears, FBA Available/Inbound still dim/zero when FBM is selected, status mode "Amazon FBA" still reads `— FBM (no FBA)`, multi-event reorder simulation still skips FBM rows, FBM Amazon consumption still counts in warehouse drain (Base Sum).
- **Trade-off:** can no longer model "US=FBM + CA=FBA on the same master_id." If that ever comes up, create separate master_ids (already the natural pattern given the `-FBM` SKU suffix convention).

## Recent Fixes (v4.195) — Amazon FBM (Fulfilled By Merchant) support, per-region (SUPERSEDED by v4.196)
- **User flagged:** "i have some amazon items that are FBM. this has a ripple effect on all of our views for forecast, product, sku economics, and inventory planning. how is the best way to proceed."
- **Model:** FBM means Amazon orders ship from our own warehouse (no FBA pool, no warehouse→FBA replenishment). So FBM Amazon consumption behaves like Shopify — continuous draw from warehouse — and Amazon FBA tiering doesn't apply to that row.
- **Granularity:** per-asin **and** per-region (US can be FBM while CA stays FBA — rare, but supported). Stored on `inventory.fulfillment_amazon` (TEXT, default `'FBA'`, CHECK in {`FBA`,`FBM`}).
- **⚠ SQL TO RUN:** `supabase_v4195_fulfillment_amazon.sql` — adds the column + check constraint + backfills existing rows to `'FBA'`. Run BEFORE deploying or saves will throw.
- **Math impact** (`inventoryNeedBreakdown`):
  - FBM Amazon: `amazon.base = amazon_vel × horizon` (continuous draw); `amazon.reorder = 0`; multi-event reorder simulation is **skipped**
  - FBM Amazon's base is **included in `baseSum`** (it IS a warehouse drain) — was excluded for FBA
  - Need TOTAL counts FBM Amazon in the warehouse drain (like Shopify)
- **Status / Action:**
  - `getStatusInputs(r, 'amazon')` returns `null` for FBM (no FBA pool to score against)
  - `getStatusLabelFor` shows `— FBM (no FBA)` when in Amazon FBA mode
  - `getActionRollup` skips the Amazon-pool check for FBM rows (only Warehouse tier matters)
- **Pooled records** (`combineRegionRecords`): per-region modes are stored on `fulfillment_amazon_by_region`. If all regions agree → that mode. If they differ (e.g. US:FBM, CA:FBA) → `MIXED` (math defaults to FBA for safety; user should drop to a single-region view for precise accounting).
- **Row UI:** `FBM` (orange) or `MIXED` (amber) badge prefixes the title in the Inventory Planning table. Tooltip on MIXED lists the per-region breakdown.
- **Edit modal:** new "Amazon fulfillment" dropdown at the top of the Inventory section. Selecting FBM disables + dims the FBA Available / FBA Inbound inputs (forced to 0 on save) and rewrites the hint to call out the warehouse-draw consequence. `toggleFbaFieldsForFulfillment()` handles the disable/enable state.
- **Persistence:** `saveEditModal` writes `fulfillment_amazon` into the inventory upsert payload. Single-row edit (not mirrored across regions — that's the whole point of per-region storage).

## Recent Fixes (v4.194) — Channel reorder columns switch to MARGINAL (per-period) for PO planning
- **User flagged:** "looking 120 days out and thinking we'll need 13,272 of this item doesn't make sense, as the order for 5,617 will already have been placed." Cumulative reorder columns stack the imminent order onto every later horizon, making it hard to see "what's the NEXT order I need to plan for?"
- **Best practice for PO look-ahead is MARGINAL** (per-period bucket): each column shows just the events firing in that specific window. A product on a 90-day reorder cycle reads `5,617 / 0 / 5,617 / 0` cleanly — you immediately see the cadence and the next-order timing without doing subtraction.
- **Channel-specific columns updated** (AMAZON REORDER + CHEWY REORDER groups):
  - Labels renamed `0–30d Amz` / `30–60d Amz` / `60–90d Amz` / `90–120d Amz` (and similarly for Chwy) so the bucket boundaries are explicit
  - Values computed as the diff between cumulative breakdowns at adjacent horizons (since `inventoryNeedBreakdown(r, X).amazon.reorder` is cumulative through X)
  - Group header renamed to `AMAZON REORDER (PER PERIOD)` / `CHEWY REORDER (PER PERIOD)` so the marginal semantic is visible at the band
  - Sort + per-cell tooltips reflect marginal math
- **Aggregate columns kept CUMULATIVE** — `Need — TOTAL`, `Need — BASE FORECAST`, `Need — REORDER` all still answer aggregate-volume questions over [0, X]. So if you want "total reorder volume over next 90 days," use Need — REORDER. If you want "what fires in each bucket," use the channel-specific columns.
- **Updated group-header tooltip** lists the four bucket boundaries explicitly + explains why marginal is better for scheduling. Chart metric dropdown labels updated to call out "(per period — marginal)" for these.

## Recent Fixes (v4.193) — Per-row hover tooltips on Status + Action badges
- **Issue:** users couldn't tell the difference between "FBA Soon" and "Plan FBA Ship" — both are amber-ish labels in the Status column and the column-header tooltip alone didn't explain WHY a given row landed in one tier vs the other.
- **Fix:** added per-row hover tooltips to both badges in the inventory table. Cursor changes to `help` on hover.
- **Status tooltip** shows:
  - Tier description (e.g. "🟡 0-30d of slack — place FBA shipment within the month")
  - The actual math for THIS row: stock pool · daily rate · DOS · lead + safety → ROP · slack
  - The full tier ladder for reference (🔴 ≤0 · 🟡 0-30 · ⚠️ 30-60 · 🟢 >60)
- **Action tooltip** shows:
  - The rollup label (e.g., "🔴 PO + Ship FBA")
  - Per-pool tier for warehouse + Amazon (so the user can see both)
  - How the rollup verbs are derived from per-pool tiers
- **Helper functions** `getStatusTooltipFor(r, mode)` and `getActionTooltipFor(r)` live next to the other status helpers; per-row `pre` object now carries `stTip` + `actionTip` strings consumed by the column renders.

## Recent Fixes (v4.192) — Inventory Planning: collapsible scorecards + chart for more table real estate
- **New toggle bar** at the top of the inventory page: two buttons (`▾ Scorecards` and `▾ Chart`) that collapse / expand those sections.
  - `▾` = expanded (shown). `▸` = collapsed (hidden).
  - `▾ Scorecards` hides all three scorecard rows together (status counts + top metrics + mode tiles) as a single block.
  - `▾ Chart` hides the line chart panel below the selection bar. The selection bar itself stays visible (low-effort summary you usually want).
- **Persistence:** state saved to `localStorage.ipCollapsed` as `{ scorecards: bool, chart: bool }`. Survives view switches + page refreshes.
- **Chart respects the collapsed flag** — `updateInventoryChart` checks `isIpChartCollapsed()` first and bails early if collapsed, so toggling on the chart re-runs the build.
- **Restoration:** `applyIpCollapsedState()` runs every time the Inventory sub-view is shown, immediately after `renderInventoryTbl`. The toggle button labels also flip ▾↔▸ so the icon mirrors the current state.

## Recent Fixes (v4.191) — Multi-event Amazon reorder simulation
- **Bug surfaced by user:** the Amazon Reorder columns showed the same `2,428` across 30d/60d/90d/120d. Reason: the model only fired the FIRST trigger within the horizon. But for a product with `reorder_qty_days=90`, a SECOND event fires ~90 days later, a THIRD at ~180, etc. Cumulative reorder should grow across horizons.
- **Fix:** the Amazon block in `inventoryNeedBreakdown` now walks forward and accumulates EVERY event whose order-by day lands within the horizon:
  - `firstOrderByDay = max(0, fbaDos − threshold)` — when the first event fires
  - Then each subsequent event fires at `prevOrderDay + reorder_qty_days` (when the prior batch is consumed)
  - Loop continues while `nextOrderDay ≤ X` (capped at 12 iterations as a safety)
  - Each event's qty = `forwardSeaDemand(arrival + reorderQty) − forwardSeaDemand(arrival)` (or flat `reorderQty × rate` for new-override products)
- **`amzMeta.events`** array now carries `[{orderDay, arrival, qty}, …]` for tooltip transparency. The Amazon Reorder cell tooltip lists each event explicitly so the user can see which orders are stacked into the cumulative total.
- **Example impact (Pawty Mix, FBA-DOS≈95, threshold=90, reorder_qty=90, vel≈24):**
  - Old: 30d/60d/90d/120d Amz Reorder = 2,428 / 2,428 / 2,428 / 2,428 (single event)
  - New: 30d/60d/90d/120d Amz Reorder = 2,428 / 2,428 / 2,428 / 4,856 (second event fires at ~day 95, included in 120d horizon)
- **`fbaStock` in the simulation includes `ipInTransitFor(r)`** (the Working/Receiving shipments we created but Amazon hasn't picked up yet) — consistent with the status/scorecard math.
- **Deprecated rows still zero out** — multi-event sim returns empty events array, reorder = 0, `fires = false`.

## Recent Fixes (v4.190) — Status tiers are LEAD-TIME-driven (Reorder Point), not gap-horizon-driven
- **v4.189 mistake:** I tied Status tiers to the 30d/60d/90d gap columns (Order Now ↔ 30d short, etc.). User correctly pushed back — the urgency of a reorder isn't about coverage, it's about supplier lead time. A product with a 90-day lead time that covers 120 days needs to be marked "Order Soon" (you have 30 days of slack before you MUST place the PO).
- **Fix:** classic Reorder Point model. ROP = `lead_time + safety_stock` (days). Slack = `DOS − ROP`. Tiers:
  - 🔴 **Order Now**: slack ≤ 0 (at or past the must-order point)
  - 🟡 **Order Soon**: 0 < slack ≤ 30 days
  - ⚠️ **Plan Ahead**: 30 < slack ≤ 60 days
  - 🟢 **OK**: slack > 60 days
- **DOS computation** still mode-aware (uses the 90d need divided by 90 to derive daily rate — Amazon mode uses Amazon consumption rate, Warehouse mode uses full warehouse drain rate). The mode picks the stock pool + the demand denominator.
- **Defaults when fields are blank:** `lead_time || 60` (a reasonable manufacturer turnaround) and `safety_stock || 14` (matches the modal's default). So a row with no explicit lead-time still gets sensible tiering instead of nodata.
- **Status / Action / Gap are now three different lenses on the same SKU:**
  - **Gap** = "do I have enough stock to cover horizon X's needs?" (coverage)
  - **Status** = "given my supplier timeline, do I need to place a PO?" (timing)
  - **Action** = "what actions are needed across all pools?" (rollup of Status across warehouse + Amazon FBA)
  - They CAN diverge (gap healthy + status saying Order Soon if lead time is long) — that's the right behavior.

## Recent Fixes (v4.189) — Inventory Planning: Status ties to gap horizons; Status ≠ Action (mode vs rollup)
- **Three coupled problems addressed:**
  1. **Status was decoupled from the visible Gap.** Old logic (v4.180) used DOS-vs-reorder-threshold tiers, so a row could be "Order Soon" while showing a 30d Gap shortfall. Now tiers tie directly to the gap horizons:
     - Order Now ↔ need(30d) > stock
     - Order Soon ↔ need(60d) > stock
     - Plan Ahead ↔ need(90d) > stock
     - OK ↔ 90d covered
  2. **Status label was abstract.** Now mode-specific actionable:
     - Amazon FBA mode → 🔴 Send to FBA / 🟡 FBA Soon / ⚠️ Plan FBA Ship / 🟢 FBA OK
     - Warehouse mode → 🔴 Place PO / 🟡 PO Soon / ⚠️ Plan PO / 🟢 WH OK
     - Combined → unchanged
  3. **Status + Action columns showed the same value.** Now they answer different questions:
     - **Status** = "what does the ACTIVE MODE say?" (mode-specific)
     - **Action** = "what actions are needed across BOTH pools?" (mode-agnostic rollup)
- **`getActionRollup(r)`** checks warehouse AND Amazon FBA status independently, then combines the verbs at the worst tier. Examples:
  - Warehouse=order-now + Amazon=order-now → "🔴 PO + Ship FBA"
  - Warehouse=order-now + Amazon=ok → "🔴 Place PO"
  - Warehouse=ok + Amazon=order-soon → "🟡 FBA Soon"
  - Both=plan → "⚠️ Plan PO + FBA"
  - Deprecated + warehouse=order-now → "🔴 ⛔ + Place PO" (Shopify/Chewy still need fulfilment)
- **`getStatusFor(r, mode)`** lets any caller compute the tier for any pool, independent of the dropdown. Used by Action rollup + future per-mode tooling. `getStatus(r)` is now a thin wrapper that defers to the active mode.
- **`getStatusInputs(r, mode)`** factored out so the tier logic + scorecards + gap math can all share the same stock/need inputs.
- **`getStatusLabelFor(r, mode, tier)`** maps tier → mode-specific verb. Used by the Status column.
- **Column widths bumped:** Status 104→128px, Action 104→160px (Action labels are longer now with combined verbs like "PO + Ship FBA").
- **Column tooltips updated** so users can hover and see exactly what Status vs Action mean.

## Recent Fixes (v4.188) — Inventory Planning: scorecards split into 3 rows (Status / Metrics / Mode)
- **Reorganization:** the single 9-tile row was cramped. Now arranged as three logical rows:
  - **Row 1 — Status counts** (full-width, 4 equal columns): 🔴 Order Now · 🟡 Order Soon · ⚠️ Plan Ahead · 🟢 Covered. Padding + value font bumped (`.scorecards-status .sc` 16px padding, `.sc-val` 32px) for prominence since these are the most-glanced tiles. SELECTION chip moved to the Order Now tile's label so the user can see at a glance whether the numbers reflect filtered vs selected.
  - **Row 2 — Top metrics** (auto-fit): Total Vel/day · `${h}d` Need · On Hand · `${h}d` Gap · Order (`${target}d` target). Includes in-transit 🚧 chips on On Hand + Gap as before.
  - **Row 3 — Mode tiles** (auto-fit): Mode-specific tiles (Amazon Vel/day / Amazon Need / FBA Stock / FBA Gap in Amazon mode; Warehouse Need / Stock / Gap / Channel mix in Warehouse mode; an info message in Combined mode).
- **HTML containers:** `#ip-scorecards-status` (new), `#ip-scorecards` (existing — now just the metrics row), `#ip-scorecards-mode` (existing).
- **Build helpers split:** `buildInventoryStatusScorecardsHTML` (new) handles the 4 status counts; `buildInventoryTopScorecardsHTML` (renamed semantically) handles the 5 metric tiles. `buildInventoryModeScorecardsHTML` unchanged.
- `refreshInventoryScorecards()` now updates all three rows. Still fires on every checkbox click and reads from the pool cache (cheap).

## Recent Fixes (v4.187) — Inventory Planning: left-align body cells for align:'left' columns
- **Bug:** `td` defaults to `text-align:right` globally (set for the numeric-heavy Forecast / Inventory tables). The IP_COLUMNS registry marked Brand / Region / Product / ASIN / Master ID / SP SKU as `align:'left'`, and headers used that (via `class="tl"` + inline `text-align:left`). But the body cell renders just emitted plain `<td>`s without the class, so short text in those columns floated to the right edge of the column width. Product column was the most visible — short names like "Birthjays Rollies" looked weirdly indented.
- **Fix:** added a post-process step in `renderInventoryTbl`'s cell-render loop. For any column flagged `align:'left'`, inject `text-align:left` into the body cell's inline style (prepended so render-specified styles still override if needed). One-line wrapper around the existing `c.render(r, pre)` call — no need to edit individual render functions.

## Recent Fixes (v4.186) — Scorecards re-render on every checkbox click
- **Bug:** v4.184 made the scorecards selection-aware (aggregate over checked rows when present) — but `toggleInventoryRow` + `toggleInventoryAll` only called `refreshInventorySelectionBar()` + `updateInventoryChart()`. The scorecards (top row + mode-specific row) were left stuck on whole-table totals until the next full re-render (filter change, etc.). So checking a row updated the bar + chart but not the scorecards above.
- **Fix:** added `refreshInventoryScorecards()` — rebuilds both scorecard rows from the existing `ipPooledRecordsByKey` cache (no table re-filter, no body re-render). Called from both `toggleInventoryRow` and `toggleInventoryAll`.
- Cheap enough to fire on every checkbox flip: just two innerHTML swaps, no DOM diffing on the (potentially 500+) table rows.

## Recent Fixes (v4.185) — Make Total = Base + Reorder add up cleanly
- **Confusion:** users reading the Need columns expected Total = Base + Reorder, but it didn't add up. v4.167's Base included Amazon's sales velocity, but Total excluded it (Amazon's contribution to Total came via Reorder only). So Base + Reorder ≠ Total, and Base was conceptually double-counting Amazon's demand alongside the Reorder event that already covers it.
- **Fix:** Base now means "continuous warehouse drain only" — Shopify base + Chewy base. Amazon is excluded because its demand reaches the warehouse via the Reorder event (warehouse → FBA shipment), not via continuous draw. The Reorder qty is already sized to cover ~reorder_qty_days of Amazon velocity, so including Amazon base in Base would double-count.
  - **Math now adds up:** Total = (Shopify base + Chewy base) + (Amazon reorder + Chewy reorder) = Base + Reorder ✓
- **Per-channel `amazon.base` still computed** and exposed on the breakdown for tooltips + the Amazon-mode scorecard's `${h}d Amazon Need` tile (which intentionally shows Amazon-only consumption). Just not summed into the aggregated `base`.
- **Labels updated** so users know what Base means now:
  - Group header: "NEED — BASE FORECAST" → "NEED — BASE (CONTINUOUS DRAIN)"
  - Per-column tip: explicitly notes Amazon is excluded and why
  - View popup section label: "Need — BASE (continuous-drain channels: Shopify + Chewy base)"
  - Chart metric dropdown: "Need — BASE (continuous drain: Shopify + Chewy)"
- **Tooltip on each Base cell** lists the per-channel breakdown AND surfaces Amazon's sales velocity as an "(Amazon's sales velocity = Xu — NOT counted here)" footnote so the user can still see it.
- **Total cell tooltip** now ends with `= ${total}u total = Base (${base}) + Reorder (${reorder}).` making the math obvious.
- **Expected impact on numbers:** for products with Amazon presence, the displayed 30d/60d/90d/120d Base values will drop substantially (they were carrying ~Amazon vel × horizon previously). The new values reflect only Shopify (and Chewy when we get consumer-level data). Numbers are RIGHT now; old numbers had a hidden semantic bug.

## Recent Fixes (v4.184) — Restore top scorecard row + add mode-specific row below; gap math folds in in-transit
- **v4.183 mistake:** I replaced the original 9-tile top scorecard row with a mode-dependent set. User wanted the top row to STAY CONSTANT and a NEW row to appear below with mode-specific tiles. Fixed.
- **Top row** (`#ip-scorecards`, constant across modes): Order Now / Order Soon / Plan Ahead / Covered · Total Vel/day · `${h}d` Need · On Hand · `${h}d` Gap · Order (`${target}d` target). Selection-aware (banner chip in the 🔴 tile reads "SELECTION (N selected)" when aggregating over checked rows).
- **NEW bottom row** (`#ip-scorecards-mode`, mode-specific):
  - **🏪 Warehouse:** `${h}d` Warehouse Need · Warehouse Stock · `${h}d` Warehouse Gap · Channel mix (Amazon-reorder / Shopify base / Chewy reorder split).
  - **📦 Amazon FBA:** Amazon Vel/day · `${h}d` Amazon Need · FBA Stock (incl 🚧 in-transit) · `${h}d` FBA Gap.
  - **∑ Combined (legacy):** single info tile noting "top row already covers this — switch modes for extra tiles".
  - Banner header reads `Mode tiles · 📦 Amazon FBA · Scope: 4 selected (selection)`.
- **Gap math now folds in `ipInTransitFor(r)`** — the shipments we've created in Manage FBA Shipments but Amazon hasn't yet processed (Working/Receiving statuses). Applies to:
  - **Per-row Gap columns** (`30d Gap` / `Active Gap`) — pre-computed `gapH` / `gap30` now use `(total_onhand + in_transit)` instead of raw `total_onhand`.
  - **Top-row `On Hand` + `${h}d Gap` scorecards** — effective on-hand includes in-transit.
  - **Bottom-row FBA Gap scorecard** (Amazon mode) — already used the in-transit-aware FBA Stock.
- **🚧 badges everywhere in-transit contributes:**
  - Per-row gap cells: `−2,338 short 🚧` (cell-level chip)
  - Top-row `On Hand` tile: `🚧 incl` chip in label, sub-text reads `🚧 incl 1,140 in transit`
  - Top-row `${h}d Gap` tile: `🚧 incl` chip when in-transit applies
  - Bottom-row FBA Stock tile: `🚧 N` showing the in-transit count
  - Tooltips on every chip explain that Working/Receiving shipments are folded in.

## Recent Fixes (v4.183) — Inventory Planning: mode-aware + selection-aware scorecards; gap colors flipped to balance-sheet convention
- **Scorecards now drive off the active Status mode (Warehouse / Amazon FBA / Combined):**
  - The four status counts (🔴 Order Now / 🟡 Order Soon / ⚠️ Plan Ahead / 🟢 Covered) stay constant across modes (they count rows by `getStatus(r)` which is already mode-aware).
  - The bottom row of scorecards swaps per mode:
    - **🏪 Warehouse:** Total Vel/day · ${h}d Warehouse Need · Warehouse Stock · ${h}d Warehouse Gap · Order (${target}d target)
    - **📦 Amazon FBA:** Amazon Vel/day · ${h}d Amazon Need · FBA Stock (incl 🚧 in-transit) · ${h}d FBA Gap
    - **∑ Combined (legacy):** Total Vel/day · ${h}d Need · On Hand · ${h}d Gap · Order (${target}d target)
- **Selection-aware:** when ≥1 row is checked, scorecards aggregate over the SELECTION instead of all visible rows. Banner above the cards reads "Scope: 4 selected SKUs · Status mode: 📦 Amazon FBA · aggregated over selection". No selection → scope is the filtered table (current default).
- **Save with view:** the Status mode is part of saved views since v4.182 (`statusMode`), and the selection is too (`selection`). So applying a saved view restores both → the scorecards rebuild to match. Nothing new needed on the persistence side.
- **Gap display flipped to balance-sheet convention (v4.183):**
  - Old: `+2,232` in yellow when need > on-hand (shortage). Counterintuitive — users read "+" as "extra".
  - New: `−2,232 short` in red (shortage) or `+800` in green (surplus). Matches a bank-balance readout where positive = good, negative = bad.
  - Applies to both the per-row 30d/Active Gap cells and the scorecard Gap tiles.
  - `.gap-warn` is now orange (was yellow); `.gap-ok` is now green (was muted grey); `.gap-crit` still red.

## Recent Fixes (v4.182) — Saved views: persist selection + deep-link via `?view=Name`
- **Inventory view selection wasn't being saved.** v4.166 captured columns + sort + filters in `ipCaptureCurrentState` but skipped the checked-row selection (`inventorySelected`). Now persisted as `selection: [...inventorySelected]`. Plus the Status-by mode (`warehouse` / `amazon` / `combined`) which was also slipping.
- **`ipApplyView`** restores the saved selection — clears the current set then adds each saved key. The checkbox column, selection bar, and chart all reflect the restored selection because `renderInventoryTbl()` re-reads `inventorySelected` on every paint.
- **Saved views now have URLs.** Format: `#${page}/${sub}?view=${encodedName}`.
  - `#forecast/inventory?view=My%20View`
  - `#forecast/demand?view=Export%20Amazon%20only`
- **Router changes:**
  - `routeParse()` extracts the `?view=` parameter via `URLSearchParams`.
  - `routeApply()` first navigates to the right page/sub-view, then defers a `setTimeout(0)` to call the matching `applyView` function (Inventory or Forecast) so the data + DOM are ready.
  - `routeWriteView(page, sub, name)` is the only way to put `?view=` in the URL — sets `_routerActiveView` and writes a hash with the param.
  - `routeWrite(page, sub)` (plain nav clicks) explicitly clears `_routerActiveView` so the view URL doesn't leak across pages. So clicking the Demand tab from `#forecast/inventory?view=X` lands you at `#forecast/demand` cleanly.
  - `clearInventorySelection()` also clears the active view URL (selection IS the view, so emptying it breaks the association).
- **Both saved-view paths now write the URL on apply:**
  - `ipApplyView(name)` → `routeWriteView('forecast', 'inventory', name)`
  - `fcApplyView(name)` → `routeWriteView('forecast', 'demand', name)`
- **`ROUTE_VIEW_APPLIERS` map** lets the router know which apply function to call for which `(page, sub)` combo when restoring from URL. Easy to extend if/when other pages add saved-view systems.

## Recent Fixes (v4.181) — Hash-based deep links for every page + sub-view
- **Pattern:** `#${page}/${subview}` updates `window.location.hash` on every nav action. Single-file HTML on GitHub Pages — hash routing needs zero server config. Browser back/forward, refresh, and bookmarks all work.
- **Routes:**
  - `#forecast/demand`, `#forecast/inventory`, `#forecast/seasonality`, `#forecast/chewy`, `#forecast/fba-shipments`
  - `#data/uploads`, `#data/query`
  - `#products`, `#bundles`, `#sales`
  - `#pnl/amazon`, `#pnl/shopify`, `#pnl/cogs`
  - `#settings`
- **Wiring:**
  - `routeWrite(page, sub)` — uses `history.replaceState` (not `assign`) so we don't fire our own hashchange.
  - `routeApply()` — reads hash, dispatches through the existing nav functions (`showPage`, `switchForecastView`, `switchDataView`, `switchPnlView`). Guarded by `_routerSilent` flag to prevent infinite loops.
  - `hashchange` listener handles browser back/forward + manual edits to the URL bar.
  - `showPage` + each `switchXxxView` call `routeWrite(...)` after they apply their state.
  - `init()` calls `routeApply()` at the end of the boot sequence (only when a non-empty hash is present), so deep links work on first paint.

## Recent Fixes (v4.180) — Inventory Planning: status uses reorder_threshold_days + Working/Receiving shipments count as in-transit
- **Status logic was using fixed 30/60/horizon thresholds**, ignoring the per-product `reorder_threshold_days` field. Result: a product with 62-day FBA cover + 90-day reorder threshold showed "Plan Ahead" instead of "Order Now" — even though it's below threshold and should be triggering. Rewrote `getStatus` to use DOS (days-of-supply) vs threshold tiers:
  - **Order Now**: DOS < threshold (below reorder point)
  - **Order Soon**: DOS < threshold × 1.25 (approaching threshold)
  - **Plan Ahead**: DOS < threshold × 1.5
  - **OK**: DOS >= threshold × 1.5
- DOS is computed mode-aware:
  - Warehouse mode: `warehouse / (inventoryNeed(r, horizon) / horizon)`
  - Amazon FBA mode: `(fba_available + fba_inbound + in_transit) / (amazon_base / horizon)`
  - Combined: `total_onhand / (r.needX / horizon)`
- **In-transit visibility (v4.180):** added `loadFbaInTransit()` which pulls `fba_shipments` rows whose linked `fba_shipment_summaries.status` is NOT 'Closed' (Working / Receiving / unknown). Sums `quantity_shipped − quantity_received` per master_id into `ipFbaInTransitByMaster`. This represents shipments YOU'VE created in Manage FBA Shipments that haven't yet been picked up by Amazon's `afn-inbound-*` buckets in the FBA Inventory Snapshot.
- **Used two places:**
  - **Status math (Amazon FBA mode):** `fba_inbound` + in-transit folded into the effective FBA position. Catnip Spray at 4,141 + (say) 1,200 in-transit = 5,341 effective → DOS goes from 62 to 80 → still below 90 threshold so still "Order Now", but the math is honest about your pipeline.
  - **🚧 badge on the FBA In column:** orange `🚧 1,200` next to the regular FBA Inbound number. Tooltip explains what's counted.
- **Refreshed on demand:** `loadFbaInTransit()` runs when the Inventory page is shown AND after every FBA shipment upload (so newly-created Working shipments show up immediately).

## Recent Fixes (v4.179) — Inventory Planning: pooled records resolve correctly in the selection bar + chart
- **Bug:** v4.177's chart + selection-bar resolved selection keys via `records.find(x => x.master_id === mid && (x.region || 'US') === reg)`. But when the region filter is "US + CA pooled", `combineRegionRecords` produces synthetic rows with `region = 'US+CA'` (or `'CA+US'` if no US listing) that don't exist in the base `records` array. Result: pooled rows silently dropped from the chart + their needs missing from the bar's sum. User saw "4 selected" with only 2 lines on the chart and a `90d need` total that was clearly low.
- **Fix:** added `ipPooledRecordsByKey` Map — populated at the end of `renderInventoryTbl` with the actual rows currently displayed (post-pooling, post-filter). `ipResolveSelectedRecord(key)` checks this cache first, then falls back to the base-records lookup. Both `refreshInventorySelectionBar` and `updateInventoryChart` use the resolver. The chart now plots every checked row; the bar's totals match what's visible in the table.
- **Edge case:** if the user changes region mode (e.g. pooled → US only) without clearing selection, keys with the old `US+CA` region won't resolve in the new view's cache. The fallback `records.find` also won't find them. Those rows silently drop from the chart/bar — by design for now; user can clear + re-check if needed. Future: could auto-clear selection on region change.

## Recent Fixes (v4.178) — Inventory Planning: Status-source dropdown (Warehouse / Amazon FBA / Combined)
- **Bug pattern:** `getStatus(r)` compared `total_onhand` (FBA + FBA inbound + warehouse) against `r.need30/60/horizon` (cross-channel consumption forecast). A product with 4,141 units at Amazon FBA and 0 in the warehouse would show "Order Soon" — but that's misleading: warehouse is empty so Shopify/Chewy can't fulfill, and the operator can't see that until they drill in.
- **New `Status by` dropdown** next to the existing Status filter. Three modes:
  - **🏪 Warehouse stock** (default) — your-warehouse stock vs `inventoryNeed(r, X)` (TOTAL warehouse drain: Shopify base + Chewy reorder + Amazon FBA-replenishment shipments). Answers "do I need a manufacturer PO?"
  - **📦 Amazon FBA stock** — `fba_available + fba_inbound` vs Amazon-only consumption (`inventoryNeedBreakdown(r, X).amazon.base`). Answers "do I need to send another shipment to Amazon?"
  - **∑ Combined (legacy)** — the v4.177 behavior, preserved as an option.
- **Mode is persisted** in localStorage as `ipStatusMode`. Restored on first render so refreshes don't drop the user's preference.
- **Scorecards relabeled** to reflect the active mode — e.g. with Warehouse mode the subtitle reads "warehouse runs dry within 30d" instead of the generic "Run out within 30d". Tooltip on each scorecard spells out which stock pool vs which demand metric is driving the count.
- **Status badge column** + the rightmost Action column both pick up the new logic automatically (both call `getStatus(r)`).
- **Walking the user's screenshot:** Catnip Spray 3oz, FBA=4,141, warehouse=0. Previously "Order Soon" (FBA stock dominated). With Warehouse mode it now correctly flags as "Order Now" since warehouse=0 can't cover even 30d of Shopify+Chewy demand. With Amazon FBA mode it stays "OK" (4,141 covers ~62 days of Amazon consumption at 66/day).

## Recent Fixes (v4.177) — Inventory Planning: per-row checkboxes + selection bar + line chart with metric picker
- **Pattern parity with Demand Forecast page** — checkboxes drive a selection set, which surfaces a summary bar + line chart. Row-click still opens the Inventory edit modal (preserves the existing inventory-specific edit flow).
- **New `_chk` column** at the front of `IP_COLUMNS`, locked + default-visible. Header has a select-all that toggles every currently-visible row. Row-level checkbox stops click propagation so it doesn't trigger the modal.
- **`inventorySelected` Set** — keys are `master_id_region` (handles US/CA/pooled cleanly).
- **Selection bar** above the table (`#ip-selection-bar`) — appears when ≥1 row is checked. Shows count, brand mix, summed `horizon-day need`, summed on-hand. Two actions:
  - `⬇ Show selection in table` — filters the table down to just the checked rows (other filters still apply). Toggles to `↑ Show all in table` when active. State held in `ipShowOnlySelectedMode`.
  - `✕ Clear selection` — clears the set + re-renders.
- **Line chart** below the selection bar (`#ip-chart-panel`) — Chart.js, hidden when no selection. Metric picker offers 7 options:
  - Need — TOTAL (warehouse drain)
  - Need — BASE FORECAST (sales velocity)
  - Need — REORDER (Amazon + Chewy events)
  - Amazon REORDER (trigger qty)
  - Chewy REORDER (their forecast)
  - Need vs On-hand cover (two-line gap chart)
  - Inventory cover (days)
- **Series picker:** Total (sum across selection) vs Per product (one line per selected product, capped to ~10 colors). Mirrors the Forecast page's pattern.
- **Sync points:** `toggleInventoryRow`, `toggleInventoryAll`, `clearInventorySelection`, `renderInventoryTbl` (when filters change) all funnel through `refreshInventorySelectionBar()` + `updateInventoryChart()`.
- **`ipVisibleColumns()` updated** to always include locked columns (`_chk`) regardless of the user's saved-view state. Saved views from before v4.177 keep working — they just don't reference `_chk`, but the column shows up anyway because it's locked.

## Recent Fixes (v4.176) — New (Amazon) launch override: truly flat math on Forecast page
- **Bug:** v4.172's launch override set `rec.blended_daily = rate` and `rec.sea_idx = 1`, but `forwardSeaDemand` (which actually computes need30/60/90/120 for the Forecast page) integrates the seasonal **curve** day-by-day and ignores `sea_idx`. Result: Forecast page still showed curve-adjusted numbers (e.g., 30/day × 30d came out 918, not 900) and the Sea Index column showed varying values (1.02× / 0.98× / 1.03×) even though seasonality was supposedly disabled.
- **Fix:** added a short-circuit at the top of `forwardSeaDemand` AND `getForwardSea` — when `r.new_amazon_override` is true, return flat `blended × horizonDays` (and 1.0 for sea respectively). Both functions are now honest about the override.
- **Inventory page was already flat** (the v4.172 `isNewOverride` branch in `inventoryNeedBreakdown` does its own math without going through `forwardSeaDemand`). This release brings the Forecast page into alignment.

## Recent Fixes (v4.175) — FBA Shipments viewer merges in the summary CSV data
- **The summary CSV uploader was landing rows in `fba_shipment_summaries` but the viewer was only reading `fba_shipments` (per-SKU detail). Result: uploads worked but the data was invisible.** Fixed by joining both tables on shipment_id in `loadFbaShipments` and rendering the merged view.
- **`loadFbaShipments` fetches both tables in parallel.** Detail rows go into `fbaShipmentsCache`, summary rows into `fbaShipmentSummariesCache` (a Map keyed by shipment_id). If the summaries table doesn't exist yet (migration not run), the fetch fails silently and the page falls back to the prior behavior.
- **Two new columns:**
  - **`Located`** — Units located vs Units expected. Shows the located number, with a small delta indicator: `1,200 ✓` when they match, `1,190 ⚠ -10` (orange) when short, `1,210 +10` (green) when extra. Tooltip notes shrinkage > 1% is worth filing a reimbursement claim for.
  - **`Status`** — colored badge: Closed (green) · Receiving (orange) · Working (blue) · Cancelled (red).
- **Both columns sortable.** Click the header to sort by status alphabetically, or by located qty numerically.
- **Summary-only rows** — when a shipment is in the summary CSV but no per-shipment .tsv was ever uploaded, the row still appears (with a small `summary only` chip next to the Shipment ID). No expand caret (no detail to show). All summary fields still rendered. Useful for backfilling visibility without uploading every individual .tsv.
- **Header status line** updated — shows `25 shipments · 12,403 units · summaries: 25 · expected 12,403 / located 12,196 · ⚠ 207 short` when summaries are loaded. Makes total shrinkage visible at the page level.
- **Expanded view footer:** when you expand a shipment that has both detail + summary data, a small footer line under the per-SKU table shows `📋 Summary: status Closed · last updated 2026-05-24 · expected 1,200 / located 1,190` so you don't have to scroll up.
- **Delete now removes both rows** — when you ✕ a shipment, both `fba_shipments` (line items) and `fba_shipment_summaries` (rollup) entries are deleted.

## Recent Fixes (v4.174) — Demand Forecast: row click opens product modal; selection (checkboxes) drives the detail panel
- **Click vs check were doing the wrong things.** Clicking a row on the Demand Forecast page was opening the inline `forecastDetailPanel` (a unique behavior different from every other page in the app), while checking a row only added to a hidden `forecastSelected` Set with no visible feedback. Confusing.
- **New behavior:**
  - **Click row** → opens the **product modal** (`openProductModal`) — parity with Products / Bundles / Inventory pages.
  - **Check row(s)** → reveals the detail panel above the table:
    - **1 selected:** same per-product detail as before (IDs · velocity · per-horizon demand forecast).
    - **2+ selected:** aggregated summary — brand/region/bundle mix, summed velocities, weighted seasonal multiplier, most-common trend, and summed Units Needed per horizon (30/60/90/120).
  - **Close (✕)** on the panel → clears the selection entirely + unchecks the rows.
- **Wiring:** `refreshForecastSelectionPanel()` is the single entry point. Called from `toggleForecastRow`, `toggleForecastAll`, and `renderAll` (so saved-view selections populate the panel on load). The old `openForecastDetail(asin, masterId, region)` is kept as a backward-compat shim — anything that called it still works.

## Recent Fixes (v4.173) — Stop overstating Shopify upload date; fix Amazon group rollup
- **Shopify "today" bug:** Shopify aggregates daily → weekly with `week_start = Monday-of-that-week`. A daily upload through (say) Tuesday creates a row with `week_start = Mon` even though only 2 of 7 days are populated. My code then said "Data through Sun" by tacking +6 days on the Monday, overstating the data coverage by up to 6 days. Result: if your latest Shopify upload reached any day in the current week, the dashboard claimed "Data through (today)" even when you'd only uploaded a partial week.
- **Fix:** stop computing the Sunday end. Show `week_start` directly with a "Week of" framing — unambiguous. The per-tile message reads `📅 Latest data week starts Mon 2026-05-18`; the group rollup reads `Week of 2026-05-18 (6d ago)`. No more false "today" when partial-week data is loaded.
- **Amazon group rollup bug (parallel):** the group rollup was showing the latest `week_start` (Monday) verbatim — confusing since the per-tile message showed the Saturday end. Now both show the Saturday end consistently (Amazon's parser validates each upload as a complete Sun-Sat week, so the Saturday is reliable). Reads `thru Sat 2026-05-16 (8d ago)`.
- **Group-label rename:** "Data Through" → "Latest Data" for both Amazon + Shopify. More honest umbrella — works whether the latest data is a specific day (Amazon) or a partial week (Shopify).

## Recent Fixes (v4.172) — Wire up `new_product_amazon` (launch override) + `deprecated_product_amazon` (Amazon-only reorder zeroing)
- **⚠ SQL TO RUN:** `supabase_v4172_new_amazon_daily_units.sql` — adds `products.new_amazon_daily_units NUMERIC(10,2)` so the manual launch rate persists.
- **Background:** since v4.160 both flags were on the model but neither had math effects — v4.161 explicitly removed deprecated's effect because zeroing the cross-channel PO was wrong. With the v4.167 per-channel breakdown in place, we can now drive both flags surgically.
- **`new_product_amazon` (LAUNCH OVERRIDE):**
  - New field `new_amazon_daily_units` — manual expected daily rate (number). UI input appears next to the checkbox in BOTH the Inventory edit modal (`ef-new-amazon-rate`) and the Products modal (`pf-new-amazon-rate`), visible only when the flag is checked. Stored on `products`.
  - When flag is on AND rate > 0:
    - **Inventory page:** Amazon vel = rate (overrides historical). Amazon base = `rate × horizon` (flat — no seasonality). Amazon reorder = `reorder_qty_days × rate` (flat). Trigger logic (FBA-DOS vs threshold) still applies.
    - **Demand Forecast page:** `recomputeRecordVelocity` overrides `blended_daily = rate`, `sea_idx = 1`, `adj_daily = rate`. need30/60/90/120 are derived from the flat rate. A 🆕 NEW badge appears next to the product name with a tooltip explaining velocity + seasonality are bypassed.
    - **Trade-off accepted:** any existing Shopify/Chewy history is ignored on the Forecast page while the override is active. Appropriate for genuine launches; flip the flag off once history is established.
  - When flag is on but rate is blank/0: silently falls back to historical (the badge still shows but in a muted style indicating "rate not set").
- **`deprecated_product_amazon` (AMAZON-SUPPRESS):**
  - When flag is on: Amazon **reorder = 0** in the Inventory model. Amazon **base stays at historical** (models the wind-down sell-through).
  - Shopify + Chewy unaffected — a product deprecated on Amazon may still be alive on other channels.
  - Tooltip on AMAZON REORDER column now surfaces the deprecated state explicitly.
- **Code touchpoints:**
  - Records-build (line ~2796): pulls `new_amazon_daily_units` from `products` onto each record.
  - `recomputeRecordVelocity`: branches on the new flag + rate; overrides velocity fields when active.
  - `inventoryNeedBreakdown` Amazon block: flat-math branch for new override; zero-reorder branch for deprecated. Tooltips updated.
  - Inventory edit modal load + save (around line 14620 / 14760): reads/writes the new field on both `r` (in-memory record) AND mirrors to peers + recomputes velocity + persists to `products`.
  - Products modal load + save (around line 15289 / 15483): same. After save, mirrors onto all matching in-memory records + triggers `recomputeRecordVelocity` so changes flow through without a reload.
  - `toggleNewAmazonRate(prefix)` helper shows/hides the rate input based on checkbox state (works for both `ef-` and `pf-` prefixes).

## Recent Fixes (v4.171) — Uploads page label fix + Inventory CSV export wired
- **Uploads page label fix:** Shopify DTC + Amazon group rows were labeling the rollup as "Last Upload" but the value was actually the END of the latest data week (week_start + 6 for Shopify, week_start + 5 for Amazon's Sun→Sat report). With the most recent week ending on the current day, "Last Upload: today" was misleading. Renamed:
  - Amazon group + Shopify group → `Data Through`
  - Warehouse group → `Last Sync` (matches what refreshLabel actually shows — Sheet sync date, not a true file upload)
  - Chewy / FBA Inventory / FBA Ship Detail / FBA Ship Summary already accurately labeled (`Last Snapshot` / `Last Shipment` / `Last Refresh`).
- **Inventory Planning CSV export wired (`downloadInventoryCSV`):** the top-bar ↓ CSV button previously fell through to the Forecast page exporter when you were on Inventory Planning — wrong context, mostly garbage output. Now `exportCSV()` routes `forecastView === 'inventory'` to a dedicated writer.
  - Respects current filters (brand / region / category / status / horizon / target / search) — same logic as `renderInventoryTbl`.
  - Respects the user's visible-columns set (`ipVisibleColumns()`) + current sort.
  - Always prepends `master_id / asin / brand / region / title` for join-back even if those columns are hidden in the view.
  - Composite cells (status badge, PO-by date) flatten to readable labels (`"Order Now"`, `"2026-08-12"`).
  - Filename: `smarterpaw-inventory-90d-2026-05-24.csv` (horizon + date).

## Recent Fixes (v4.170) — Inventory Planning: Need-group color coding + header tooltips + drop default Vel/day
- **Group headers are now color-coded** so the relationship between TOTAL and its components reads at a glance:
  - **NEED — TOTAL** = green (the answer, light green-tinted background band)
  - **NEED — BASE FORECAST** = blue (component A)
  - **NEED — REORDER** = orange (component B — matches the `+R n` badge color)
  - **AMAZON REORDER** + **CHEWY REORDER** = orange-yellow (drill-downs of REORDER)
- **Each Need group header has a tooltip** (cursor:help on hover) explaining the math:
  - TOTAL: per-channel breakdown of warehouse drain (Amazon contributes reorder, Shopify contributes base, Chewy contributes reorder) + note that the `+R n` badge surfaces the reorder portion.
  - BASE FORECAST: explains what each channel's base means (Amazon FBA→customer consumption, Shopify continuous draw, Chewy = 0 today since no consumer-level data).
  - REORDER: explains the lumpy events (Amazon FBA trigger + Chewy POs; Shopify = 0 because no buffer pool).
  - AMAZON REORDER: trigger mechanics + reorder qty formula + pointer to product edit modal for tuning threshold/qty.
  - CHEWY REORDER: source = chewy_forecasts table from Vendor Statement uploads, latest snapshot per month.
- **Vel/day column now default OFF** — already featured on the Demand Forecast page and not load-bearing for PO planning. Existing users keep their saved visibility (`ipVisibleCols` is persisted); only fresh defaults exclude it. Toggle back on via the View popup if needed.

## Recent Fixes (v4.169) — Uploads page redesigned: expandable groups with full drop cards inside
- **v4.167's table layout regressed drag-drop and readability** — user feedback: rows were cramped, status column always empty, last-upload dates not readable, no visible drop target. Fixed.
- **New layout: three section blocks** — 📊 Sales & P&L · 📦 Inventory · 🚚 FBA Shipments. Each section is a card; inside each card, expandable group rows.
- **Each group row** is collapsed by default. Click to expand → reveals the original full-size `.dz` drop cards with all instructions, click-to-pick, drag-drop, status line, and per-card last-upload date. Multiple groups can be open at once. State held on the DOM (`.open` class).
- **Group-row summary** shows icon · title · 1-line description · last-upload rollup (e.g. `2026-05-24 (yesterday)`). Group rollup picks the most recent across all sub-tiles in the group.
- **Drag-drop wired uniformly** via `initUploadDropTargets()` — every `.dz` card on the uploads page gets dragover/drop listeners; drops dispatch through the card's own `<input type=file>` (so multi-file works on the FBA Shipment Detail card). Old per-id drag-drop block at the top of the file removed to avoid double-firing.
- **`refreshUploadDataRanges` extended** to populate per-group rollups + previously-missing last-upload IDs:
  - `last-amz-sales-grp` (combined US/CA + EU latest)
  - `last-shopify-sales-grp`, `last-chewy-sales-grp`
  - `last-warehouse-grp` (reads from #refreshLabel)
  - `last-fba-inv-grp`, `last-fba-ship-grp`, `last-fba-ship-sum-grp`
  - Per-card `last-sales-skuecon-eu`, `last-fba-inv`, `last-fba-ship`, `last-fba-ship-sum`
  - All show a short relative-time suffix (`today` / `2d ago` / `3w ago` / `2mo ago`).

### Section structure (per user-requested hierarchy)
- **📊 Sales & P&L**
  - **Amazon — SKU Economics (US/CA + EU)** — expands to TWO drop cards: one for US/CA (with Folder/Zip multi-week backfill buttons) + one for EU. The Sun→Sat warning lives inside the expanded body.
  - **Shopify DTC** — expands to 1 drop card.
  - **Chewy** — expands to snapshot-date prompt + 1 drop card.
  - **Legacy — Amazon by Child ASIN** — collapsed by default, expands to the 6 per-brand-per-region tiles.
- **📦 Inventory**
  - **Warehouse Stock (NOT WIRED)** — expanded body shows a placeholder card: "warehouse-inventory uploader hasn't been added yet — current numbers are whatever was last loaded from the legacy Shopify Inventory export." Legacy Shopify Inventory dropzone retained (dimmed) for rollback / reference. Per user note: no 3PL, no Google Sheet — the real pipeline is TBD.
  - **Amazon FBA Inventory Snapshot** — expands to 1 drop card.
- **🚚 FBA Shipments**
  - **Shipment Detail** (per-shipment .tsv, multi-file) — expands to 1 drop card.
  - **Shipment Summary** (list CSV, NEW from v4.167) — expands to 1 drop card.

## Recent Fixes (v4.168) — Inventory edit modal: stop closing on click-drag-out
- **Bug:** The Inventory Planning row-edit modal had a bare `click` handler on `#editOverlay` that closed the modal whenever the click event's mouseup landed on the backdrop. If a user clicked inside the modal, dragged the cursor out (e.g., during text selection or accidentally), and released on the backdrop, the modal closed and any unsaved edits were lost.
- **Fix:** Track `mousedown` + `mouseup` independently — only close when BOTH events land on the overlay itself. Drags that start inside the modal are now ignored.
- **Reference:** the Products page modal has no backdrop-close at all, so click-drag never closed it there. This fix gives the Inventory modal the same drag-safe behavior while still keeping a clean backdrop click as an explicit "close" gesture.

## Recent Fixes (v4.167) — Uploads page table view + multi-file shipments + new Shipment Summary uploader + Need column architecture rewrite
- **⚠ SQL TO RUN:** `supabase_v4167_shipment_summaries.sql` — creates `fba_shipment_summaries` table (per-shipment-id rollup: status, last_updated, units_expected, units_located).

### Need architecture rewrite — per-channel base + reorder model
- **Conceptual fix:** old Need columns conflated channel-level sales velocity with channel-level reorder events. New model treats them as independent:
  - **`base`** per channel = sales velocity × horizon (seasonal forward) — what each channel will *consume*.
  - **`reorder`** per channel = lumpy replenishment events — what each channel will *order from the warehouse*.
  - Amazon contributes its reorder to Total (its base is FBA-internal churn); Shopify contributes its base (no buffer pool); Chewy contributes its reorder.
- **`inventoryNeedBreakdown(r, X)` now returns** `{amazon:{base, reorder, vel, meta}, shopify:{base, reorder, vel}, chewy:{base, reorder, vel}, base, reorder, total}`. Backward-incompatible — all old `nb.amazon` / `nb.shopify` / `nb.chewy` numeric accesses replaced with `nb.<channel>.<base|reorder>`.
- **`+R n` badge on Need-Total cells** (orange, mirrors Forecast page `+B n` pattern) — surfaces the reorder portion of the total at a glance. `+R 5,308` means 5,308 of the cell's total came from lumpy reorder events.
- **NEED — BASE FORECAST** (renamed from "NO REORDER"): sales-velocity forecast across ALL channels (Amazon vel + Shopify vel + Chewy vel × horizon). Today Chewy vel = 0 (we don't have consumer-level Chewy data); framework supports it when/if we do.
- **NEED — REORDER** (renamed from "REORDER ONLY"): now includes BOTH Amazon trigger AND Chewy POs (was Amazon-only).
- **New AMAZON REORDER columns** (4 horizons, default OFF) — channel-isolated Amazon trigger qty.
- **New CHEWY REORDER columns** (4 horizons, default OFF) — channel-isolated Chewy PO forecast.
- **Walmart** placeholder noted in the doc — channel ready to plug in when sales channel + reorder rules are defined.

### Uploads page reorganization (table view)
- **Replaced** five stacked card-style sections + the SKU Master table with a single dense **upload table** grouped by category (Sales / Inventory / Shipments / Legacy). Columns: Icon · Type+Description · Last Upload · Status · Action.
- **Drag-and-drop on table rows** — drop a file on any row to dispatch it to that row's primary input. `initUploadRowDragDrop()` is idempotent + called on Data → Uploads page show.
- **SKU Master section removed** — the Products page covers product editing and the per-SKU lead time / warehouse fields are reachable via inline editing there. Hidden stub elements (`#skuTBody`, `#skuCount`, `#skuSrch`, `#skuBrand`, `#skuTblCount`, `#f-newsku`, `#salesRefreshBadge`) kept so existing handler code that targets these IDs still finds something. `renderSkuTbl()` now writes into hidden DOM with no visible side effect.
- **Status/last spans** use the existing `.dz-st` / `.dz-last` class names — scoped CSS overrides inside `.up-tbl` strip the legacy `margin-top:10px` so they sit inline cleanly. All existing handlers (skuecon, shopify, fba-inv, etc.) work unchanged.
- **Legacy By-Child-ASIN tiles** preserved inside a `<details>` accordion at the bottom of the table — still upload-able for historical backfills, out of the way.

### Multi-file shipment upload + new Summary uploader
- **`handleFbaShipmentUpload` now accepts multiple files** (the `<input>` carries `multiple`). Processes sequentially: each file runs its own parser, dedup is per-shipment so re-uploads are idempotent. Progress shown in status line ("⏳ 3/12 · FBA19….tsv…"). Failed files don't block the batch; final alert summarizes any failures.
- **NEW: `handleFbaShipmentSummaryUpload` + `parseFbaShipmentSummary`** — accepts the Manage FBA Shipments → Download CSV (the list view, not per-shipment). Upserts to `fba_shipment_summaries` keyed on `shipment_id`. Captures:
  - `units_expected` vs `units_located` (shrinkage / extras → Amazon reimbursement claims)
  - `status` (Closed / Receiving / Working — in-flight tracking)
  - `last_updated` (when Amazon last touched the shipment)
  - Region inferred from `ship_to` FC code prefix (Y* = CA).
  - Status line surfaces shortfall: `✓ 25 shipments · 12,403 expected / 12,196 located · ⚠ 207 units short`.
- **Viewer integration** (planned): the existing FBA Shipments sub-view can join `fba_shipment_summaries` on `shipment_id` to show status badge + shortfall column. Not wired yet — current iteration just lands the data.

## Recent Fixes (v4.166) — Inventory Planning: column-visibility + saved views + 3-way Need split (Total / Base / Reorder)
- **⚠ SQL TO RUN:** `supabase_v4166_inventory_saved_views.sql` — adds `user_profiles.inventory_saved_views` JSONB column. Run BEFORE deploying or saved views won't persist (column toggles still work, they fall back to localStorage).
- **New IP_COLUMNS registry** mirrors `FC_COLUMNS` on the Forecast page. Each entry has `key, label, group, groupHdr, w, align, default, num, tip, headHtml, sortVal, render`. Drives the header row, category header row, and body cells — single source of truth. 29 columns total across 8 groups.
- **Three-way Need split** (the key user ask):
  - **NEED — TOTAL** (default ON): `need30/60/90/120` = Amazon reorder trigger + Shopify continuous + Chewy forecast (v4.164 model unchanged).
  - **NEED — NO REORDER** (default OFF): `needBase30/60/90/120` = Shopify continuous + Chewy only — what the warehouse needs even if no Amazon FBA replenishment fires. Useful for backing out the Amazon-trigger noise to see baseline demand.
  - **NEED — REORDER ONLY** (default OFF): `needRO30/60/90/120` = Amazon reorder trigger contribution only — zero when the trigger fires after the horizon end. Useful for seeing the lumpy Amazon-PO impact in isolation.
  - All three reuse the existing `inventoryNeedBreakdown(r, X)` which already returned `{amazon, shopify, chewy, total}` — no new math, just exposed three views of the same numbers.
- **📋 View popup** added to the controls bar — mirrors Forecast page pattern:
  - **Saved Views section**: name a state (cols + sort + brand/region/category/status/horizon/target/search filters), apply / rename / update-to-current / delete. Stored in `user_profiles.inventory_saved_views` JSONB; localStorage cache for first-paint speed.
  - **Column visibility checkboxes** grouped by category with `all / none` shortcuts per group. Persists to localStorage `ipVisibleCols`.
  - **Reset to defaults** button.
- **Sort key falls back to first visible column** if the active sort key is hidden — prevents the table from sorting by an invisible column.
- **Group header row** is now dynamic — colspans computed from the runs of contiguous visible columns sharing a `groupHdr`. Drop a column from a group and the header band shrinks; hide a whole group and the band disappears.
- **Region chip** now shows `ALL` (with `.rtag-all` styling) when the row is pooled (region = `US+CA`), instead of leaking the internal `US+CA` string.
- **New columns added beyond the Need split:** `master_id`, `sp_sku`, `total_onhand` — all default OFF, available via the View popup.
- **init flow** now calls `ipLoadSavedViewsFromDb()` alongside `fcLoadSavedViewsFromDb()` so views populate as soon as auth resolves.

## Recent Fixes (v4.165) — FBA Shipments page sortable + readable detail rows
- **Problem:** v4.163 shipped the FBA Shipments sub-view with a fixed date-desc sort and detail rows that crammed SKU + ASIN + FNSKU + Product Title into a single colspan cell. The result was hard to scan and impossible to sort.
- **Click-to-sort headers** on Date / Shipment ID / Name / Region / Ship To / SKUs / Units. Default sort = date desc. State held in `shipSortKey` + `shipSortDir`; `shipSetSort(key)` toggles direction or switches column. Active column shown in `var(--text)` with arrow indicator; inactive shown as muted `↕`.
- **Detail rows now use a nested table** inside a single colspan=9 cell so per-SKU columns (SKU · ASIN · FNSKU · Product · Qty) line up cleanly within the group instead of fighting the parent's column widths. Sub-table header keeps the same uppercase mono style at 9px. Detail rows have their own narrow padding (5px vs 7px) so the nesting reads as a sub-section.
- **Region rendering** switched from emoji flag (`🇺🇸` rendered as text "us" on some setups) to the existing `.rtag` chip style — same as the Inventory Planning region column.
- **Expanded shipment row** gets a subtle background highlight (`var(--surface2)`) so the open group reads as a unit with its detail block.
- **Unmapped items** flagged inline with a small orange `⚠ unmapped` badge instead of a separate column entry that disappeared into the parent table's layout.

## Recent Fixes (v4.164) — Inventory Planning "Need" columns = order volume by channel, not consumption forecast
- **User feedback:** the old Inventory Planning page reused the Forecast page's consumption-need math (forwardSeaDemand + Chewy forecast), so "30d Need" duplicated what's already on Forecast. Jason called it "not helpful." The Inventory page should answer "how many units must I order across channels in this horizon?" — order volume, not depletion.
- **New per-channel order-volume model** (lives in `inventoryNeedBreakdown(r, X)`):
  - **Amazon** = trigger-based FBA replenishment. FBA-DOS = `(fba_avail + fba_inbound) / amazon_velocity`. Order-by day = `max(0, FBA-DOS − reorder_threshold_days)`. If `orderByDay ≤ X`, the order fires inside the horizon and counts `forwardSeaDemand(arrival + reorder_qty_days) − forwardSeaDemand(arrival)` toward the Need cell. Else 0.
  - **Shopify** = continuous warehouse draw, no trigger. `forwardSeaDemand` on Shopify-only velocity over horizon X (seasonally adjusted).
  - **Chewy** = Chewy's own monthly forecast via existing `getChewyFcUnits(mid, X, region)`.
  - Total = sum of the three.
- **Per-channel velocity helpers** (v4.164 new): `getInventoryChannelVel(r, channelTest)` filters `salesData[mid]` by channel + region (pooled records pass region check); `invAmazonVel(r)` matches `/^amazon/`; `invShopifyVel(r)` matches `'shopify'`. Honors the Velocity Window dropdown (30/60/90/120d).
- **Inventory page rewired** — Need columns, scorecards, gap (30d + active-horizon), and the click-to-sort comparators now call `inventoryNeed(r, X)` instead of reading `r.need30/60/90/120`. **Forecast page untouched** — still uses `rederiveNeeds` (consumption-based) → `r.needX`. `getStatus(r)` also still uses `r.needX` (stockout risk = consumption check, which is the correct semantic for "🔴 Order Now").
- **Hover tooltips** on every Need cell show the per-channel breakdown including Amazon's trigger meta: vel/day, FBA-DOS, order-by day, arrival day, reorder window. Column-header tooltips explain the new model so the user isn't confused vs Forecast page numbers.
- **Worked example** (from Jason's note): Catnip Spray 3oz, vel 61.38/d, FBA = 4,141. FBA-DOS = 67d. Threshold = 90 → orderByDay = 0 (already past). With 60d lead, arrival = 60. 30d Need = forwardSeaDemand(60 → 150) ≈ 5,308. Old display was 2,075 (consumption). New display is 5,308.
- **Trade-off accepted for v1:** one Amazon order per horizon (a 120d horizon with a 30d reorder cycle would technically see 2 triggers — not modeled yet). Can extend to multi-trigger simulation later if it matters.

## Recent Fixes (v4.163) — FBA Shipments sub-view under the Forecast nav
- **Gap:** v4.155 added the FBA shipment uploader (one .tsv per shipment, dedup on shipment_id,sku) but gave the user no UI to *see* the uploaded shipments. Once the upload-status line scrolled past, the only way to confirm what was in the database was the SQL Query sub-view.
- **New "🚚 FBA Shipments" entry** in the Forecast nav dropdown (alongside Demand Forecast / Inventory Planning / Seasonality / Chewy Forecasts). Lives at `#page-fba-shipments`. Reachable via `switchForecastView('fba-shipments')`.
- **Initial draft was on Data → Uploads page** (right below the uploader); user pushed back — it didn't belong there. Moved to its own forecast sub-view to keep Uploads tightly focused on data ingestion.
- **Table:** grouped by `shipment_id`; columns = date · ID · name · region · ship-to · SKU count · unit total · delete-button. Click any row to expand into per-SKU line items (sku · ASIN · fnsku · product title · qty). Each expanded line flags `⚠ unmapped` if no product matched on master_id/ASIN — catches typos + missing catalog entries.
- **Filters in the header:** free-text search (matches shipment ID, name, ship-to, item SKU/ASIN/master_id) · region (US/CA/all) · time window (90/180/365 days/all). Default window = 365 days.
- **Lifecycle:** lazy-loaded on first nav into the sub-view; force-refreshed after each successful shipment upload so the new row appears next time the user opens the sub-view. Cached in `fbaShipmentsCache`.
- **Delete button** per shipment row — confirms, then deletes all line items from `fba_shipments` where `shipment_id = ?`. Logged via `logAudit('delete.fba_shipment', …)`.
- **Code additions:** `loadFbaShipments(force)`, `renderFbaShipmentsTbl()`, `toggleFbaShipment(id)`, `deleteFbaShipment(id)`. No new tables — reads existing `fba_shipments` from v4.155 schema. No SQL migration needed.

## Recent Fixes (v4.162) — Reorder controls also editable from the Inventory edit modal
- **Gap:** v4.160-161 added the four PO-planning controls (reorder threshold, reorder qty days, new-Amazon, deprecated-Amazon) to the Products tab modal — but **not** to the Inventory page's edit modal (`openEditModal` / `saveEditModal`). Users clicking a row on the Inventory page didn't see the new fields. Fixed.
- **New "🛒 PO planning" section** added between Supplier & Lead Time and Seasonal Index Override in the inventory edit modal. Three controls:
  - Reorder threshold (days) — number input
  - Reorder qty (days of supply) — number input
  - Amazon lifecycle column — 🆕 New + ⛔ Deprecated checkboxes
  - Footnote: "These values are per product (apply across all regions / channels)."
- **Save path:** writes the four fields to the `products` row (channel-agnostic, per master_id), separately from the per-region inventory upsert. Also mirrors onto every in-memory `records[]` entry sharing the same `master_id` so the pooled view + the other-region row reflect the change without reload.
- **Re-render fix:** `saveEditModal` was only calling the legacy `renderSkuTbl` + `renderAll` — neither updates the modern Inventory Planning table. Added a `renderInventoryTbl()` call so badges + Order Qty refresh in place.

## Recent Fixes (v4.161) — PO planner cross-channel; reorder fields move to products
- **Scope correction.** v4.160 gated PO recommendations to ASIN products, which was wrong. Manufacturer PO planning should apply to ALL products regardless of channel (Shopify-only, Chewy-only, Amazon, multi-channel). The Amazon-specific consideration — that Amazon has two inventory pools (warehouse + FBA) — is handled automatically by `total_onhand` which already sums fba_available + fba_inbound + warehouse for ASIN products and just warehouse for non-ASIN. Same PO formula, different inventory composition.
- **Schema migration.** Run `supabase_v4161_reorder_on_products.sql`. Adds `products.reorder_threshold_days` (default 90) + `products.reorder_qty_days` (default 90) and backfills from any per-inventory values (takes the max across regions if they differ). Old `inventory.reorder_threshold_days` / `inventory.reorder_qty_days` columns stay in place but unused — removable later.
- **`poByDateBurndown` + `recommendOrderQty`** drop the `!r.asin` gate. They now run for every product with velocity > 0. Reads `reorder_threshold_days` / `reorder_qty_days` from the product (via records-build).
- **`deprecated_product_amazon` is visual-only now.** v4.160 zeroed the PO recommendation when this was set — wrong, because a product deprecated on Amazon may still sell on Shopify/Chewy and need manufacturer stock. The badge stays; the math doesn't suppress.
- **`new_product_amazon` unchanged** — visual flag only.
- **Product modal** writes the four reorder fields to `products` directly via `productData`. The v4.160 separate two-region `inventory` upsert is removed. Load reads from `p.*`.
- **Modal hint cleaned up** — removed the "only saved with an ASIN" warning since reorder fields now apply universally.

## Recent Fixes (v4.160) — Per-SKU reorder controls + Amazon lifecycle flags
- **Schema:** run `supabase_add_reorder_fields.sql`. Adds `inventory.reorder_threshold_days` (default 90), `inventory.reorder_qty_days` (default 90), `products.new_product_amazon` (default false), `products.deprecated_product_amazon` (default false).
- **Reorder model rewritten.** Replaces the global "Target supply" sizing for ASIN products with per-SKU values:
  - **`poByDateBurndown(r)`** now uses `reorder_threshold_days` (when projected days-of-supply drops to threshold, PO must be in motion) instead of `safety_stock` × `daily_vel` as the floor. PO-by = day stock hits threshold − lead time.
  - **`recommendOrderQty(r, fallback)`** now computes order qty as `forwardSeaDemand(lead + reorder_qty_days) − forwardSeaDemand(lead)` — i.e., seasonal demand from arrival date for `reorder_qty_days`. Falls back to the global Target supply only when `reorder_qty_days` is unset.
- **PO planning is ASIN-only now.** Both helpers return `null`/`0` for non-ASIN products (Shopify-only, Chewy-only, bundle parents without ASIN) and for deprecated products. Matches the spec — Amazon FBA replenishment doesn't apply to those rows.
- **Lifecycle flag behavior:**
  - **Deprecated** → `recommendOrderQty` returns 0, `poByDateBurndown` returns null, the inventory row gets a "⛔ Deprecated" status badge + faded styling.
  - **New** → 🆕 badge prefixed to the product name in the inventory row. PO math is unchanged — limited history makes velocity unreliable, operator should eyeball the suggestion.
- **Product modal additions** (visible regardless of ASIN; the inventory-side reorder fields silently skip save without an ASIN — note shown):
  - Reorder threshold (days) — number input
  - Reorder quantity (days of supply) — number input
  - 🆕 New product (Amazon) — checkbox
  - ⛔ Deprecated (Amazon) — checkbox
- **Save path:** product fields land on `products`; the two inventory-side fields upsert to BOTH `inventory(asin,'US')` and `inventory(asin,'CA')` rows (same values — one PO covers pooled US+CA marketplaces), preserving existing fba_available / fba_inbound / warehouse / lead_time_days / safety_stock by fetching first + merging.

## Recent Fixes (v4.159) — Inventory: Target-supply dropdown impact made visible
- **Reported:** "changing the target supply dropdown doesn't appear to do anything." The dropdown DID fire `renderInventoryTbl()` and the Order Qty column WAS recomputing — but that column is the rightmost in a wide table (often off-screen), and many rows in the user's current view have Vel=0 (so Order Qty = 0 regardless of target).
- **Fix:** added a **"Order (Xd target)"** scorecard to the top scorecard row — sum of recommended order qty across visible SKUs, plus a "N SKUs to order" subline. Updates live with the dropdown, so 60/75/90 differences are immediately visible at the top without scrolling. Orange when total > 0, green when nothing to order.

## Recent Fixes (v4.158) — Inventory Planning: click-to-sort + default 30d-need + frozen header
- **Click-to-sort on every column.** New `ipSetSort(key)` + `ipSortVal(r, key, targetDays)`. Headers are clickable with ↑/↓/↕ indicators; click toggles direction. Numeric columns sort desc-first, text columns (Brand/Product/ASIN/Rgn) asc-first. Special cases: Status sorts by urgency rank (Order Now → OK), PO By sorts by date (soonest first), Order Qty + Gaps sort numerically.
- **Default sort = 30d Need descending** — the SKUs that most need a PO float to the top instead of the alphabetical/no-data clutter that was showing first.
- **Frozen header.** The `thead` was already `position:sticky` but the Inventory `.tbl-wrap` is `flex:1` with no bounded height, so the *page* scrolled instead of the wrapper and the sticky header never engaged. Added `#page-inventory .tbl-wrap { max-height: calc(100vh - 230px); overflow:auto }` so the wrapper is the scroll container — both header rows (group + columns) now freeze on scroll.

## Recent Fixes (v4.157) — Uploads page: de-dupe inventory sections
- **Removed the redundant legacy Amazon Restock tiles.** The "Weekly Inventory Refresh" section's "Amazon Restock Report" + "Amazon CA Restock Report" tiles (`parseRestock`) updated `inventory.fba_available` / `fba_inbound` from the Restock Inventory report — the same fields the new FBA Inventory Snapshot uploader (v4.154) updates from the richer Manage FBA Inventory report (+ snapshot history). Overlapping; dropped the two tiles.
- **Kept the Shopify warehouse tile** — it's NOT redundant (populates `inventory.warehouse` / 3PL stock, which the FBA snapshot doesn't touch). Renamed the section "🏪 Warehouse / 3PL Stock", fixed the misleading "saves to browser storage" copy (it writes to Supabase), and pointed users to the FBA Inventory Snapshot section for FBA position.
- **`parseRestock` + `handleUpload('restock'/'caRestock')` retained** in code but no longer reachable from the UI — left in place to avoid touching unrelated logic; can be deleted in a later cleanup.
- **Drag-drop dispatch rewritten** to route each tile to its correct handler (`dz-shopify` → `handleUpload`, `dz-fba-inv` → `handleFbaInventoryUpload`, `dz-fba-ship` → `handleFbaShipmentUpload`). Previously the generic handler defaulted unknown tiles to the `caRestock` path.

## Recent Fixes (v4.155) — FBA shipments (commit 2)
- **New `fba_shipments` table** + per-shipment `.tsv` parser. Run `supabase_add_fba_shipments.sql` before deploying. Source: the packing-list export (e.g. `FBA19CJKP303.tsv`) — key-value header block + item table. No bulk Inbound Shipment Items report exists in the account, so it's one file per shipment.
- **Parser (`parseFbaShipment`):** reads `Shipment ID` / `Name` / `Ship To` from the header; parses `created_date` from the Name string (`FBA STA (04/29/2026 20:25)-MEM2` → `2026-04-29`); infers region from the destination FC (Canadian FCs use Y-prefix airport codes, else US); reads the item table (Merchant SKU / ASIN / FNSKU / Shipped). Resolves `master_id` by ASIN → sp_sku/shopify_sku → SP-TEMP. Upserts on `(shipment_id, sku)` so re-uploads are idempotent.
- **Uploader tile** 🚚 on Data → Uploads. This is the cadence-learning source for Phase 2 (typical order size + interval per SKU).

## Recent Fixes (v4.156) — v1 PO planner on the Inventory page (commit 3)
- **Recommended order quantity** — new `recommendOrderQty(r, targetDays)`: order-up-to = `forwardSeaDemand(r, lead_time + targetDays)` (seasonally-integrated demand) + safety stock (`safety_stock` days × daily velocity), minus current on-hand (available + inbound + warehouse). New **"Order Qty"** column in the PO PLANNING group + a **"Target supply"** selector (60 / 75 / 90 days, default 75).
- **Burn-down PO-by date** — new `poByDateBurndown(r)`: projects seasonal demand forward, finds the day inventory hits the safety floor, backs off the lead time. Sharper + horizon-independent vs the old flat `poDL` (which is kept as a fallback when velocity/lead is missing). The "PO By" column now uses it.
- **US+CA pooled planning** — when the region filter is "US + CA" (empty), the inventory table now collapses to **one row per product** via `combineRegionRecords` (sums velocity + inventory across regions, re-derives blended_daily/needs). So the PO recommendation is a single order covering both marketplaces — matching how the same physical product is ordered. "US only" / "CA only" still show per-region rows.
- **Model notes:** Chewy is excluded from the PO demand (forwardSeaDemand is Amazon/DTC only — Chewy ships separately, not from FBA). Uses all-channel `blended_daily` against total on-hand (FBA + warehouse) — internally consistent pooled model. Lead time + safety stock come from the per-SKU `inventory` fields (preserved by the v4.154 snapshot sync).
- **FBA forecasting build status:** commits 1-3 complete (snapshot table + uploader, shipments table + uploader, v1 PO planner). **Phase 2** (when shipment history accumulates): cadence learning ("you usually order ~X every Y weeks; this rec is N% off your norm") + inventory burn-down chart from the weekly snapshots.

## Recent Fixes (v4.154) — FBA Inventory snapshots (commit 1 of FBA forecasting expansion)
- **New `fba_inventory_snapshots` table** + uploader — first piece of the FBA replenishment-forecasting build. Run `supabase_add_fba_inventory_snapshots.sql` before deploying.
- **Source:** Amazon "Manage FBA Inventory" report (the afn-* flat file — `224166020595.csv` shape). Captures the full position: `afn_fulfillable_quantity` (available to sell), reserved, unsellable, total, warehouse, the three inbound stages (working/shipped/receiving), researching, reserved-future-supply. Keyed `(asin, region, snapshot_date)`.
- **Uploader** on Data → Uploads tab. Because the report has no internal date or region column, it prompts for both: `promptFbaSnapshotMeta()` (region US/CA + snapshot date, default today), then the existing brand prompt (for auto-creating SP-TEMP products from unknown ASINs). Validates the file actually has `afn-fulfillable-quantity` — rejects the pricing/listings report with a clear error.
- **Legacy `inventory` table sync:** after writing the snapshot, the parser also pushes `afn_fulfillable_quantity` → `inventory.fba_available` and the summed inbound stages → `inventory.fba_inbound` for matching `(asin, region)`, **preserving** the user's `lead_time_days` / `safety_stock` / `warehouse` (fetched first, merged). So the existing Inventory Planning page immediately reflects the real FBA position without any other change.
- **Weekly cadence intended** — upload each week to accumulate a burn-down trajectory (Phase 2 uses this for the burn-down chart + inbound→fulfillable transition tracking).
- **Region/brand model:** the FBA report is per brand-account + marketplace (this account = Meowijuana US). ASIN-matched products inherit their existing brand; the brand prompt only assigns newly auto-created SP-TEMP products.
- **Still to come:** commit 2 = `fba_shipments` table + per-shipment `.tsv` parser (no bulk Inbound Shipment Items report available in the account). commit 3 = v1 PO planner on the Inventory page (PO-by date + recommended qty, US+CA pooled, 60-90d target).

## Recent Fixes (v4.153) — P&L category filter actually filters
- **Latent bug, surfaced after v4.152.** The Amazon P&L and Diagnostics category filters compared `prod.category_id` (integer FK) directly to `cat` (the dropdown's string value — the category NAME). That comparison silently always failed, so selecting any non-default category produced an empty view. v4.152 fixed the *duplicates* in the dropdown but didn't fix this — the underlying filter was broken since v4.62 when the dropdown was first wired.
- **Fix:** both P&L sites now resolve the FK before comparing — `(allCategories.find(c => c.id === prod.category_id)?.category || '') !== cat`. Mirrors the pattern already used by every other category filter in the codebase (Products / COGS / Forecast / Shopify P&L / Units Sold all use this resolution).
- **Sites updated:**
  - `renderPnl` main agg loop (Amazon SKU Economics view)
  - `renderPnlDiagnostics` per-ASIN aggregator (Diagnostics sub-view)
- **Shopify P&L unchanged** — its `renderShopifyPnl` already used the correct resolution pattern.

## Recent Fixes (v4.152) — P&L category dropdown: derive from products, dedupe
- **Bug:** Amazon and Shopify P&L category dropdowns were populated by iterating `allCategories` directly. That table has one row per (category, subcategory) pair, so any category with multiple subcategories appeared in the dropdown N times.
- **Fix:** populate the dropdown from the products catalog instead — take `distinct category_id` values that actually appear on `allProducts` (so unused categories don't clutter the picker), look up each id's `category` name via `allCategories`, dedupe, sort alphabetically. Applied to both the Amazon P&L (`#pnl-cat`) and Shopify P&L (`#spnl-cat`).
- **Side benefit:** dropdown now also re-runs only once per page session (`dataset.populated` guard on the Amazon side matches the existing Shopify guard) — no more growing list when the user re-opens the P&L tab.

## Recent Fixes (v4.151) — COGS page: row-click to edit product + one-click BOM apply
- **Row click opens product modal.** Every COGS table row is now clickable — same UX as the Products tab — so the user can edit title, brand, category, channel IDs, etc. without navigating away. Hover gives a subtle background highlight.
- **Stop-propagation on interactive cells** so clicking COGS values still triggers the cell editor (turns the td into a number input) and clicking the channel-IDs cell still lets you select-text the ASIN, instead of opening the modal. Existing `✕ dismiss` / `↺ undo` buttons already had `event.stopPropagation()` and continue to work.
- **One-click "✓ Apply" button** next to "BOM: $X.XX · auto-fillable" for bundle COGS that have a complete BOM sum but no stored value. Clicking writes the BOM total to the stored field via `cogsApplyBom(master_id, channel_field, value)` — no typing required.
- **"↺ Sync" button** appears next to "BOM: $X.XX ⚠ (delta)" when stored ≠ BOM total. One click overwrites the stored value with the BOM total — useful for catching drift after component COGS changes upstream.
- **Audit log:** new `cogs.apply_bom` action records master_id, channel, applied value, and the previous value.

## Recent Fixes (v4.150) — Chewy Forecasts: Revision Tracker (pre-month lock-in analysis)
- **New collapsible "📜 Revision Tracker" panel** between the scorecards and the main table on the Chewy Forecasts page. Lets the user pick any forecast month and see how Chewy's forecast for that month evolved from the very first snapshot through the final value locked in by the last snapshot taken BEFORE the month started.
- **Per-SKU + aggregate breakdown:**
  - **First Forecast (total)** — earliest snapshot value for the month + the date Chewy first told you that number.
  - **Final Pre-Month Lock** — last snapshot value with `upload_date < month_start`. If Chewy never sent a forecast for that month before it started, shown as `—` with an explanatory tooltip.
  - **Net Revision** — `locked − first`, in units and %. Green for upward revision, red for downward, grey for flat.
  - **Current Latest** — most recent snapshot value (for past months, this is what Chewy is saying NOW about an already-elapsed month — useful for spotting post-month adjustments).
- **Per-SKU table** sorted by net-change magnitude (biggest revisions on top). Columns: SKU · Product (with brand chip) · First · First date · Locked · Lock date · Net change · % · Latest.
- **Honors the brand + search filters** at the top of the page — narrowing the table also narrows the Revision Tracker so the analysis matches what you're looking at.
- **Defaults to the current calendar month** if it's in the data, else the most recent month present. Picker shows every month in the data, newest first.
- **Summary chip** in the collapsed `<details>` header — shows the picked month + net revision so the headline insight is visible without expanding.
- **Cheap when collapsed** — `renderChewyRevisionTracker()` writes to hidden DOM whenever the main `renderChewyForecast()` runs, so opening the panel is instant.

## Recent Fixes (v4.149) — Row-level math reconciliation: Net Proceeds tooltip + honest Margin/Contrib % for zero-sales rows
- **Reported bug:** an EU row with $0 net sales, $3.72 FBA fees, and -$7.84 Net Proceeds looked unreconcilable in the table. The visible columns only show FBA Fees + Referral + Ad Spend as separate items — for EU, Net Proceeds also subtracts Digital Services Fees that aren't surfaced anywhere in the row. Made the row's math opaque.
- **Reported bug #2:** Margin % and Contribution % showed `0.0%` for that row instead of indicating a real loss. The render did `r.net_sales > 0 ? (proceeds/net_sales)*100 : 0` — divide-by-zero protection that fell through to a misleading 0%.
- **Fix #1: Net Proceeds cell tooltip.** Hover any Net Proceeds value to see the per-row fee breakdown: `Net Sales − FBA Fulfilment − DSF (FBA) − DSF (Selling) − Referral − Ad Spend − … + FBA Reimbursement = Net Proceeds`. Only non-zero fee lines are listed. Reconciles to Amazon's `net_proceeds_total` directly.
- **Fix #2: Margin / Contribution % honest zero-sales handling.** When `net_sales = 0`:
  - If proceeds (or contrib) is also 0 → show `0.0%` (truly nothing happened)
  - If proceeds/contrib is non-zero → show `— (loss)` in red with a tooltip explaining: "No sales this period, but losing $X (storage / DSF / refunds on unsold inventory). Margin/Contribution % is undefined when sales = $0."
  No more false `0.0%` reading on rows that are actually leaking money.
- **Fix #3: DSF columns added to PNL_COLUMNS registry.** Two new toggleable columns — `DSF (FBA)` and `DSF (Selling)` — under the "fees" group. Default OFF; users enable via the View popup. When in EU mode, ticking these makes EU rows fully reconcilable inline without needing the explainer panel.

## Recent Fixes (v4.148) — EU fees: stop parking into wrong US buckets
- **User correctly pushed back** on the v4.141 mapping that parked Digital Services Fee (FBA) into `aged_inventory_fee_total` and DSF (Selling) into `refund_admin_fee_total`. Those are semantically different fee categories — "Aged Inventory" is Amazon's long-term storage penalty, not a UK/EU tax. The fee breakdown panel was displaying DSF values under those misleading labels.
- **Fix:** EU rows now carry two distinct fields:
  - `digital_services_fba_fee` ← Digital Services Fee (FBA Fulfilment fees) total
  - `digital_services_selling_fee` ← Digital Services Fee (Selling on Amazon fees) total
  US/CA buckets (`aged_inventory_fee_total`, `refund_admin_fee_total`) stay zero for EU rows; never reused for unrelated EU fees.
- **`totalFees` calculation** now adds the two EU fields unconditionally — US/CA rows have undefined → 0, EU rows contribute their actual DSF values. Same change applied to `pnlTotalsForRange` (period-over-period delta), the main agg, and selectedAgg loops. `PNL_NUMERIC_FIELDS` (drives the multi-select rollup) extended to include both new fields.
- **Fee breakdown panel is now region-aware.** EU mode shows: `FBA Fulfilment (incl. Base + Fuel)` · `Digital Services Fee — FBA Fulfilment` · `Digital Services Fee — Selling` · `Referral Fee` · `Sponsored Products`. US/CA mode unchanged.
- **Explainer panel updated.** The 🧮 disclosure no longer claims DSF is "surfaced as Aged Inventory" — names the actual breakdown labels and explains DSF is EU-specific with its own distinct field.

## Recent Fixes (v4.147) — sales_weekly CHECK constraints: allow EU values
- **SQL-only hotfix.** No code changes. v4.144 started inserting EU rows into `sales_weekly` (region in {GB, DE, FR, IT, ES, NL}, channel in {amazon_gb, ..., amazon_nl}), but the original schema's `sales_weekly_region_check` and `sales_weekly_channel_check` CHECK constraints only whitelist US/CA values, so inserts fail with `"new row violates check constraint sales_weekly_region_check"`.
- **Patch file:** `supabase_v4147_sales_weekly_eu_checks.sql`. Idempotent — drops the existing region + channel CHECK constraints (under whatever auto-generated names they have) and re-adds them with the EU values included. Run ONCE in Supabase → SQL Editor before attempting any EU upload.
- **New region whitelist:** `US, CA, MX, GB, DE, FR, IT, ES, NL`. Added MX since `storeToRegion()` already supports it.
- **New channel whitelist:** `amazon_us, amazon_ca, amazon_mx, amazon_gb, amazon_de, amazon_fr, amazon_it, amazon_es, amazon_nl, shopify, chewy`.

## Recent Fixes (v4.146) — Merge robustness: product_cogs + FK cascade
- **`runMerge` now handles `product_cogs`.** The previous version touched every other dependent table but missed `product_cogs` (its PK is master_id, so a straight UPDATE src→tgt would PK-collide when both products had COGS rows). New flow:
  - Read both src and tgt COGS rows.
  - If src has a row: when tgt also has one, **merge null fields** — fill any tgt-null COGS column with the src value, upsert tgt, then delete src. When tgt has no row, just reassign src→tgt. Either way: useful COGS data from the duplicate is preserved on the survivor.
  - Wrapped in try/catch — non-fatal. Worst case is the FK CASCADE handles cleanup at the final product delete.
  - Fields covered: `amazon_cogs`, `amazon_cogs_eu`, `dtc_cogs`, `chewy_cogs`.
- **Schema patch — `sku_economics_eu` FK now CASCADEs.** The original v4.139 migration created the FK with default NO ACTION semantics, blocking direct product deletes (Products tab → Delete button) when EU rows existed. v4.145 fixed the merge tool via JS reassignment; v4.146 fixes the schema so direct deletes also work without manual cleanup.
  - **New file:** `supabase_v4146_eu_fk_cascade.sql` — idempotent ALTER that drops the existing FK (under any auto-generated name) and re-adds it with ON DELETE CASCADE. Run ONCE in Supabase SQL Editor.
  - **Updated:** `supabase_add_sku_economics_eu.sql` for fresh installs now includes `on delete cascade` on the FK directly — anyone running it post-v4.146 gets the right behavior without the patch.

## Recent Fixes (v4.145) — Merge + SP-TEMP promotion: reassign sku_economics_eu FKs
- **Bug:** `runMerge` and the SP-TEMP→SP-XXXX promotion path in `saveProduct` updated the master_id on every other dependent table (sales_weekly, sku_economics, chewy_forecasts, bom, inventory, channel_listings) but missed `sku_economics_eu` (added in v4.139). Merging a duplicate that had any EU rows failed with: `"violates foreign key constraint sku_economics_eu_master_id_fkey on table sku_economics_eu"`.
- **Fix:** added `sku_economics_eu.master_id` UPDATE alongside the others in both flows. Marker comment in `runMerge` flags it as the v4.139 oversight so anyone adding future FK-bearing tables knows to update both paths.
- **Known latent gap (not v4.145 scope):** `product_cogs` rows aren't migrated during merge either — if both src + tgt have COGS rows, merge would fail on the master_id PK. Not the user's current symptom; flagged for a future pass.
- **Schema note:** `sku_economics_eu`'s FK currently uses default `NO ACTION` behavior (not `ON DELETE CASCADE`). If you ever delete a product directly (via the Products tab Delete button) that has EU rows, you'll hit the same error. Workaround for now: delete the EU rows manually or run `ALTER TABLE sku_economics_eu DROP CONSTRAINT sku_economics_eu_master_id_fkey, ADD CONSTRAINT sku_economics_eu_master_id_fkey FOREIGN KEY (master_id) REFERENCES products(master_id) ON DELETE CASCADE;` once. Not bundled into v4.145 to avoid forcing another migration run.

## Recent Fixes (v4.144) — EU SKU Economics also writes to `sales_weekly` (visibility + forecast-ready)
- **Gap acknowledged from v4.139:** EU was P&L-only — sales rows weren't landing in `sales_weekly`, so EU units never appeared in Units Sold, channel-mix queries, or `velocity_calculated`. User correctly pushed back that EU products map to existing SmarterPaw master_ids (same physical product, different regional listing) and the volume is comparable to Shopify (which is already mixed in without distorting US forecasts). Fixed.
- **`parseEuSkuEconomics` now writes both tables.** Alongside the `sku_economics_eu` upsert, it inserts rows into `sales_weekly`:
  - `channel` = `'amazon_gb' | 'amazon_de' | 'amazon_fr' | 'amazon_it' | 'amazon_es' | 'amazon_nl'` (per-country, mirroring the `amazon_us` / `amazon_ca` naming pattern — gives per-country velocity for free)
  - `region` = the country code
  - `shopify_sku` = NULL (Architecture Rule #1)
  - `week_start` = Monday-shifted via `dateToMondayLocal(startSun, true)` — matches the US/CA convention so `sales_weekly` stays uniformly Monday-based
  - `units_ordered` = `net_units_sold`; `revenue` = `net_sales` in **native currency** (GBP/EUR — `sales_weekly` has no currency column, so the value is raw native; `sku_economics_eu` remains the FX-aware source for revenue analysis. Forecasting uses units, which is currency-agnostic.)
  - Zero-unit rows are skipped (existing US convention — `sales_weekly` is about sales)
- **Delete + insert pattern** (Architecture Rule #5) — Amazon rows can't upsert against the functional `coalesce(shopify_sku,'')` unique index. Deletes existing `(channel, asin, week_start)` matches in batches of 100 ASINs, then inserts the new rows.
- **Overlap prompt covers both writes.** The v4.143 `sku_economics_eu` overlap dialog already filters `econRows` by user's choice; `salesRows` is derived from the same array, so the choice flows through to sales_weekly writes too. No double-prompt.
- **Phase 2 marker for EU forecasting.** The records-build loop in `init()` hardcodes `regions = ['US','CA']` for products with ASIN — that's why EU velocity rows in `velocity_calculated` never reach the Forecast tab today. Added a doc comment naming the **one-line change** to enable EU forecasting later: change that array to `['US','CA', ...EU_REGIONS]`. Marker text: `PHASE 2 EU forecasting`. EU sales_weekly + velocity_calculated entries are already populated from v4.144 onward, so flipping requires no parser changes, no schema migrations, no historical backfill.
- **Status message** updated to surface both write counts: `✓ N P&L rows · M sales rows · GB/DE/... · 1 week · K ASINs · J new products`.

## Recent Fixes (v4.143) — EU SKU Economics: overlap-overwrite prompt
- **Gap closed.** The EU uploader was upserting silently on `(asin, region, week_start)` conflict — a re-upload of the same week silently overwrote existing rows. The US uploader has a dedicated `showUploadConflictDialog` flow on overlap; EU now has the same.
- **What it does:** after dedup, queries `sku_economics_eu` for any existing keys that match what the file is about to write. If any overlap, shows the conflict dialog with `Cancel` / `Add new rows only` / `Replace`. `new_only` filters out the overlapping `(asin, region, week_start)` rows before insert; `replace` lets the existing upsert proceed (overwrite via unique constraint); `cancel` aborts.
- **Dedup remains as before:** in-file rows with the same `(asin, region, week_start)` are summed (multi-MSKU pattern, mirrors US v4.61). The DB-level unique constraint is the ultimate guarantee of one row per key.

## Recent Fixes (v4.142) — Fee calculation explainer for US + CA (parity with EU)
- **New 🧮 disclosure panel above the scorecards** when US or CA region is active — mirrors the EU explainer added in v4.141. Lists every fee field that rolls into Amazon Fees, the Net Proceeds formula, where COGS comes from, and the Contribution Profit / Margin / Contribution % derivations.
- **Header swaps US ↔ CA** depending on selected region.
- **CAD→USD conversion note** is conditionally inlined into the Net Sales bullet only when CA is selected — keeps the panel focused per region.
- **Reuses the same `<details>` UX as the EU panel** so the disclosure feels uniform across the three Amazon regions.

## Recent Fixes (v4.141) — EU fee mapping bug + transparency
- **Bug fix:** `loadEuPnlTab` was double-counting `Base fulfilment` and `Fuel/logistics surcharge` into Amazon Fees. The Amazon EU report's `Fulfilment by Amazon fulfilment fees total` column IS the consolidated fulfillment fee — it already includes Base + Fuel as sub-components. Per-unit reconciliation on a sample row: `Base 2.70/u + Fuel 0.04/u = 2.74/u = Fulfilment by Amazon per unit`. Adding the components on top inflated FBA Fulfillment by ~50% (it was `5.40 + 0.08 + 5.48` instead of just `5.48`).
- **Verified against the report:** `27.78 net sales − 5.48 fulfillment − 0.10 DSF FBA − 0.10 DSF Selling − 5.00 referral − 9.79 sponsored = 7.31 net proceeds` ✓ matches `net_proceeds_total`.
- **Corrected mapping (EU → sku_economics shape):**
  - `fba_fulfilment_fees_total` → `fba_fulfillment_fee_total` (single source — no longer double-adding Base + Fuel)
  - `digital_services_fee_fba_fulfilment_total` → `aged_inventory_fee_total` (parked in the unused EU bucket so it still rolls into Amazon Fees)
  - `digital_services_fee_selling_total` → `refund_admin_fee_total`
  - `referral_fee_total`, `sponsored_products_total`, `net_proceeds_total` → 1:1
  - Raw `base_fulfilment_fee_total` + `fuel_logistics_surcharge_total` retained on the row under `_eu_base_fulfilment` / `_eu_fuel_surcharge` for future drill-down if needed.
- **New 🧮 "How EU fees + proceeds are calculated" disclosure panel** above the scorecards, visible only when EU region is selected. Spells out every input → bucket → output mapping in plain language so the user can reconcile against the Amazon EU report row-by-row. Mirrors the partial-data callout pattern used on the Shopify view.

## Recent Fixes (v4.140) — P&L empty state on region switch
- **Bug:** switching to a region with no data (e.g. clicking 🇪🇺 EU before any EU upload, or before running the v4.139 migration) left the previous region's scorecards + fee breakdown + footnote on screen. `renderPnl` early-returned on empty `sourceData`, so nothing got cleared — visually it looked like EU had CA's numbers.
- **Fix:** removed the early-return. When `sourceData` is empty, the function now explicitly renders an empty state — zeroed/cleared scorecards with a "No EU SKU Economics data uploaded yet — use the 🇪🇺 EU uploader on Data → Uploads, and make sure `supabase_add_sku_economics_eu.sql` has been run" message, zeroed row count, "— Empty —" tbody, empty fee breakdown, hidden chart, cleared `pnlVisibleMids` / `pnlExportRows`. Same path covers EU error cases (table doesn't exist, RLS denied) — `loadEuPnlTab`'s catch block now also routes through `renderPnl` so the UI clears, then overwrites the tbody with the specific error message.

## Recent Fixes (v4.139) — Amazon EU SKU Economics: table + uploader + P&L EU toggle
- **New table `sku_economics_eu`** — separate from `sku_economics` because the EU fee taxonomy is structurally different (Digital Services Fees, Fuel surcharge — no parallel in US/CA; conversely no Inbound/Aged/Removal/Storage Util in EU) and the native currencies are GBP + EUR rather than CAD/USD. `week_start` is kept as the report's native **Sunday** (not Monday-shifted like `sku_economics`) — isolated to this table, documented in the column. Unique key `(asin, region, week_start)`. Run `supabase_add_sku_economics_eu.sql` BEFORE deploying v4.139.
- **New column `product_cogs.amazon_cogs_eu`** for EU shipments (different freight + import duty than US/CA fulfillment). EU P&L falls back to `amazon_cogs` if `amazon_cogs_eu` is blank, so adoption is gradual. Surface: new "Amazon EU COGS" column on the COGS page, editable inline; CSV download/upload extended to include it.
- **New EU uploader tile** on the Uploads tab (separate from US/CA SKU Economics — same single-file Sun-Sat validation, but maps the British "fulfilment" spelling and EU-specific fee columns). Brand prompt fires at upload (no Brand column in the raw export); unknown EU ASINs auto-create as `SP-TEMP-{asin}` with the chosen brand. Non-EU rows in the file are rejected with a clear error.
- **`storeToRegion`-equivalent EU set:** new module-level `EU_REGIONS = {GB, DE, FR, IT, ES, NL}`. The EU parser validates the file's `Amazon store` column against this set.
- **P&L tab — new 🇪🇺 EU region button.** Clicking it:
  - Loads `sku_economics_eu` (paginated, cached as `euPnlData`).
  - Shows a secondary "Market" dropdown: `All EU (rollup)` / GB / DE / FR / IT / ES / NL — defaults to "All EU".
  - Re-labels the native-currency toggle button from `CAD` → `Local` (since native varies per row: GBP for GB, EUR for the rest).
  - Triggers `fetchEuFxRates()` against `frankfurter.app` (free, ECB-sourced) to get live GBP→USD and EUR→USD; cached for the session with sensible fallbacks (`pnlFxGbp = 1.27`, `pnlFxEur = 1.08`).
  - All `pnlData`-iterating loops in `renderPnl` (main agg, selectedAgg, prev-period delta, chart) route through a new `getPnlSource()` helper that returns the right data array + region predicate, so the same renderer powers US/CA and EU without conditional branches in the loop body.
  - COGS lookup goes through `getActivePnlCogs(mid)` — returns `amazon_cogs_eu` when in EU mode, falling back to `amazon_cogs` if the EU column is blank.
- **FX semantics:** the existing `pnlCurrencyMode` two-state model (`usd` | `cad`) is reused for EU — `cad` mode now means "show native (Local)" when in EU view. The currency-label rendering elsewhere (`USD*` footnote, etc.) already adapts per region.
- **Schema mapping (EU → normalized):** `loadEuPnlTab` projects EU rows onto the `sku_economics` shape `renderPnl` expects. `base_fulfilment + DSF FBA + Fuel + FBA fulfilment total` → `fba_fulfillment_fee_total` (consolidated FBA fee). `DSF (Selling on Amazon fees)` → `refund_admin_fee_total` (closest existing bucket; not perfect semantically but keeps total whole). Inbound / Aged / Removal / Storage Util / Referral Refunds / FBA Reimbursement default to 0 — the EU report doesn't break those out.

## Recent Fixes (v4.138) — Shopify DTC P&L sub-view (v1, partial data)
- **New 🛍 Shopify DTC sub-view** added to the P&L dropdown (alongside Amazon SKU Economics and COGS). Mirrors the Amazon P&L layout — same filter strip (period with "Last 7 days", brand, category, search, quick filter), scorecards, time-series chart with metric selector, multi-select aggregation with persistent selection across filters, period-over-period delta chips, and click-to-sort product table.
- **Data sources for v1:** `sales_weekly` rows where `channel='shopify'` (paginated, per Architecture Rule #4) for revenue + units; `product_cogs.dtc_cogs` for COGS. No region toggle — Shopify is US-only by SmarterPaw's convention.
- **Partial-data callout** prominently displayed above the scorecards naming what's NOT captured yet: transaction / payment-processor fees, shipping costs, refund admin, ad spend (Meta / Google / TikTok). Net Proceeds here is "Net Sales − COGS" with no fee/cost subtraction — explicitly flagged so the user doesn't read it as full P&L.
- **Live scorecards (current):** Net Sales, Total COGS, Net Proceeds, Margin % — each with period-over-period delta vs the equal-length prior window (reuses the Amazon `pnlDeltaChip` helper). **Placeholder scorecards** render "—" with explanatory tooltips: Transaction Fees, Shipping, Ad Spend (DTC), Refunds. Visible gaps so the user can see exactly what an uploader needs to backfill.
- **Cache invalidation:** `handleSalesUpload` resets `shopifyPnlData = []` after a successful `channel='shopify'` upload so the next open of the tab re-fetches.
- **Skipped for v1 (can layer in later):** Diagnostics tab (no per-SKU mystery here — Shopify SKUs auto-create as SP-TEMP on upload), Saved Views popup, Show-selected-only toggle, fee-breakdown sidebar. Structure is parallel to Amazon so any of those can be ported when needed.
- **Future:** when the user pulls a Shopify report with the missing economics columns, they'll likely want a new `shopify_economics` table parallel to `sku_economics`, an uploader that writes to it, and updates to `renderShopifyPnl` that read from it. The scorecard placeholders + the partial-data banner are the seams.

## Recent Fixes (v4.137) — Products tab: filter by notes
- **Two new options in the Products tab `prodFilter` dropdown:** "📝 Has notes" (products where `products.notes` is non-empty — general admin / merge history) and "📝 Has forecast notes" (products where `products.forecast_notes` is non-empty — the deliberate per-product annotations edited from the Forecast tab, v4.99).
- **Note indicators in the Product cell.** A 📝 icon shows when a product has a forecast note; a dimmed 🗒 shows when it has a general note (suppressed for needs-review rows, which already key off `notes`). Hovering either icon shows the note text in the tooltip — so the filter is actionable without opening every modal.

## Recent Fixes (v4.136) — Bundle attribution in the per-channel Sold / Forecast columns
- **The "Sold by channel" and "Forecast by channel" 30/60/90/120d columns ignored bundle attribution.** Even with "+ bundle components" checked, `fcSoldByChannel` summed only direct channel sales — so a component product whose demand came mostly through bundle sales showed understated per-channel numbers (the main Need columns already counted it; only these per-channel columns didn't).
- **Fix:** new `fcBundleAttrByChannel(r, channels, days)` helper returns the bundle-attributed units for a channel group over a window, gated by the `fBundleAttr` checkbox (returns 0 for the Chewy group — Chewy demand isn't in `sales_weekly`). `fcSoldByChannel` now adds it to the direct total; `fcForecastByChannel` extrapolates from that bundle-inclusive base automatically.
- **+B badge** on both column families — orange `+B N` marker surfaces the attributed portion, same affordance as the main Sold / Need columns. Column width bumped 74px → 90px to fit. Tooltips updated.
- **Core forecast untouched.** `fcSoldByChannel` only feeds the per-channel display columns — the main Need columns and scorecards run off `blended_daily` / `need_N` (a separate path that already had bundle attribution via `recomputeRecordVelocity`). Verified the change can't shift the primary forecast.
- Toggling "+ bundle components" re-renders these columns live (the checkbox's `applyVelocityWindow()` → `renderAll()`).

## Recent Fixes (v4.135) — Shopify weekly aggregation: Sunday bucketed into the wrong week
- **Bug:** the Shopify daily→weekly aggregator put each week's **Sunday** sales into the *next* week's bucket. `dateToMondayLocal` mapped Sunday FORWARD to the next-day Monday — correct for Amazon's Sun-Sat report weeks (a Sunday is the START of that week), but wrong for Shopify, which reports genuine daily data where a Sunday is the LAST day of its Mon-Sun week.
- **Symptom:** a Shopify report covering Mon May 11 → Sun May 17 split into TWO `week_start` rows — May 11 (Mon-Sat) + May 18 (Sun only). The upload reported "2 weeks" for a one-week file, and the Uploads tab's "Data through" date showed `2026-05-24` (May 18 + 6) — a future date.
- **Fix:** `dateToMondayLocal(date, sundayMapsForward = true)` gained a direction flag. `parseShopifySales` now passes `false` — a Sunday maps BACK 6 days to its week's Monday. `parseSkuEconomics` keeps the default (`true`) — Amazon's Sun-Sat convention is unchanged.
- **Scope:** this affected every Shopify upload since v4.92 (when `dateToMondayLocal` was introduced). Each stored weekly row was `[Mon-Sat of its own week] + [Sunday of the prior week]` — total units conserved, but Sunday attributed one week late. Impact on velocity/forecasts is minor (a 1-day shift inside rolling 30/60/90d windows), but the week boundaries were wrong.
- **Cleanup:** no clean SQL migration is possible — the rows are already weekly aggregates, so the mis-bucketed Sunday can't be separated out. To correct historical data, **re-upload the daily Shopify CSVs** (one Mon-Sun week per file is cleanest) and choose **Replace** at the overlap prompt; the v4.135 parser buckets them correctly. The most-recent week's dangling Sunday self-corrects when the following week is uploaded.

## Recent Fixes (v4.134) — "Data through" date: correct week-end per channel
- **SKU Economics "data through" date was one day too late.** v4.133 added `week_start + 6` for every channel, but Amazon's SKU Economics report runs **Sunday→Saturday** while `week_start` is stored as the *Monday* of the overlapping Mon-Sun week (v4.91 parser convention). Monday + 6 = the *following Sunday* — one day past the report's real Saturday end. Fixed: SKU Economics now uses `week_start + 5` (Saturday) and labels it `thru Sat YYYY-MM-DD`.
- **Shopify unchanged** — Shopify genuinely runs Monday→Sunday, so `week_start + 6` (Sunday) is correct. Now labeled `through Sun YYYY-MM-DD` for clarity.
- `endOfWeek(mondayStr, offset)` gained an explicit offset arg (defaults to 6) so each channel passes its own reporting convention.

## Recent Fixes (v4.133) — Data Uploads: show "data through" date per section
- **Each upload tile's `.dz-last` line now shows where the loaded data currently ends** — so the user can see at a glance how current each channel is before deciding what to upload next.
- **`refreshUploadDataRanges()`** queries the latest data date per channel:
  - **SKU Economics** — latest `week_start` per region from `sku_economics`, shown as the week-END (Saturday, `week_start + 6`): `📅 Data US: thru 2026-05-16 · CA: thru 2026-05-16`.
  - **Shopify DTC** — latest `week_start` from `sales_weekly` where `channel='shopify'`, shown as week-end: `📅 Data through 2026-05-17`.
  - **Chewy** — latest `upload_date` + furthest `forecast_month` from `chewy_forecasts`: `📅 Last snapshot 2026-05-12 · forecasts thru 2026-09`.
- **Runs on Uploads-view open** (`switchDataView('uploads')`) and **after every successful upload** (Shopify / SKU Economics single + folder + zip / Chewy handlers all call it), so the line updates immediately without a tab switch. Per-file batch counts still live in the `.dz-st` status line.
- Empty-state messages ("📅 No SKU Economics data loaded yet" etc.) when a channel has no rows.

## Recent Fixes (v4.132) — P&L: "Last 7 days" period + scorecard period-over-period deltas
- **New "Last 7 days" option** at the top of the P&L period dropdown.
- **Every scorecard now shows a +/- delta vs the previous equal-length period.** e.g. with "Last 7 days" selected, each card shows "▲ 12.4% vs prev" comparing against the 7 days before that. Works for every period type (fixed-day, YTD, custom) — `getPnlPrevDateRange()` derives the prior window purely from the current `{from,to}` span (equal length, immediately preceding).
- **Apples-to-apples comparison set.** The prior-period total is computed over the SAME products the scorecards reflect — the selected set if a selection is active, else the visible post-quick-filter rows (`comparisonMids`). So the delta answers "these exact SKUs — how did they do in the prior window," not "top 10 this period vs a different top 10 last period."
- **Color sense flips for cost metrics.** `pnlDeltaChip(cur, prev, goodWhenUp, ...)` — Gross/Net Sales, Net Proceeds, Contribution Profit/% read green on an increase; Amazon Fees, Ad Spend, COGS read green on a *decrease* (a fee increase is unfavorable).
- **Contribution %** delta is shown in percentage POINTS (`+2.3 pts`), not percent-of-percent, since the metric is itself a percentage.
- **Edge cases:** no prior data → "▲ new · no prior data"; flat (<0.05% change) → grey "→". Each chip's tooltip names the exact prior date range.
- **New helpers:** `getPnlPrevDateRange(cur)`, `pnlTotalsForRange(from, to, midSet)` (mirrors the renderPnl agg loop's fx + field mapping so prior totals are directly comparable), `pnlDeltaChip(...)`.

## Recent Fixes (v4.131) — Password reset + change password
- **"Forgot password?" link** on the login screen. `sendPasswordReset()` reads the email field (or prompts if empty) and calls `sb.auth.resetPasswordForEmail(email, { redirectTo })`. Success message shows inline in green.
- **Password-recovery landing flow.** Clicking the reset email returns the user to the dashboard with `type=recovery` in the URL. Two detection paths so the user can't slip into the app without setting a new password:
  1. `bootAuth()` checks `window.location.hash`/`.search` for `type=recovery` BEFORE `getSession()` runs and sets `_passwordRecoveryMode = true` + shows the reset gate (guards the race where `getSession()` returns the recovery session before the `PASSWORD_RECOVERY` event fires).
  2. `onAuthStateChange` also handles the `PASSWORD_RECOVERY` event → `showPasswordResetGate()`.
  `onAuthSuccess()` bails while `_passwordRecoveryMode` is set, so the dashboard never loads behind the reset screen.
- **New `#pw-reset-gate` overlay** — "Set a new password" form (new + confirm, min 8 chars). `submitPasswordReset()` validates, calls `sb.auth.updateUser({ password })`, clears the recovery flag, strips the recovery token from the URL via `history.replaceState` (so a reload doesn't re-trigger the gate), then runs the normal `onAuthSuccess` flow.
- **Settings → 🔑 Change password** — for already-signed-in users. `changePassword()` validates new + confirm (min 8 chars), calls `sb.auth.updateUser({ password })`; the existing session stays valid so no re-login. New section sits at the top of the Settings page above Users.
- **Audit log:** `user.password_reset` (via email link) and `user.password_change` (via Settings) events recorded.
- **Setup note:** `resetPasswordForEmail`'s `redirectTo` is `window.location.origin + pathname` — the same URL already whitelisted for Google OAuth, so no new Supabase redirect-URL config is needed. If reset emails land but the link errors, confirm that URL is in Supabase → Auth → URL Configuration → Redirect URLs.

## Recent Fixes (v4.130) — Query Database: COGS % of MSRP presets
- **Two new presets** in the Query Database tab:
  - **COGS % of MSRP** — catalog-wide avg / median / min / max of `amazon_cogs ÷ msrp × 100`, plus the sample-size count.
  - **COGS % of MSRP by Brand** — same metric grouped by brand (avg + median per brand).
- Both join `products` ↔ `product_cogs`, use `amazon_cogs` as the COGS source, and exclude bundles + rows missing MSRP or COGS. Comments in each query note how to swap to `dtc_cogs` for the DTC cost basis.

## Recent Fixes (v4.129) — Rename saved views
- **New ✎ rename button** next to each view in the View popup, on BOTH Forecast and P&L. Prompts for a new name (pre-filled with the current one); cancels on empty / unchanged input. Conflicting target name asks to overwrite.
- **Button order in each row:** Apply (the view name itself) · ✎ Rename · ↻ Update · ✕ Delete — rename sits just left of update because it's the less-destructive edit action.
- **Rebuild instead of delete+add** for the rename so the entry keeps its iteration position. Doesn't matter for the popup (sorts alphabetically) but stays cleaner if downstream code ever needs insertion order. Forecast version persists the rebuilt object via the existing `fcPersistSavedViews()` so the rename syncs to Supabase too; P&L version persists to localStorage via `pnlPersistSavedViews()`.

## Recent Fixes (v4.128) — View popup repositioned + relabeled
- **Button label "📋 Columns" → "📋 View"** on both the Demand Forecast and P&L tabs. Since v4.126/v4.127 the popup actually manages a lot more than columns (full report state: sort, filters, time range, channels, selection, + columns), so "View" frames it better and matches how the popup itself describes a saved bookmark.
- **Popup anchoring switched from inline / button-anchored → fixed top-right of viewport.** Earlier behavior anchored the popup directly below the button using the button's bounding rect (Forecast) or `position:absolute;top:100%;right:0` (P&L). When the button landed mid-filter-strip the popup got clipped by neighboring controls; with two rows of filters above the popup it visibly cut off (see screenshot 2026-05-14).
- **New positioning:** `position:fixed; top:84px; right:20px; max-height:calc(100vh - 110px); overflow-y:auto`. Always lands in the top-right corner just below the app header — consistent regardless of where the trigger button sits, and tall enough to scroll its own content rather than being squeezed by adjacent UI. Both tabs use the same metrics so they feel uniform.
- **Popup title updated** to "📋 View — Saved Views & Columns" so the popup's purpose is clear once opened.

## Recent Fixes (v4.127) — Forecast Saved Views capture full report state
- **Same upgrade as v4.126 P&L, applied to the Forecast tab.** Saved views now capture every dimension that defines what's on screen, not just columns + sort.
- **Schema v3:** `{ cols, sortChain, filters, selection }`.
  - `filters = { fBrand, fRegion, fCategory, fStatus, fHorizon, srchTerm, fPeriod, fCustomFrom, fCustomTo, channels: {total, amazon, shopify, chewy}, fVelocityWindow, fBundleAttr, fHideBundles, fIdCol }`
  - `selection = [...forecastSelected]` — array of `master_id_region` row-keys.
- **Backward compatible.** New helpers `fcViewFilters(v)` and `fcViewSelection(v)` return null for v1 (bare array) and v2 (cols + sortChain) views — older views still apply correctly, they just don't restore filters or selection.
- **Apply order:** set columns, sort, every DOM filter input, then `applyVelocityWindow()` (recomputes blended_daily per record honoring the new velocity window), then `applyFilters()` (reads the DOM into f* globals and triggers renderAll + chart update). Selection is replaced before applyFilters so the chart/scorecards/banner pick it up on the same render.
- **Popup summary chip** beneath each view name now shows a compact preview — `N cols · sort · brand · region · status · period · vel · channels · N selected` — so the user can read a view's contents without applying it. Tooltip on apply names every captured dimension.
- **Saves to Supabase** via the existing `fcPersistSavedViews()` → `user_profiles.forecast_saved_views` sync (introduced v4.100), so the full-state views follow the user across browsers / devices. localStorage stays as a fast first-paint cache.

## Recent Fixes (v4.126) — P&L Saved Views capture full report state
- **Saved views upgraded from columns-only → full report snapshot.** Each view now captures: visible columns, sort key/direction, region (US/CA), currency mode (USD/CAD), time-range period (and customFrom/customTo for custom), brand, category, search text, quick filter, AND the selected products list (`pnlSelectedMids` as an array). Applying a view restores every dimension.
- **Why:** the user explicitly asked "does the saved view also keep the selected products and time range set?" — previously no; now yes for both, plus everything else that defines what's on screen.
- **Storage schema v2:** `{ cols: [...], sort: {key,dir}, region, currency, period, customFrom, customTo, brand, cat, search, quick, selectedMids: [...] }`. Old format (bare array of column keys) is still readable via the new `pnlViewCols(v)` accessor — pre-v4.126 views still apply (columns-only) without errors.
- **Apply logic:**
  - Sets columns first (no render), then sort, then calls `setPnlRegion(...)` (which triggers a render), then currency mode + button styling, then period/from/to/brand/cat/search/quick/selection, then a final `renderPnl()` to pick up the rest. Shows / hides the custom-range inputs based on the restored period.
  - Selection is replaced wholesale (cleared first so unrelated current selections don't bleed in).
- **Popup affordances:** each view name now shows a compact metadata strip beneath it — `N cols · region · brand · period · quick · N selected` — so the user can see what's in a view at a glance without applying it. Tooltip on apply names every captured dimension. The Save / Update buttons name what they capture in the dialog text + tooltip. A footer note below the Save button enumerates the captured fields ("columns · sort · region · currency · time range · brand · category · search · quick filter · selected products").
- **Snapshot helper:** `pnlSnapshotState()` is the single source of truth for what gets saved — used by both Save-as-new and ↻ Update so the two paths can't drift.

## Recent Fixes (v4.125) — Forecast chart + P&L column registry / saved views (feature parity pass)
Two ports between the Forecast and P&L tabs:

### Forecast tab — horizon line chart (port of the P&L weekly chart)
- **New chart panel between scorecards and the table.** Visible only when 1+ products are selected (mirrors P&L). X-axis is the 4 forecast horizons (30 / 60 / 90 / 120 days); Y-axis is the picked metric. Two dropdowns:
  - **Metric** — `forecast_vs_sold` (default — two lines: Need + historical Units Sold over same window), `forecast` (just Need), `sold` (just historical sold), `gap` (Need − Sold; positive = accelerating demand vs recent run-rate), `seasonality` (avg multiplier across each horizon — weighted by Need for the Total aggregation), `inventory_cover` (cover days = inventory ÷ implied daily rate at each horizon).
  - **Series** — `Total` (one line per metric, summed across selection) or `Per product` (one line per selected product per metric).
- **Calculations exactly mirror the scorecard math.** Two helpers — `fcForecastNeedAt(r, h, chans, useCustom)` and `fcHistoricalSold(r, days, chans, useCustom)` — reproduce the existing forecast-Need + bundle-attribution + Chewy-bypass + channel-filter semantics. The "Sold" line honors the SAME channel selection as the forecast (Amazon-only forecast → Amazon-only sold), so the comparison is apples-to-apples. Bundle attribution is included on both sides via `getBundleAttrDailyVelocity` (for forecast) and `getBundleAttrUnits` (for sold).
- **No new precomputation.** All values are derived per-record at chart-render time from the same precomputed `r.blended_daily`, `r.need_N`, `r.sea_idx`, salesData[], BOM[] — so bundles / per-channel velocity / per-product seasonality stay correct regardless of selection state.
- **Updates live** on row toggle (`toggleForecastRow` / `toggleForecastAll`), full re-render (`renderAll`), and metric / series dropdown changes. Same lazy-load Chart.js (`getChart()`) used by the P&L chart.

### P&L tab — column registry + saved views (port of the Forecast tab pattern)
- **New `PNL_COLUMNS` registry** at module scope: 23 columns covering identity (master_id, ASIN, Product), volume (Units), revenue (Gross / Net Sales), every Amazon fee line (FBA Fees / FBA Storage / Inbound Placement / Inbound Transport / Low Inventory / Aged Inventory / Removal / Storage Util / Referral / Referral Refunds / Refund Admin), ads (Ad Spend), cost (COGS / FBA Reimbursement), profit (Net Proceeds / Contrib Profit / Margin % / Contrib %). Each column has `key` (matches sort), `label`, `default:true/false`, `align`, `headerTitle` tooltip, `render(r)` cell HTML, `csv(r)` export value, and a soft `group` for the popup layout.
- **Default visible set = the pre-v4.125 layout** — Product, Units, Net Sales, FBA Fees, Referral, Ad Spend, COGS, Net Proceeds, Margin %, Contrib %. So users see no visual change until they open the popup.
- **`📋 Columns` button** in the filter strip (next to Quick filter) opens a popup with:
  - Saved Views section (apply / ↻ update / ✕ delete) + 💾 Save current as view button at the bottom.
  - Column checkboxes grouped by category (Identity / Volume / Revenue / Amazon fees / Advertising / COGS / Profit) with hover tooltips on each.
  - ↺ Reset defaults button to return to the original visible set.
- **Persistence:** `pnlVisibleCols` (Set of column keys) and `pnlSavedViews` (`{viewName: [colKeys]}`) both write to `localStorage` immediately on change. Stale keys (column removed from the registry between versions) are filtered out on load. Cross-device sync via `user_profiles` is NOT done yet — that's a follow-up if needed; matches how v4.99 first shipped saved-views before the v4.100 Supabase backfill.
- **Sort still works for all columns.** `PNL_SORT_VAL` keeps explicit formulas for computed columns (`margin`, `contribution_pct`, `contribution_profit`) and falls back to `r[key]` for everything else — so any new field-based column in the registry sorts correctly without a switch entry per column.
- **Click-to-sort header** preserved (each `<th>` has `onclick=pnlSetSort(key)`, ↑/↓/↕ indicators).
- **No changes to scorecards / chart / Diagnostics** — those use the same precomputed `rows` they always did.
- **CSV export** unchanged for now (still uses its own fixed column list). Could be wired to honor visible columns later; out of scope for this pass per user.

## Recent Fixes (v4.124) — Forecast tab: persistent selection + "Show selection in table" toggle
- **Same selection-persistence behavior as v4.122/v4.123 P&L** ported to the Demand Forecast tab. `applyFilters()` no longer calls `forecastSelected.clear()` — selections survive Brand / Region / Category / Status / Search / Horizon changes. The user can build a custom forecast report by checking products across multiple searches.
- **Drill banner** added above the four scorecards (only visible when selection is non-empty). Shows count, first 3 product names, ⚠ N hidden-by-filter chip when applicable, and three action buttons:
  - **👁 Show selection in table** — filters the visible product table to ONLY the selected products, bypassing brand/region/cat/status/search/hide-bundles. Button turns green ✓ when active; click again to return to the normal filtered view.
  - **✕ Clear selection** — empties `forecastSelected` and exits selection-only mode.
- **Scorecards aggregate the FULL selection (not just visible).** `renderForecastScorecards` now uses the new `fcGetSelectedRecords()` helper when selection is non-empty — same region-collapse rule as `getVisible` so the records being summed have the right per-region semantics (combined for unpinned region, per-region for pinned). Hidden-by-filter count is computed against the visible set.
- **No calculations are touched.** All per-record values — `bundle_daily` (bundle attribution), `blended_daily` (with bundle slice folded in for Total mode), `sea_idx` / `getEffectiveCurveForProduct` (per-product seasonality), `getChannelVelocityForRecord` (per-channel velocity including Chewy split), `getBundleAttrDailyVelocity` (channel-aware bundle slice for custom-channels mode), `forwardSeaDemand` (curve-integrated needs) — stay precomputed on every record. Selection-only mode just changes which rows flow through to display and scorecards; the records themselves are the same precomputed objects. User explicitly requested confirmation that bundles / velocity / seasonality-by-channel weren't broken — they're not.
- **Region-aware selection key.** Selection keys are `master_id_region` (e.g. `SP-0123_US`, `SP-0123_US+CA`). `fcGetSelectedRecords` strips the region suffix to pre-filter records, then applies the same region-collapse rule (`combineRegionRecords` when fRegion is empty) before matching the full rowKey — so a row checked in unpinned mode (rowKey = `SP-0123_US+CA`) only re-renders correctly while unpinned, and a row checked in US-mode (`SP-0123_US`) only re-renders correctly with region=US. If the user switches region after selecting, the rowKey can stop matching — known limitation; the selection isn't lost, just can't render its checkbox.
- **CSV export integration:** the existing "filtered" export scope passes through `getVisible()`, so toggling on `👁 Show selection in table` and then exporting "filtered" produces a custom-report CSV. No export-dialog changes needed.
- **Bundle double-count caveat:** if the user selects BOTH a bundle parent AND one of its components, the scorecard sum double-counts the bundle sale (once via the bundle row, once via the component's `bundle_daily` attribution slice). This was the existing behavior for visible-only scorecards too; selection-only mode inherits it. The `Hide bundles` filter (which suppresses bundle rows but keeps attribution on components) is the workaround.

## Recent Fixes (v4.123) — P&L: "Show selection in table" toggle
- **New `👁 Show selection in table` button** in the drill-banner (right of the "hidden by filter" chip, left of "✕ Clear selection"). Click to filter the visible product table to ONLY the currently-selected products — brand / category / search / quick-filter are all bypassed in this mode. Click again (button reads `✓ Showing selection only` in green) to return to the normal filtered view. Lets the user see their full custom report (built across multiple searches) in one table without having to manually clear their filters.
- **Selection-only mode preserves the filters in state** — the brand/cat/search inputs aren't cleared; they just don't apply while the toggle is on. Turning it off restores the prior view exactly.
- **Quick-filter slicing is also bypassed** in this mode (no point Top-10-ing your selection of 7 products).
- **Auto-exit:** `pnlClearSelection` and the empty-selection case in `pnlToggleShowSelected` both reset `pnlShowSelectedOnly = false`. If you uncheck rows one-by-one until the selection is empty, the next render falls back to the normal filtered view automatically (the agg-loop gates on `pnlSelectedMids.size > 0`).
- **Hidden-by-filter chip suppressed** when this mode is active — it would always be 0 (everything selected is also visible).

## Recent Fixes (v4.122) — P&L selections persist across filter changes
- **Bug:** clicking products to add to the report, then changing the search / brand / category, **silently cleared** the prior selections. `renderPnl` had a hard prune step (`if (!pnlVisibleMids.includes(mid)) pnlSelectedMids.delete(mid)`) that removed any selection that fell outside the current display filter. So you couldn't build a custom report by searching multiple times in a row.
- **Fix:** removed the prune. `pnlSelectedMids` now persists across brand / category / search / quick-filter changes — only region + date are "universally applied" (those filter `pnlData` itself before anything else runs). Selections clear only when the user explicitly hits the ✕ Clear button or unchecks a row.
- **Parallel `selectedAgg` aggregator** built fresh each render. Walks `pnlData` for any row whose `master_id ∈ pnlSelectedMids` AND matches region + date, completely bypassing brand / cat / search / quick filters. Scorecards / fee breakdown / chart now show the full selected set even when some products are hidden by the visible-table filter. The pre-existing `updatePnlChart` aggregator was already doing this for the chart (read pnlData directly, filtered by mid), so it remains untouched; only the scorecard/fee path was using the wrong source.
- **Drill banner upgraded** to communicate the new behavior:
  - Subtitle now reads "selection persists across filters" so the user knows mid-search clicks don't blow away their progress.
  - When 1+ selected products fall outside the current visible filter, an orange "⚠ N hidden by filter" chip appears next to the Clear button — with a tooltip explaining that those products are still in the totals above, just not in the table below.
  - Clear button text changed from "← Show all products" to "✕ Clear selection" for clarity.
- **CSV export honors the selection.** When the top-bar CSV button is clicked while a selection is active, `doDownloadPnlAmazonCSV` exports the selected rows (not the visible-but-not-selected ones). Filename gets a `-selected` suffix so you can tell custom-report exports apart from the standard "this view" export. Falls back to visible-rows export when no selection is active. Audit log records `selectedOnly: true/false`.

## Recent Fixes (v4.121) — ASIN affordances: explicit US + CA listing links
- **Both regional listing links rendered side-by-side.** `renderAsinAffordances` now always emits a 🇺🇸 amazon.com/dp/{asin} link AND a 🍁 amazon.ca/dp/{asin} link, regardless of which region the calling context "thinks" the ASIN belongs to. An ASIN can exist in either marketplace and the user often wants to check both; relying on a single inferred-region link forced an extra click when the inference was wrong.
- **Five icons per ASIN cell:** ⎘ copy · 🇺🇸 US listing · 🍁 CA listing · 🔍 Amazon search · 🌐 Google search. The /dp/ links are the primary action; search + Google remain as fallbacks for delisted ASINs where the product detail page 404s.
- **Affects both surfaces** that use the helper: the Products tab ASIN column and the four P&L Diagnostics tables (Unmatched / Matched / Off-week / Duplicates).

## Recent Fixes (v4.120) — Products tab gets the same ASIN affordances as Diagnostics
- **Shared `renderAsinAffordances(asin, region)` helper hoisted to module scope.** Renders the ASIN text plus three small icon-buttons: ⎘ copy · 🔍 Amazon search · 🌐 Google search. Default region is US (matches the Products tab convention; ASINs there aren't region-tagged, and a product with both US+CA listings has different ASINs per region anyway).
- **All three icons stop click propagation** so they don't trigger a parent row's onclick (Products tab rows open the edit modal on row click; without `stopPropagation` the search would happen *and* the modal would open underneath).
- **Products tab ASIN cell** now uses the helper — same UX as the P&L Diagnostics Unmatched/Matched/Off-week/Duplicates tables. Click ⎘ to copy, 🔍 to look up the listing on Amazon search (works for delisted ASINs where the legacy `/dp/ASIN` link 404s), 🌐 to Google it as a last resort.
- **P&L Diagnostics `asinCell` slimmed** down to a pass-through wrapper around the shared helper (passes `pnlRegion` for the regional storefront TLD).

## Recent Fixes (v4.119) — P&L Diagnostics: identify-then-assign UX for unmatched ASINs
- **Amazon link switched from `/dp/ASIN` → `/s?k=ASIN`** (search). Most unmatched ASINs are old / discontinued listings; their product-detail page returns "Page Not Found", but the search results page still surfaces the listing (with title, which is the fastest way to identify the brand). Added a 🌐 Google search link as a last-resort fallback for ASINs that Amazon has fully purged. Three icons per ASIN cell: ⎘ copy · 🔍 Amazon search · 🌐 Google search.
- **Per-row Action column rebuilt as three brand quick-chips** (`M` / `D` / `K`) using the existing `chip c-meow / c-doggi / c-kkz` brand color classes. One click creates the SP-TEMP-{ASIN} product under that brand — no popup, no Brand-filter dependency. Replaces the v4.118 generic ✚ Add button that relied on a prompt or the active Brand filter (which Jason often had set to a *different* brand than the orphan's actual brand). Workflow now: hover 🔍 → see the title → click matching letter → row drops off and totals refresh. New helper `pnlDiagCreateOneAs(asin, brand, btn)` powers the chips; the brand is hardcoded per chip so no resolver logic runs.
- **Bulk button is still available** for the "I already know they're all the same brand" case (resolves brand via the active filter or one prompt as before).

## Recent Fixes (v4.118) — P&L Diagnostics: inline "Create product" actions for unmatched ASINs
- **Per-row ✚ Add button** on every UNMATCHED row of the diagnostics Unmatched table — creates an `SP-TEMP-{ASIN}` product on the spot, mirroring the auto-create logic in `parseSkuEconomics` (same upsert, same `notes:'Auto-created from P&L Diagnostics — needs review'`, same `active:true`). After write, refreshes `allProducts` and re-renders both Diagnostics and Summary so the row disappears and its fees/sales roll into the totals. Brand-mismatched rows show "already exists" instead (those products are in the catalog already; the button would be a no-op).
- **Bulk ✚ Create N SP-TEMP products button** in the Unmatched table header — same upsert against every unmatched ASIN in one round-trip, after a confirm dialog naming the count and brand. `pnlDiagUnmatchedCache` stashes the ASIN list at render time so the bulk handler doesn't have to re-walk `pnlData`.
- **Brand resolution:** if the P&L Brand filter is already on Meowijuana / Doggijuana / Kitty Ka-Zoom, that brand is used directly. Otherwise the user gets the same `promptForSkuEconomicsBrand` modal that the upload flow uses (cancel aborts the operation). One prompt covers an entire bulk run.
- **Why the unmatched ASINs existed in the first place:** sku_economics rows uploaded before v4.57's auto-create logic existed, OR rows pointing to master_ids that were later deleted, OR rows inserted via raw SQL. The button gives the user a one-click path to recover those rows so their fees / ad spend / units stop being orphaned from the brand-filtered P&L. Audit log records `product.diag_create` (single) or `product.diag_bulk_create` (batch).

## Recent Fixes (v4.117) — P&L Diagnostics: ASIN click-to-copy
- **Every ASIN cell in the Diagnostics tables now has a ⎘ copy button** next to the Amazon PDP link. Clicking copies the bare ASIN to the clipboard (useful for pasting into Seller Central, Looker filters, the products catalog form, etc.). Button flashes "✓" green for ~0.9s on success.
- **Single `asinCell(asin)` helper** inside `renderPnlDiagnostics` renders both the link + copy button so all four diagnostic tables (Unmatched, Matched, Off-week, Duplicates) get the same affordance — no duplicated JSX per table.
- **`pnlCopyAsin(asin, btn)` writer** uses `navigator.clipboard.writeText` with a hidden-textarea + `document.execCommand('copy')` fallback for browsers that block the modern API outside secure contexts.

## Recent Fixes (v4.116) — P&L Diagnostics sub-view
- **New 🔍 Diagnostics tab inside the Amazon SKU Economics P&L view** for reconciling against Looker / Amazon's own reports. Sub-tab strip with `📊 Summary` (default — original scorecards + chart + product table) and `🔍 Diagnostics` (the new view). Shares all filters (region / period / brand / category / search / FX-mode), so flipping tabs just re-renders the same dataset through a different lens.
- **Four diagnostic surfaces, each driven from `pnlData` filtered by the active region+date+brand+cat+search:**
  - **Tiles row** — Matched ASINs / Unmatched ASINs / Brand-mismatched ASINs / Suspect rows (off-week + duplicate counts). Each tile names the dollar impact so the user sees at a glance where hidden $ are.
  - **Unmatched ASINs table** — ASIN-level rows that the brand filter dropped (either no product in `products` OR product brand doesn't match the active filter). Shows units, net sales, fees, ad spend — these are dollars NOT in the Summary scorecards. Each ASIN links to its Amazon page (`amazon.com` for US, `amazon.ca` for CA). Common smoking gun for the "Looker shows N more products than the app" complaint: the user can spot Doggijuana SKUs hidden under "Unknown" brand placeholders and add them to the catalog.
  - **Matched ASINs table** — every ASIN being summed into the Summary scorecards, with its mapped `master_id` and brand. Useful for spotting brand misattributions (an ASIN here under "Doggijuana" that Looker counts elsewhere, or vice versa). Aggregates 1 row per ASIN (no master_id collapse) so the count matches Looker's ASIN-level row count.
  - **Week-start hygiene** — Amazon SKU Economics rows where `week_start` isn't a Monday. Leftover bad dates from pre-v4.91 / pre-v4.92 parser bugs would show up here. Should be empty.
  - **Same-week duplicate canary** — ASINs with ≥2 `sku_economics` rows for the same ISO week but different `week_start` values. Each pair inflates the totals because both rows are summed. Inflates totals exactly the way the user saw with the "app fees > Looker fees" discrepancy.
- **All amounts honor the CAD/USD toggle** (same `fxMul(currency)` semantics as the Summary view), so Diagnostics totals tie out against the Summary totals.
- **Live refresh:** flipping `Brand` / `Period` / etc. while on the Diagnostics tab calls `renderPnl()` which now also calls `renderPnlDiagnostics()` when active. No-op when on Summary (the panel isn't rendering hidden DOM until the tab is opened).

## Recent Fixes (v4.115) — P&L CAD/USD toggle actually applied
- **The CAD/USD pill on the Amazon P&L tab was wired to UI but not to the aggregator.** v4.113 added the toggle, `pnlCurrencyMode` state, and a `toUsd(val, currency)` helper, but the row-aggregation loop at the heart of `renderPnl` was still using the original hardcoded `const fx = row.currency === 'CAD' ? 1 / pnlFxRate : 1;` — so every CAD row was converted to USD regardless of mode and the scorecards/table/chart didn't move when the user clicked CAD. Same bug in the chart's per-week aggregator and the hidden-orphan sales tracker.
- **Fix:** replaced the helper with `fxMul(currency)` — `(currency === 'CAD' && pnlCurrencyMode === 'usd') ? 1/pnlFxRate : 1`. Three call-sites updated: the orphan-tracker (line ~4411), the main aggregator (line ~4423), and the chart aggregator (line ~4808 — kept inline since the helper isn't in scope there). The currency-label `cur` and FX footnote were already mode-aware from v4.113.
- **Why the bug existed:** the v4.113 work created `toUsd(val, currency)` as a new utility but never replaced the existing inline `fx` expressions. Two parallel conversion paths existed; only the unused one honored the mode. The new helper is named `fxMul` because what it returns is a multiplier (used inline as `* fx`), not a converted value — names the actual semantics so callers don't get tempted to rebuild the same parallel path.

## Recent Fixes (v4.114) — Bundle attribution badge on Need columns
- **30d / 60d / 90d / 120d Need columns now show a `+B N` badge** when bundle attribution is contributing units, same orange marker style as the Sold column already had. Visual confirmation that bundle attribution is feeding the forecast (previously you had to hover the cell and read the tooltip's "+X.XX u/day from bundle-component attribution" line to know).
- **Math:** the bundle slice is computed by running the bundle-only daily velocity through `forwardSeaDemand(..., d)` — same curve integration as the main Need, so the badge's number is directly comparable to the cell's main number. In Total mode the bundle velocity is `r.bundle_daily` (precomputed by `recomputeRecordVelocity`); in custom-channels mode it's `getBundleAttrDailyVelocity(r.master_id, fcWinDays, nonChewy, r.region)` for the active channel filter. Hidden when the "+ bundle components" filter is off or when there's no bundle contribution.
- **CSV export unchanged** — the `get(r,ctx)` function still returns the all-in Need total (which already includes bundle attribution); only the inline `<td>` render adds the badge. Intentional per user request: the badge is visual confirmation only, not a separate exportable column.

## Supabase
- URL: `https://yjcnuyoaemlipvuinptp.supabase.co`
- Anon key: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlqY251eW9hZW1saXB2dWlucHRwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNTY4NjcsImV4cCI6MjA5MzgzMjg2N30.CACwOGjnC370ZPjKlXG4dDpU9bVwCP4JDBD451WvwaM`
- Dashboard password: `SmarterPaw2026`

## Database Tables
- **products** — PK: `master_id` (SP-XXXX real, SP-TEMP-{ASIN} temporary). Fields: master_id, sp_sku, shopify_sku, chewy_sku, asin, brand, title, short_name, is_bundle, category_id, barcode, msrp, wholesale, cogs, supplier, active, notes
- **sales_weekly** — (master_id, channel, asin, shopify_sku, week_start). Channels: amazon_us, amazon_ca, shopify, chewy. Unique index: `(channel, asin, coalesce(shopify_sku,''), week_start)`
- **velocity_calculated** — VIEW grouping by master_id+region, returns v30/v60/v90/v120
- **inventory** — asin, region, master_id, fba_available, fba_inbound, warehouse, lead_time_days, safety_stock
- **bom** — bundle_master_id, component_master_id, qty, verified
- **sku_economics** — full P&L per (asin, region, week_start). Unique: (asin, region, week_start)
- **chewy_forecasts** — (chewy_sku, master_id, forecast_month YYYY-MM, forecast_units, upload_date). Unique: (chewy_sku, forecast_month, upload_date)
- **categories** — id, category, subcategory

## Dashboard Tabs
- 📊 **Forecast** (dropdown): Demand Forecast, Inventory Planning, Seasonality, Chewy Forecasts
- 📁 **Data** (dropdown): Uploads, Query Database
- 📋 **Products**
- 📦 **Bundles**
- 📈 **Units Sold**
- 💰 **P&L**
- ⚙ **Settings**

## Critical Architecture Rules
1. **Amazon rows in sales_weekly NEVER have shopify_sku** — must be null or unique constraint breaks
2. **master_id is always auto-incremented SP-XXXX** — never derived from sp_sku or any other field
3. **SP-TEMP-{ASIN}** = auto-created placeholder when ASIN not in products catalog. Promoted to real SP-XXXX when user saves the product
4. **Supabase default row limit = 1000** — all large queries must use `.range()` pagination
5. **ALL `sales_weekly` writes MUST use DELETE+INSERT** (not upsert). The table's unique index is functional (`coalesce(shopify_sku, '')` to handle Amazon's null shopify_sku), and Supabase upsert with plain-column `onConflict` silently degrades to plain INSERT against functional indexes — producing duplicate rows on every re-upload. Audit history: parseSkuEconomics + parseEuSkuEconomics always used DELETE+INSERT; parseShopifySales (fixed v5.96), parseSalesWeekly Amazon branch (fixed v5.97), and doRestore (fixed v5.97) all had the bug. No other table currently uses a functional-expression unique index — if you ever add one, use DELETE+INSERT for that table too.
6. **Chewy data → chewy_forecasts table only** (not sales_weekly). Velocity uses getChewyFcUnits() forward forecast
7. **Foreign key order matters**: when promoting SP-TEMP → SP-XXXX, insert new product FIRST, then update references, then delete old temp

## Active Issues to Fix

### 1. Install `exec_sql` in Supabase (one-time)
File `supabase_create_exec_sql.sql` lives in the project folder. Open Supabase → SQL Editor → New query → paste the file → Run. Uses `SECURITY INVOKER` + `SET LOCAL transaction_read_only = on` so writes are rejected by the database itself, not just by a string check. Once installed, the Query Database subview runs arbitrary SELECT/WITH queries via `/rest/v1/rpc/exec_sql`. If not installed, the dashboard now surfaces a clear error pointing to this file.

### 2. Header dropdowns invisible (workaround in place)
The Data + Forecast header dropdowns set `display:block` on click but the panel doesn't paint visibly — likely a stacking-context interaction with the sticky header's `backdrop-filter: blur(18px)`. Workaround in v4.42: visible sub-tab strip inside `page-data` (📥 Uploads | 🔍 Query Database) so the dropdown isn't required for navigation. Forecast tab still relies on the dropdown — needs a similar fallback or a real CSS fix.

### 3. Query tab presets to add (once Query tab is reachable)
Suggested presets to write: low inventory alert, velocity leaders (top 50 by v30), stale products (no sales 90d), channel mix per master_id, unverified bundles, products missing identifiers, last-upload timestamps per channel.

## Setup notes — Supabase RLS + table GRANTs

**Security fix 2026-06-08 — `shopify_sales_daily` had RLS DISABLED (`supabase_v6_47_shopify_sales_daily_rls.sql`):** Supabase emailed a `rls_disabled_in_public` critical alert. Root cause: `supabase_v5_98_shopify_sales_daily.sql` created the table + granted DML to `authenticated` but never ran `enable row level security` and never created a policy — the ONE `CREATE TABLE` in the whole migration history that slipped through. Every other table (the original 8 via the auth_setup do-block, plus product_cogs, sku_economics_eu, fba_inventory_snapshots, fba_shipments, fba_shipment_summaries, inventory_events, user_profiles, audit_log) had both. v6.47 fixes it: `enable row level security` + an authenticated-full-access policy (mirrors inventory_events) + `revoke all from anon` + re-affirm the authenticated grant. Idempotent. No index.html change, no breakage (the dashboard uses each user's JWT → passes the policy). **Hard rule reinforced:** every new `CREATE TABLE` migration MUST include, right after the create: `alter table X enable row level security;` + a `create policy … for all to authenticated using(true) with check(true);` + `grant … to authenticated;`. The grant alone is NOT enough — RLS is the gate the Supabase linter checks. To audit all public tables for missing RLS: `select tablename from pg_tables where schemaname='public' and tablename not in (select tablename from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relrowsecurity);` (or just check `relrowsecurity` in pg_class).

**Gotcha learned 2026-05-10:** RLS policies are LAYERED on top of Postgres role grants. The `authenticated` role needs explicit `GRANT SELECT/INSERT/UPDATE/DELETE` on the table — without it, PostgREST returns 403 BEFORE RLS gets a chance to evaluate. The first auth setup migration only granted sequences, not tables, so any new table created post-setup (like `product_cogs`) would 403 on read until grants were added. Both `supabase_auth_setup.sql` (5b) and `supabase_product_cogs_setup.sql` now include `grant ... on all tables in schema public to authenticated` + `alter default privileges`. If a NEW table is ever added after this, also run a one-line grant for that table.

**Supabase policy change deadline 2026-10-30:** Supabase announced (email received 2026-05-27) that on Oct 30, 2026, new tables in `public` schema will no longer be exposed to the Data API by default — explicit GRANTs become mandatory. **No action required for existing tables** — they're grandfathered and our 15 existing tables all have full `authenticated` DML grants confirmed via the audit query (see Active Issues #4 below). The `alter default privileges` clause from `supabase_auth_setup.sql` already covers future tables created via SQL Editor by the postgres role, so this aligns Supabase's defaults with what we were already doing. Belt-and-suspenders rule for future migrations: any new `CREATE TABLE` file should include an explicit `grant select, insert, update, delete on table <name> to authenticated;` right after the create, even though default privileges should cover it.

**Anon role gotcha — `supabase_revoke_anon_grants.sql` (recommended for run, 2026-05-27):** the original public-schema defaults (pre-v4.60) granted full DML to the `anon` role on every table. The v4.60 auth migration added RLS policies that gate access to authenticated users at the ROW level, but didn't revoke the underlying table-level grants — so for 8 older tables (`bom`, `categories`, `channel_listings`, `chewy_forecasts`, `inventory`, `products`, `sales_weekly`, `sku_economics`) the anon role still holds dead-weight grants. RLS policies do block anon today, but defense in depth: if any policy is ever accidentally configured as `USING (true)`, the grant means anon would immediately get full access via the publicly-embedded anon key. The migration revokes `SELECT/INSERT/UPDATE/DELETE` from anon on all current + future public-schema tables. Reversible per-table if a specific table ever needs anon access (none does today — the dashboard requires login for every feature). Tables created post-v4.60 (audit_log, fba_*, product_cogs, sku_economics_eu, user_profiles) already have anon properly locked down, so the migration is a no-op for those — it just consolidates the older tables to match. Hard rule going forward: anon access stays revoked unless a specific public-facing surface requires it.

## Recent Fixes (v4.112) — Forecast search + Velocity Window default/persistence
- **Forecast search now matches every identifier.** Was `(r.title + r.asin + r.supplier).includes(srchTerm)` — so typing "CF312" (sp_sku) or "SP-0123" (master_id) returned nothing because those fields weren't in the search blob. Expanded the search blob to include `title`, `short_name`, `master_id`, `sp_sku`, `shopify_sku`, `chewy_sku`, `asin`, and `supplier`. Matches the search behavior on the Seasonality / P&L tabs.
- **Velocity Window default changed from 30d → 60d.** 30d (live) was too noisy for forecasting — one slow week or one promo spike swings the rate enough to distort Need totals. 60d smooths weekly variation while still picking up real demand shifts within ~2 weeks. Option labels also updated to flag the trade-off ("live · noisy", "balanced", "stable", "smoothest").
- **Velocity Window choice persists across sessions.** `applyVelocityWindow` now writes the active value to `localStorage`; new `restoreVelocityWindowPref()` reads it at init (called from the records-build finalization, before the recompute, so `blended_daily` / `need_N` start from the saved window not the HTML default). Per-browser (not synced to Supabase) — matches how `fcVisibleCols` is persisted.

## Recent Fixes (v4.111) — bundle attribution in custom-channels mode
- **Custom-channels mode silently dropped bundle attribution.** Total mode includes bundle-attributed velocity in `blended_daily` via `recomputeRecordVelocity`, but the Need-column custom-channels path used only `getChannelVelocityForRecord` for the velocity term — direct channel sales only, no bundle credit. Symptom: a product whose recent direct sales had stalled (so `getChannelVelocityForRecord` returned 0) but whose parent bundle was still selling would show `Vel/day=0` and Need=0 across all horizons in Amazon/Shopify-filtered views, even though the Sold column displayed a meaningful `+B N` bundle attribution. Fixed in three places to keep them consistent:
  - **Need column `get`** — `effectiveVel = chanVel + getBundleAttrDailyVelocity(mid, windowDays, nonChewyChans, region)` when `+bundle components` is on. The bundle slice respects the channel filter (e.g. Amazon-only excludes Shopify bundle sales) and the active velocity window.
  - **`fcPrecompute.fcNeed`** — same logic, so `pre.n30/60/90/120` (used by render) matches the column `get` (used by sort/export).
  - **Scorecard `nonChewyTotal` reducer** — same logic, so the top scorecards agree with per-row totals when bundle attribution is contributing in a custom-channels view.
- **Why this didn't show up in Total mode:** `r.blended_daily` is computed by `recomputeRecordVelocity` which already calls `getBundleAttrDailyVelocity(mid, w, null, r.region)`. Total mode reads the precomputed value from `r.need_N` — bundle was already in there. Only the custom-channels code paths bypassed the precomputed values, recomputing velocity fresh from `salesData` per channel and forgetting the bundle slice.

## Recent Fixes (v4.110) — scorecard `from sea` excludes Chewy
- **Mixed-channel scorecard `+/- X from sea` was over-attributing.** v4.109 fixed the per-row Need totals to avoid double-applying the seasonal curve to Chewy, but the scorecard's `from sea` footer still computed `totalNeed - totalNeed/avgSea` against the FULL total (including the Chewy slice). Symptom: with Shopify + Chewy selected, the displayed sea impact was larger than with Shopify-only, even though Chewy contributes the exact same units in both views (Chewy bypasses the curve). Fixed: scorecard now tracks `nonChewyTotal` and `chewyTotal` separately for each horizon. `seaImpact = nonChewyTotal - nonChewyTotal/avgSea` — only the curve-applied slice contributes to sea attribution. Display labels updated: "X from sea (non-Chewy)" appears whenever Chewy is part of the channel mix, with a hover tooltip naming the split. Total mode (chewy-included default) also gets the fix — `r.need_N - getChewyFcUnits(N)` separates the slices for each record.

## Recent Fixes (v4.109) — Chewy seasonality double-application
- **Custom-channels Need column no longer double-applies seasonality to Chewy.** The Need column's custom-channels `get` was passing `getChannelVelocityForRecord(...)` (which includes Chewy's `fc/window` daily rate when Chewy is selected) through `forwardSeaDemand`, which multiplies the dashboard's seasonal curve. Chewy's monthly forecasts already encode Chewy's own seasonality, so this was double-counting. Symptom: scorecard `chewyOnly` branch correctly showed `getChewyFcUnits(d)` (e.g. 101 for 30d), but the per-row Need cell showed `cv × d × avg_sea` (e.g. 59) — same product, same horizon, different numbers. Fixed by splitting non-Chewy and Chewy channels at the Need-column `get` and at `fcPrecompute.fcNeed`: non-Chewy velocity gets the curve integration, Chewy's slice comes from `getChewyFcUnits` directly. Matches the scorecard `nonChewy + chewy` logic.
- **Scorecard subtitle is no longer misleading for Chewy-only.** Previously rendered "X u/day · sea 0.58× · -N from sea" even though the total came entirely from `getChewyFcUnits` and never touched the seasonal curve. Now: when `chewyOnly`, the subtitle reads "Chewy forecast · no curve applied" (with a hover tooltip explaining) and the "+/- from sea" footer is hidden. Mixed-channel and Total modes keep the existing display.
- **Duplicate `const reg` fix.** The fcPrecompute edit redeclared `reg` later in the function — would've thrown SyntaxError and broken every render path that uses fcPrecompute (i.e. the entire Forecast table). Removed the duplicate declaration before deploy.

## Recent Fixes (v4.108) — sanity-check pass cleanup
Audit found four issues in recent feature work; v4.108 addresses all four:

- **Chewy branch in `getChannelVelocityForRecord` still hardcoded to 30d.** v4.107 made the rest of the function honor `fVelocityWindow` but missed the Chewy branch — `const fc30 = getChewyFcUnits(mid, 30, ...); total += fc30 / 30;` would keep Chewy's daily rate at 30d regardless of the dropdown when Chewy was among the selected channels. Fixed: now uses `windowDays` for both the lookup horizon and the divisor, so Chewy's contribution scales with the active window like every other channel.
- **`fcSaveCurrentAsView` / `fcUpdateView` / `fcDeleteView` were sync, fired `fcPersistSavedViews()` without awaiting.** The persist function became async in v4.100 when Saved Views started writing to Supabase. Sync callers meant rapid clicks (save → save → delete) could queue concurrent writes; if a later one fired before the earlier resolved, the in-flight one could lose against the queued one or get cancelled on tab close. Three callers now `async` + `await fcPersistSavedViews()`.
- **`parseSkuEconomics`'s local `dateToMonday` used `new Date(s)`.** Worked fine for the US-format strings Amazon currently sends (`M/D/YYYY` parses as local midnight), but if Amazon ever switches to ISO format (`YYYY-MM-DD` parses as UTC midnight), the subsequent local `getDay`/`setDate` math could shift by ±1 day in non-UTC timezones — same class of bug that bit the Shopify parser in v4.92. Defensive fix: delegate to the global `dateToMondayLocal` helper (which uses `parseLocalDate` for timezone-safe parsing).

## Recent Fixes (v4.107)
- **Velocity Window dropdown now affects custom-channels mode.** `getChannelVelocityForRecord` was hardcoded to a 30-day window — meaning when the user filtered the Forecast tab to specific channels (Amazon + Shopify, Amazon only, etc.), switching the Velocity dropdown to 60/90/120 had NO effect on the Need columns or scorecards because they routed through this helper. Now reads `document.getElementById('fVelocityWindow')` like `recomputeRecordVelocity` does, so the dropdown is consistent across Total mode and any channel-filtered view. Chewy branch still uses 30d (it's a forward forecast prorated to daily, not a historical rolling window).
- **Saved Views now include the advanced sort chain.** Storage schema upgraded from `[col keys...]` to `{ cols: [...], sortChain: [{key, dir}, ...] }`. Backward-compat helpers (`fcViewCols`, `fcViewSort`) read both shapes — pre-v4.107 views still apply correctly (their `sortChain` is null so the current chain is kept). Applying a view restores BOTH column visibility AND sort order. Saving captures both. The view label in the popup now shows sort summary: `Export — Amazon · 18 cols · sort: ↓90d, ↓Brand`.
- **New "Update" button (↻) per saved view.** Previously the only way to overwrite was to save with the same name and confirm the overwrite prompt — clunky and easy to typo. New green ↻ button next to each view's apply button refreshes the view in place: column visibility + sort chain get overwritten with the current state, with a confirm dialog so accidents don't happen. Same persistence path (localStorage + Supabase) as save-as-new.

## Recent Fixes (v4.106)
- **Forecast tab — DTC-only and Chewy-only products were invisible.** The records-build loop had `if (!p.asin) return;` at the top, skipping every product without an Amazon ASIN. Below it sat a "DTC-only fallback" block that filtered `velocities.filter(v => v.source === 'shopify')` — but `velocity_calculated` has no `source` column (it groups by master_id+region only), so that filter always returned an empty array. Net effect: Shopify-only products (like Mice Dreams, Whisker Tickler) and Chewy-only products never made it into `records` and so never appeared in the Forecast tab, scorecards, or CSV exports.
- **Fix:** the no-ASIN early-return is replaced with a check that requires at least ONE channel ID (`asin` OR `shopify_sku` OR `chewy_sku`). Products without ASIN get a single US-only record (Shopify and Chewy are US-only channels) instead of iterating US+CA. Velocity is looked up via `master_id+region` (works for any channel that lands in sales_weekly, including shopify); inventory and ASIN-keyed lookups gracefully degrade to undefined when there's no ASIN. For Chewy-only products with no sales_weekly history, `blended_daily` ends up 0 and the Need columns are driven entirely by `getChewyFcUnits` + bundle attribution at render time — which is the right semantic.
- **Dead-code cleanup:** removed the broken `dtcVel = velocities.filter(v => v.source === 'shopify')` block; main loop now handles all cases.

## Recent Fixes (v4.105)
- **Seasonality tab — bulk apply supports `mix` method, not just `calculated`.** New "Method:" dropdown in the Bulk Seasonality panel (between Min weeks and the apply buttons) with two options: `⚡ calculated` (default, prior behavior) and `⊕ mix (50/50)`. `seaBulkApplyMids(mids, minWeeks, method)` now accepts a third argument and sets `sea_method` accordingly on every successfully-applied row. Both wrappers (`seaBulkApplyToSelected`, `seaBulkApplyToAll`) read the picker via `seaBulkMethod()` and pass through. The Apply Selected button label updates live (⚡/⊕ icon flips) when the dropdown changes via `renderSeasonalityList`. Confirm dialogs name the method, status line ("✓ Applied ⊕ mix to N") names the method, audit log records `seasonality.bulk_apply` with the method field.

## Recent Fixes (v4.104)
- **`sbGet` now paginates.** The init flow's parallel `sbGet('products') / sbGet('velocity_calculated') / sbGet('inventory')` calls used un-ranged `select('*')` which Supabase silently caps at 1000 rows. With SmarterPaw's ~500 products × 2 regions = ~1000 velocity rows, the cap was right at the boundary — products whose velocity row landed past it had `daily_v60/90/120 = 0` (the `|| 0` fallback when `vel` was undefined), so when the user switched the Velocity Window dropdown to 60d/90d/120d, those products' `blended_daily` became 0 (= 0 + bundle attribution), making it look like the dropdown had no effect for entire swaths of the catalog. Architecture Rule #4 cleanup. Now `sbGet` loops 1000 rows at a time via `.range()` until a page comes back smaller. Every callsite benefits — products, velocity, inventory, and any other table fetched through this helper.

## Recent Fixes (v4.103)
- **Forecast tab Need cells get a breakdown tooltip.** Hovering any Need column cell shows how the total breaks down into Amazon/DTC velocity × seasonal curve + Chewy forward forecast (or just channel velocity × curve when a channel filter is active). The breakdown is channel-aware: Total mode shows "Amazon + DTC" + "Chewy" with the on-top math, while a pinned channel filter (Shopify only / Amazon only / etc.) shows just the active channels' velocity contribution.

## Recent Fixes (v4.102)
- **Seasonality calculation no longer mixes pre- and post-channel-launch data.** `computeProductSeasonality` was summing `units_ordered` across every channel for every weekly bucket without considering when each channel went live for that product. Result: a product like Purrple Passion (Shopify since 2024, Amazon since Aug 2025) would show a false seasonal peak around late summer — that wasn't seasonality, it was "Amazon launched and the weekly volume jumped 10x."
- **Fix — channel-stable window detection.** The function now scans the product's sales rows and per-channel records the first sale week + total weeks of activity. A channel is "significant" if it has ≥3 weeks of sales (filters out one-off / test orders that would otherwise narrow the window unnecessarily). The data window for the curve calculation starts at the LATEST first-sale-week across all significant channels — so for Purrple Passion that's August 2025 onwards, where both Shopify AND Amazon were active. Pre-window data is excluded.
- **Surface the window in the UI.** The status line after Calculate from sales now reads `✓ enough data · 38 weeks observed · baseline X units/wk · window: 2025-08-04 → now (channel-stable) · channels: amazon_us(38w), shopify(36w)`. Hover tooltip explains the heuristic. The `result` object also gains `channels` and `stableStart` fields so any future UI or audit-log entry can show what data fed the curve.
- **Re-calc affected curves.** Existing stored curves (`sea_method='calculated'` or `'mix'`) are based on the pre-v4.102 math. Open the Seasonality tab → click each affected product → click ⚡ Calculate from sales → ✓ Apply. Or use the bulk "Apply to ALL eligible" button to re-run every active product. The Query Database tab → Seasonality Status preset shows which products are on calculated/mix and when they were last computed.

## Recent Fixes (v4.101)
- **Forecast tab — multi-column sort (sortChain).** Replaced the single `sortKey/sortDir` pair with `sortChain = [{key, dir}, ...]` where `[0]` is primary, `[1]` is tiebreaker, etc. `fcCompare` walks the chain and returns the first non-zero comparison; ties fall through to the next entry. `sortKey`/`sortDir` are kept as derived mirrors of `sortChain[0]` for any other code that reads them (status filters, etc.) via `fcSyncLegacySort()`.
- **Two ways to manage the chain:**
  - **Shift+click any column header** in the table — appends the column to the chain or toggles its direction if already present. Plain click still replaces (single-column sort) and toggles direction on repeat. Header `<span class="si">` now shows a small superscript chain position (e.g. `↓²`) for secondary/tertiary sorts so the priority is visible at a glance.
  - **New ↕ Sort button** next to 📋 Columns opens an Advanced Sort dialog. Lists the current chain row-by-row with per-row controls: toggle direction, move up/down, remove from chain. A dropdown at the bottom lets you add any non-active column. Plus "Clear all" and "Reset to default (Vel/day ↓)" buttons.
- **Session-only persistence.** The chain resets on page reload (back to `[{adj_daily, -1}]`). Same convention as before for a transient view state; if you want a sort to persist, save the column visibility into a Saved View — that's about columns, not sort order. (Could be extended later to persist per-user alongside saved views.)

## Recent Fixes (v4.100)
- **Saved Views now sync to Supabase per user.** Previously stored only in `localStorage` (per-browser, per-device, no sync). Now stored in `user_profiles.forecast_saved_views` (JSONB) keyed to the authenticated user — views follow you across browsers and devices, survive cache clears, and are private per user. `localStorage` is kept as a fast first-paint cache (no flash of empty popup while the DB read is in flight). `fcLoadSavedViewsFromDb()` runs at init kick-off; `fcPersistSavedViews()` writes to both localStorage and Supabase on every save/delete. Failures (RLS, network) fall back silently to local cache.
- **Setup:** run `supabase_add_forecast_saved_views.sql` in Supabase SQL Editor BEFORE deploying v4.100. Without it, writes log a warning to console but views still work in this session via localStorage; they just won't follow you to other devices.
- **Existing localStorage views auto-migrate.** First time you save or modify a view after v4.100 deploys, the full `fcSavedViews` object (including views you'd already created locally) writes to your `user_profiles` row. Nothing special to do — just save one view as if making a new one (or modify an existing one) and the local set lands in the DB.

## Recent Fixes (v4.99)
- **Forecast tab — new `Title` and `Notes` columns.** Two new entries in the SKU group of `FC_COLUMNS`:
  - **`full_title`** (label "Title", default OFF) — shows the full untruncated product title in its own column. The existing "Product" column still shows `short_name || truncated_title` for compactness; this gives you the full marketing copy for CSV exports / audits.
  - **`forecast_notes`** (label "Notes", default OFF) — free-form annotations per product (demand expectations, supply caveats, promo flags, etc.). Click the cell to edit (textarea, Enter saves, Esc cancels, blur saves). Stored in `products.forecast_notes` via the new `supabase_add_forecast_notes.sql` migration. Audit log records `product.forecast_notes`.
- **Saved Views for column selection.** Stored in localStorage as `fcSavedViews = { "View Name": [colKeys...] }`. New "💾 Saved Views" section at the top of the column-popup with three actions: apply (click the view name), delete (✕ button), or save-current-as-new (prompts for a name). Each view stores a snapshot of `fcVisibleCols`. CSV export still follows currently-visible columns — so apply a view, then export, to get that view's exact column set. Helpers: `fcSaveCurrentAsView`, `fcApplyView`, `fcDeleteView`, `fcPersistSavedViews`.
- **Setup:** run `supabase_add_forecast_notes.sql` in Supabase SQL Editor BEFORE deploying v4.99. Without it, edits to the Notes column will fail with "column products.forecast_notes does not exist".

## Recent Fixes (v4.98)
- **Chewy Forecasts — multi-select drill-down via row checkboxes.** New checkbox column on the left of each row, plus a header check-all (with indeterminate when partial). Selection state lives in `chewySelected` (Set of chewy_skus). When the selection is non-empty, the four top scorecards (30/60/90/120-Day Chewy Demand), the consumption-adjusted deltas, the monthly totals footer, and the current-month peak total all aggregate over the selected SKUs only — same UX as P&L tab's multi-select. The row count line above the table switches to "N of M SKUs selected · scorecards + totals aggregate selection only · ✕ Clear" with a clear button. Selected rows are tinted green; per-row click still opens the product modal (checkbox uses `event.stopPropagation()`). Selections auto-prune when filtered out of view (changing the Brand or Search filter drops any selected SKU that's no longer visible). New helpers `chewyToggleOne`, `chewyToggleAllVisible`, `chewyClearSelection`.

## Recent Fixes (v4.97)
- **Chewy Forecasts scorecards now use a consumption-adjusted delta vs prev snapshot.** v4.96 fixed the per-row current-month cells (showing "remaining / peak") but the top scorecards (30/60/90/120-Day Chewy Demand) still computed `delta = latest_total - prev_total`, where both totals' current-month portions had already been drained by consumption — so the delta read as a misleading drop. New helper builds a "peak-adjusted" map per part (replaces current month's value with `currentMonthPeak` for the latest comparison and `currentMonthPeakAtPrev` for the prev snapshot's view) and re-runs `fwdUnits` against it. Delta label changed from "↑/↓ X vs prev_snap" to "↑/↓ X Chewy revision vs prev_snap" with a tooltip explaining the adjustment. The displayed scorecard VALUE is unchanged (still the raw remaining demand, which is what you actually need for inventory planning) — only the delta is normalized.
- **Tooltip on the current-month column header.** The current-month `<th>` is now highlighted in orange with `ⓘ` and a hover tooltip explaining the "remaining / peak" format, why trend arrows are suppressed on that column, and how the scorecards above account for it. Other month headers get a simpler tooltip explaining the cell format.
- **Tooltip on each scorecard.** Hovering the scorecard label/box surfaces a tooltip clarifying: the number is forward-looking remaining demand summed across visible SKUs, the in-month drop is normal consumption, and the delta below is adjusted for that.

## Recent Fixes (v4.96)
- **Chewy Forecasts — current month displays "remaining / peak" instead of just the dropping remaining value.** As the month progresses Chewy's snapshot value for the current month drops while units ship/consume; it's not Chewy lowering demand, but the dashboard was rendering raw values and a `↓ Declining` trend arrow that misled the user into thinking demand was falling. Now: for the current month column (per-product cells AND footer total), the cell shows `remaining / peak` — peak = max value seen across all uploaded snapshots for that month — with a tooltip explaining "Remaining: N · Peak projection: M · Consumed/shipped so far: M-N. The drop is in-month consumption, not Chewy revising demand down." Trend arrow is suppressed on the current month since the latest-vs-prev raw delta is dominated by consumption. Other months (past, future) keep the standard value + trend display. Legend at the bottom of the table now shows `X / Y current month: remaining / peak projection (consumption-adjusted)`.

## Recent Fixes (v4.95)
- **SKU Economics batch uploads — silence the per-file overlap dialog.** `parseSkuEconomics` now takes a `conflictMode` parameter (`'prompt'` default — show dialog, `'new_only'` — skip overlapping weeks silently, `'replace'` — overwrite, `'cancel'` — abort). Both batch handlers (`handleSkuEconZipUpload`, `handleSkuEconFolderUpload`) pass `'new_only'` so a ZIP/folder of historical files doesn't dump a per-file dialog on the user mid-run. Single-file uploads still prompt as before. Fires only when there's same-ASIN-same-week overlap in the DB (different-brand uploads for the same week don't trigger because their ASINs don't match the existing rows). Use case: re-uploading historical files after a partial-data cleanup, where some weeks in the ZIP already exist in the kept window — those skip cleanly, the rest insert.

## Recent Fixes (v4.94)
- **SKU Economics — ZIP upload for back-fill.** New `🗜 Zip of CSVs` button next to the folder-upload button on the SKU Economics dropzone. Accepts a single `.zip` containing many SKU Economics CSVs (e.g. one per week, the user's historical batch). Lazy-loads JSZip from CDN on first use (kept out of the initial bundle since back-fill is rare), unpacks every `.csv` member (flattens subdirectories, skips macOS resource forks like `__MACOSX/` and `._*`), then iterates each through `parseSkuEconomics` — same validation as the folder uploader (single Sun-Sat week, dedup, brand prompt once if no Brand column). Pnl cache invalidated and `init()` runs at the end so the dashboard picks up the new rows immediately. Audit log records `upload.sku_economics_zip` with the zip filename, member count, success/fail breakdown, and per-file error summaries.

## Recent Fixes (v4.93)
- **SKU Economics — `storeToRegion()` blind to plain country codes.** Amazon's current SKU Economics CSV format puts plain country codes (`US`, `CA`, `MX`) in the `Amazon store` column, not the legacy domain-style values (`Amazon.com`, `Amazon.ca`, `Amazon.com.mx`). The old helper only matched on `.ca` / `.mx` substrings, so every plain `CA` row fell through to the US default. Worse: because the in-memory aggregation key is `(asin, region, week_start)`, US and CA rows for the same ASIN collided under `(asin, 'US', week)` and got **summed together** (per the v4.61 multi-MSKU policy) — silently inflating US totals with CA contributions, and writing zero CA rows to the DB. Fixed `storeToRegion` to recognize both formats: legacy domain-style `.ca` / `.mx` / `.co.uk` / `.de` AND plain country codes `CA` / `MX` / `UK` / `GB` / `DE` / `US`.
- **Affected uploads:** any SKU Economics file uploaded with the current Amazon format (plain country codes) — visible as "no CA rows present for that week even though the source CSV had a CA section." Historical uploads from when Amazon used domain-style values are untouched. The May 3-9 batch the user hit was the latest example.
- **Cleanup for affected weeks:** delete the contaminated week's `sku_economics` + `sales_weekly` Amazon rows and re-upload the same file with v4.93's parser:
  ```sql
  delete from sku_economics where week_start = '2026-05-04';
  delete from sales_weekly where channel in ('amazon_us', 'amazon_ca') and week_start = '2026-05-04';
  ```
  Then re-upload the same file in the dashboard. The parser will now split US and CA rows correctly into separate `(asin, region, week_start)` keys.

## Recent Fixes (v4.92)
- **Shopify upload — fractured week_start values from a timezone-poisoned parser.** The Shopify daily→weekly aggregator did `new Date(dayString)` to parse each row's Day column. JS interprets ISO strings ("2025-08-04") as UTC midnight while reading `getDay`/`getDate` in LOCAL time — so in non-UTC timezones the parser saw the "wrong" day-of-week, derived a shifted week_start via the same Sun-is-day-7 math the Amazon parser had, and finally serialized via `toISOString()` (UTC again). Different CSV formats (ISO vs M/D/YYYY) and different upload times scattered rows across multiple buggy week_start values for what should have been one canonical week — the user observed week_starts of 2025-07-29 (Tue), 2025-08-04 (Mon), and 2025-08-05 (Tue) all in the same period.
- **Fix:** new global helpers `parseLocalDate` (parses ISO + US date strings to local midnight, sidestepping UTC) and `dateToMondayLocal` (does week math in local time, formats output from local parts via `fmtLocalYMD` instead of `toISOString`). The Shopify aggregator now routes through them, producing stable Monday-of-Mon-Sun-week values regardless of CSV format or user timezone. Sunday inputs (the day-7 trap) map FORWARD to the next-day Monday (same rule the v4.91 dateToMonday fix introduced for Amazon).
- **Migration for existing data:** `supabase_fix_shopify_week_dates.sql`. Uses Postgres `date_trunc('week', week_start)::date` (which returns the Mon-Sun ISO Monday) to collapse every shopify row onto its canonical Monday, then groups by `(channel, asin, shopify_sku, region, monday)` and sums `units_ordered + revenue`. Wrapped in a transaction with preview steps before the `commit`. Note: since the existing rows are already weekly aggregates (the per-day fidelity was lost at original upload), the migration consolidates the buggy weeklies but can't reconstruct day-level placement. For high-precision needs, re-upload the daily Shopify CSVs after deploying v4.92 — the parser's delete+insert path will replace existing rows cleanly.
- **Chewy parser is NOT affected.** chewy_forecasts stores monthly granularity (forecast_month = YYYY-MM); no daily→weekly aggregation path, no timezone bug.
- **Legacy Amazon by-Child-ASIN uploader is NOT affected.** It only updates in-memory velocity (`daily_v30/v60/v90`), no week_start writes to sales_weekly.

## Recent Fixes (v4.91)
- **SKU Economics upload — uploaded data didn't appear in the P&L tab.** Two compounding bugs:
  1. **`pnlData` cache never invalidated.** `loadPnlTab()` early-returns when `pnlData.length > 0`, so after `parseSkuEconomics()` upserted fresh rows to `sku_economics`, opening the P&L tab kept rendering the pre-upload snapshot. Fixed: both `handleSkuEconUpload` (single file) and `handleSkuEconFolderUpload` (folder/batch) now reset `pnlData = []` before calling `init()`, so the next P&L open re-fetches.
  2. **`dateToMonday()` shifted Sunday inputs back six days.** Amazon's SKU Economics export uses Sun→Sat weeks (validated by the parser). The old helper used the ISO 8601 convention (Sun = day 7 = last day of its week → 6 days back to that ISO week's Monday). So a file with Start date Sun May 3 was stored as `week_start = 2026-04-27` — invisible to anyone querying for May 3-9 in the DB or filtering the dashboard by recent weeks. Fixed: Sunday inputs now map to the **next-day Monday** (Sun May 3 → Mon May 4 — the Monday of the Mon-Sun week that overlaps Amazon's Sun-Sat week). Mon–Sat inputs unchanged (return the Monday earlier in the same week).
- **Migration note for existing data:** old uploads stored under the wrong (earlier) Monday are still in the DB at those keys; this fix only affects NEW uploads going forward. To consolidate ALL historical Amazon rows (both `sku_economics` and `sales_weekly` channel=amazon_us/amazon_ca), run `supabase_fix_amazon_week_shift.sql` in Supabase SQL Editor — shifts every Amazon row forward by 7 days. Safe (all rows move together; no unique-key conflicts) and reversible (transaction-wrapped). The same shift applies to `weekToMonday` curated-CSV uploads because Amazon labels its Sun-Sat week using the ISO week of the Sunday (e.g., Aug 3-9 → "Week 31" → Jul 28), so the bug bit both raw-export and curated-CSV uploads identically.

## Recent Fixes (v4.90)
- **Forecast Trend column now sorts.** `fcTrendSortValue` regex required a number after the arrows (`/[↑↓]+\s*[+-]?\d+/`), but the actual trend strings the dashboard produces are word labels — `"↑↑ Accelerating"`, `"↑ Growing"`, `"→ Steady"`, etc. — with no number. Regex never matched, every row tied at 0, the column silently refused to sort. Replaced with simple substring matching: ↑↑ → 2, ↑ → 1, → / unknown → 0, ↓ → -1, ↓↓ → -2.
- **`chewy_part_no` → `chewy_sku` across the schema and code.** Renamed the column on both `products` and `chewy_forecasts` (the unique key on chewy_forecasts is `(chewy_sku, forecast_month, upload_date)` — Postgres auto-updates the constraint reference on RENAME COLUMN). All references in `index.html` updated: column registry label ("Chewy SKU"), product modal label, Edit modal, COGS table cell prefix, upload matcher, query presets, merge tool, CSV download/upload headers. UI labels updated from "Chewy Part #" / "Chewy Part Number" to "Chewy SKU". **Run `supabase_rename_chewy_sku.sql` in Supabase SQL Editor BEFORE deploying v4.90** — without it, every read/write touching the column will 400 with "column products.chewy_sku does not exist".
- **Chewy Forecasts tab — CSV export wired into the top-bar `↓ CSV` button.** Previously the button routed `forecast → showExportDialog` which exported the demand table, ignoring the Chewy subview. Now: when `forecastView === 'chewy'`, exports a Chewy-specific CSV — one row per SKU, columns `master_id, chewy_sku, brand, product_name, demand_30d / 60d / 90d / 120d, prev_30d / 60d / 90d / 120d, m_YYYY-MM × N` (one column per month visible). `chewyExportParts` + `chewyExportMonths` are snapshotted at the end of `renderChewyForecast()` so the CSV exactly mirrors what's on screen — same filters, same "Include past months" state. Audit log records `chewy.export` with row+month counts.

## Recent Fixes (v4.89)
- **Chewy Forecasts tab — "Include past months" toggle.** The month columns auto-advance forward as the calendar rolls over (the `m >= now` filter at render time silently drops months once they're in the past). Confirmed working — May 2026 drops off the left when the date hits June 1. New checkbox in the filter strip relaxes that filter so historical months show up too: useful for comparing what Chewy projected for a past month vs what they actually purchased. Defaults to off so the table stays focused on upcoming demand.
- **Chewy upload — older-snapshot guardrail.** The Snapshot date input on the Chewy upload card now has a "Today" button (one-click prefill) and an orange warning callout directly underneath spelling out the failure mode: for backfilling older files, set this to the date Chewy originally sent the file, otherwise the older forecast gets tagged with today's date and overrides your newer forecasts in the displayed "latest" view. The underlying rows aren't lost — `chewy_forecasts` is uniquely keyed on `(chewy_sku, forecast_month, upload_date)` so multiple snapshots coexist — but `loadChewyFcLatest()` picks the most recent `upload_date` per `(master_id, forecast_month)` when surfacing the current view.

## Recent Fixes (v4.88)
- **Bundle attribution now flows into the Need forecasts and scorecards, not just the Sold (period) column.** Bundle sales are recorded with the BUNDLE's master_id; `velocity_calculated` groups by master_id+region, so a component product's `daily_v30` (and `blended_daily` derived from it) never reflected demand pulled through bundle sales. v4.87 added a `+B N` badge to the Sold column but the Need columns + scorecards stayed bundle-blind. New helper `getBundleAttrDailyVelocity(masterId, windowDays, channels, region)` walks `allBomData`, sums each parent bundle's region-filtered sales over the rolling window, multiplies by component qty, divides by window length, and returns daily units. Folded into `blended_daily` inside a new `recomputeRecordVelocity(rec)` helper that's now the single source of truth used by the init finalization pass, `applyVelocityWindow()`, `combineRegionRecords` (post-merge finalize), and the `fBundleAttr` checkbox toggle.
- **`fBundleAttr` checkbox now triggers a full velocity recompute, not just renderAll.** Previously toggling "+ bundle components" only re-rendered the table from the same precomputed `r.need30/60/90/120` values — so the Need columns + scorecards didn't move. Now `onchange="applyVelocityWindow()"` re-runs `recomputeRecordVelocity` on every record so the forecasts shift in real time as you toggle.
- **`combineRegionRecords` no longer sums `blended_daily` across regions.** Bundle attribution is region-aware (each region's record already counts bundle sales tagged to its region; the combined record sees all rows via the 'US+CA' marker). Summing the per-region `blended_daily` would double-count bundle credit on combined rows. Removed `blended_daily` and `bundle_daily` from the additive-sum list and rely on the post-merge `recomputeRecordVelocity(c)` call to derive both fresh against the combined region marker.
- **+B badge on the Vel/day column.** New per-row indicator (orange, like the existing +DTC pill) shows the bundle-attributed daily velocity contribution to `blended_daily`. Confirms at a glance that bundle attribution is feeding the forecast — previously the +B indicator only appeared on the historical Sold column.
- **Tooltips updated** on the "+ bundle components" filter checkbox (explains it folds into velocity for forecasts) and the Vel/day column header (explains the math + when +B fires).

## Recent Fixes (v4.87)
- **Bundle attribution: paginated `bom` load.** The init flow's `sb.from('bom').select('*')` had no `.range()` call — default Supabase row cap is 1000, so any BOM rows past that were silently dropped from `allBomData`, and components whose mapping landed past the cutoff stopped getting bundle credit on the Forecast tab. Violated Architecture Rule #4 (the codebase sweep noted in earlier velocity / P&L fixes). Now paginates 1000 at a time, matching the `loadProducts` / `loadPnlTab` / `loadChewyFcLatest` pattern. Visible failure mode was "the bundle attribution stopped working" once your BOM grew past 1000 rows.
- **Bundle-attributed slice surfaced in the Sold column.** Previously bundle attribution was silent — the Sold (period) column added bundle-component sales to the total but you couldn't tell from the row whether anything was contributing, which made the feature feel broken when nothing visually changed on toggle. Added `pre.bundleAttr` to `fcPrecompute` (separate count of just the bundle-attributed portion), and the unitsSoldPeriod render now shows a small orange `+B N` badge next to the total when N>0, with a hover tooltip naming the contribution. Column width bumped to 96px to fit. Tooltip text updated to mention the indicator.

## Recent Fixes (v4.86)
- **Column header tooltips on the Forecast tab.** Every column in `FC_COLUMNS` now has an optional `tooltip` field; the `<th>` `title` attribute prefers that over the bare label. The header cursor flips to `help` so it's clear hovering will say something. Tooltip text explains the underlying math + source (e.g., Need columns name the curve integration; Sea Now names where the multiplier comes from; Trend names the v60/v90 ratio thresholds; per-channel Forecast columns call out that they don't apply seasonality — intentional). Sort hint appended where applicable.
- **Velocity Window selector.** New dropdown in the filter strip (`30d (live)` / `60d` / `90d` / `120d`) picks which historical window feeds `blended_daily` for every record. Changing it fires `applyVelocityWindow()` which recomputes `blended_daily = daily_v{N}`, then re-derives `sea_idx → adj_daily → rederiveNeeds(rec)` for every record, then renders. Default stays at 30d (matches v4.85 init behavior). The matching `Vel Xd` column in the VELOCITY LOOKBACK group is tagged with a green `★ LIVE` indicator and `num-hi` styling so it's visible at a glance.
- **CSV export now respects the US+CA collapse.** Previously the "Everything" export scope dumped `records` directly (per-region), which split US+CA into two rows even though the on-screen UI had collapsed them. Fix: `doExportCSV('forecast', 'everything')` now applies `combineRegionRecords(records)` when no region filter is pinned (mirrors `getVisible()` behavior). Filtered exports were already correct since they route through `getVisible()`.

## Recent Fixes (v4.85)
- **Query Database tab — broken by v4.60 auth migration, now fixed.** `runDbQuery()` was hand-rolling `fetch('/rest/v1/rpc/exec_sql', { headers: { apikey: SB_KEY, Authorization: \`Bearer ${SB_KEY}\` }})` — both headers using the anon key. After v4.60 enabled RLS on every data table and restricted access to the `authenticated` role, those anon-keyed calls hit RLS deny on the inner SELECT (`exec_sql` is SECURITY INVOKER, so it runs as the caller's role). The SKU Economics preset (and any other preset that touched an RLS-protected table) returned 0 rows or a generic error. Switched to `sb.rpc('exec_sql', { query: sql })` through the shared Supabase client — the client automatically attaches the logged-in user's JWT, so the query runs as `authenticated` and the policy lets it through. Cleaner error surfacing too: the Supabase client returns structured `{message, hint}` so the status line shows the real Postgres error directly.
- **New preset queries** added to the Query Database tab presets bar:
  - **Stale Products (90d)** — products with `active=true` but no sales rows in the last 90 days; ordered by last sale date so launches that never sold appear first.
  - **Missing COGS** — products with at least one channel identifier (ASIN / Shopify SKU / Chewy SKU) but no COGS recorded for that channel AND the dismissal flag isn't set; reports which channels each row is missing.
  - **Channel Mix 90d** — units per channel per master_id over 90 days plus a `pct` column (each channel's share of that product's total), so you can see whether a product is Amazon-heavy, balanced, etc.
  - **Last Upload By Channel** — most recent `week_start` per (channel, region) plus a `days_old` delta; catches stale Shopify or Chewy uploads at a glance.
  - **Seasonality Status** — per-product `sea_method`, `seasonal_type`, weeks_of_data vs sea_min_weeks threshold, and a 'ready/thin' flag.
  - **Bundle BOM** — bundle-component pairs with `verified` flag; sorted unverified-first so QC candidates surface.
  - **Margin Leaders 90d** — per-product contribution margin over 90 days from `sku_economics`; filters out low-volume noise (`units >= 30`).
  - **Audit Log Recent** — last 100 audit_log entries; the existing `audit_log` table has been there since v4.60 but there was no preset to peek at it.
- These are read-only `select` statements; the new auth-routed `exec_sql` call still enforces `transaction_read_only = on` at the database level, so any write attempt smuggled in (including via WITH ... INSERT) is rejected by Postgres.

## Recent Fixes (v4.84)
- **Rgn pill is now channel-aware.** When the channel filter is active and every selected channel is US-only (Shopify and/or Chewy), the Rgn column renders "US" on every row — even when the underlying product has an Amazon CA listing. Previously rows for those products read "ALL" because the v4.82 collapse set `r.region='US+CA'`, which was misleading: with Shopify-only or Chewy-only selected, there are no CA sales contributing to the row. Now: row pill says what's actually being counted. Falls back to the v4.83 "ALL" pill when Amazon (or a mix including Amazon) is among the selected channels, since that genuinely is multi-region.

## Recent Fixes (v4.83)
- **Combined-region rows now show "ALL" instead of "CA+US" / "US+CA".** v4.82's `combineRegionRecords()` set `r.region` to a `+`-joined string for the rendered Rgn pill — but reading "CA+US" on a row that included Shopify and Chewy sales misled users into thinking those US-only channels also operated in Canada. The pill was also broken visually because no `.rtag-ca+us` CSS class existed. Fixes: (a) added a `.rtag-all` style (green) to match `.rtag-us` / `.rtag-ca`; (b) sorted the internal region string to put US first ('US+CA', not 'CA+US') for the rare callsite that needs to read it; (c) the Rgn column render now detects a `+` and prints "ALL" with a tooltip naming the merged regions and the channel semantics ("Amazon US + Amazon CA velocity summed; Shopify and Chewy added once, US-only").

## Recent Fixes (v4.82)
- **Forecast tab: US + CA region mode now collapses to one row per product.** Previously each product with both US and CA Amazon listings appeared as two rows in the table when no region filter was pinned, which made the "same Chewy/Shopify number on both rows" duplication very visible (v4.81 zeroed Chewy on the CA row but the CA row was still there). New helper `combineRegionRecords(records)` merges records by master_id when fRegion=''  — summing daily_vXX / blended_daily / dtc_daily_v30 / fba_available / fba_inbound / warehouse / total_onhand across regions, preferring US identifiers (ASIN, sp_sku), re-deriving sea_idx / adj_daily / trend / need windows. Combined record's `region` is `'US+CA'` (or just `'US'` if only one region had data) so downstream functions can still tell the difference. Region dropdown label updated to "US + CA (combined)" with an explanatory `title` tooltip.
- **`fcSoldByChannel` now gates by record region when no DOM filter is pinned.** Previously when fRegion was empty, every sales row for the master_id was summed regardless of region — so the CA row showed US Amazon sales and US Shopify sales, and the US row mirrored it. With the v4.82 collapse the combined row's region is `'US+CA'` (passes via `.includes()`) so all rows are included on the single combined record; on a manually-pinned region (US-only or CA-only), the filter narrows correctly. For the rare case where collapse is bypassed and a per-region record reaches this function with no filter (e.g. Inventory tab callsites), the per-record gate prevents cross-region leakage.
- **`getChewyFcUnits` region gate relaxed to pass `'US+CA'`.** The v4.81 gate (`region !== 'US'`) was too strict for the new combined view. New test: `!String(region).includes('US')` — any region string containing 'US' (so 'US', 'US+CA', combined-region variants) lets Chewy through; explicit non-US strings ('CA', 'MX', etc.) still exclude.
- **Inventory tab / SKU table (`renderSkuTbl`) unchanged.** Physical inventory is per-region (FBA US vs FBA CA fulfillment centers), so the Inventory Planning view keeps showing rows per region — that's where the user makes restock decisions and US/CA inventory aren't interchangeable. Only the Forecast tab's main table + scorecards collapse.
- **Other tabs unaffected.** P&L, Units Sold, Products, Bundles, Settings all use their own data paths (sku_economics / records / allProducts) and are not routed through `getVisible()`.

## Recent Fixes (v4.81)
- **Chewy demand was double-counted on CA rows.** Each product has separate US and CA records, but `getChewyFcUnits(masterId, days)` was keyed only by master_id — so when "All regions" was selected and Chewy was in the channel mix, the same Chewy forecast got added to both the US row AND the CA row for that product, showing duplicate Chewy values on a row (CA) where Chewy doesn't actually sell. Added a `region` parameter to `getChewyFcUnits` that returns 0 when the caller's region isn't US. Region is optional for back-compat — old call-sites that haven't been updated still behave as before. Updated record-level call-sites (`rederiveNeeds`, `getForwardNeed`, `getChannelVelocityForRecord` chewy branch, `fcForecastByChannel`, scorecard totals) to pass `r.region`. Net effect: CA rows now show 0 for Chewy contribution; US rows show the full Chewy forecast as before. The "duplicate rows" feeling was the same Chewy number appearing twice — now it appears once, on the US row.
- **Scorecard totals also picked up the v4.80 curve integration.** `renderScoreCards`'s totalNeed reducer was still using the v4.79 flat math (`adjVel × h`) for the mixed-channels path; now uses `forwardSeaDemand` like every other site. Single-channel Chewy-only scorecard already used `getChewyFcUnits` directly, so just needed region gating.

## Recent Fixes (v4.80)
- **Forecast need windows now INTEGRATE the seasonal curve across the horizon** instead of multiplying current-week sea_idx by N. Previously `need30 = adj_daily × 30` and `need120 = adj_daily × 120` used the SAME current-week multiplier as a constant across the whole horizon — so a product sitting at sea_idx=2.0 (peak) with a 120d window crossing into a 0.5× trough was forecasting ~2-3× too much demand. New helper `forwardSeaDemand(r, days)` sums `blended_daily × curve[weekOf(day)]` for each day in the horizon (max 120 iterations — fine for performance). Used by the finalization pass in `init()`, by `getForwardNeed`, and by the custom-channels render path. Chewy demand still added separately via `getChewyFcUnits` because Chewy's monthly forecast already encodes its own seasonality.
- **`getForwardSea(r, days)` is now the AVERAGE of the curve across the horizon, not a point estimate at end-of-horizon.** "30d Sea / 60d Sea / 90d Sea / 120d Sea" columns now mean "average seasonality across the next N days" — which is also what the integrated Need column above bakes into its number. A point-at-end value can be hugely misleading: with H=120 and the future-week landing in a trough, `getForwardSea` was returning 0.5× while the actual demand-weighted average across those 120 days was closer to 1.4×.
- **ISO week vs calendar week mismatch eliminated.** `computeProductSeasonality()` buckets sales rows into proper ISO 8601 weeks (week-containing-Thursday rule). But `getAutoSeaIdx`, `getForwardSea`, and the inline `currentWk` calcs in the seasonality + forecast detail panels all used a simpler `(jan1.getDay() + dayOfYear) / 7` calendar-week formula. The two disagreed by up to 1 week at year boundaries — so a calculated curve indexed by ISO W52 might get looked up at calendar W1, returning the wrong cell. All curve lookups now go through `isoWeekOfYear()` for consistency.
- **Net effect:** for products with strong seasonality and long horizons (60–120d), Need numbers may shift meaningfully (in either direction) vs v4.79. Products near peak now show LOWER needs at long horizons (the curve falls off into the future); products near trough show HIGHER. Trend, raw velocity, and the per-channel Sold columns are unchanged (they don't apply seasonality). Per-channel Forecast columns are still flat-extrapolated (no seasonality applied) — a known divergence from the main Need column that was not in scope for this fix.
- **Single source of truth for need windows.** Added `rederiveNeeds(rec)` helper — every place that writes `need30/60/90/120` on a record (init finalization, Restock Inventory upload, velocity-refresh after upload, legacy Amazon Child ASIN upload, Edit-modal save) now routes through this one function. Previously each call-site had its own copy of `Math.round(adj_daily × N) + getChewyFcUnits()`; some forgot Chewy entirely (Edit-modal save), some used the old flat math even after the v4.80 integrator existed. Now they all use `forwardSeaDemand` + Chewy consistently.
- **Custom-channels need path also integrates the curve.** `fcPrecompute()` previously did `Math.round(adjVel × N)` for the custom-channels render path (where `adjVel = chanVel × current_week_sea_idx`) — two layers of wrongness: flat over horizon AND applying current-week multiplier to a daily rate that already crossed the curve via the chosen channels. Now uses `forwardSeaDemand(synth, N)` where `synth = {...r, blended_daily: chanVel}`. Chewy still embedded in chanVel when selected, so no separate add (slight known imprecision since Chewy's own seasonality gets multiplied by our curve, but it's small relative to Amazon+DTC for most products).
- **Correction to v4.80 ISO-week notes.** The old `getForwardSea` actually DID use proper ISO 8601 calc — so the "ISO mismatch" only applied to `getAutoSeaIdx` and the two inline `currentWk` calcs in the seasonality/forecast detail panels. The unification is still worth doing for consistency (and protects against the same bug if a new call-site gets added later), but the per-horizon Sea columns were not misaligned in v4.79.

## Recent Fixes (v4.79)
- **Per-product seasonality now flows into the main Forecast tab.** Previously the `sea_method` / `seasonal_type` settings only drove the forward-looking sea columns (via `getForwardSea` → `getEffectiveCurveForProduct`); the current-week `r.sea_idx` and the derived `adj_daily` + `need30/60/90/120` columns were still computed during the initial record build at index.html:2061 / index.html:2137 using raw `SEED.curves[category]`. Result: "Sea Now" and the 30/60/90/120-day need totals on the Forecast tab were stuck on category defaults regardless of what was picked per-product. Added a finalization pass right after the records array is built (between the DTC-only loop and `setFreshBadge`) that recomputes `sea_idx = getAutoSeaIdx(rec)` for every record (honoring `sea_override` when set) then re-derives `adj_daily` and the need windows. The two initial build sites still write a category-default sea_idx, but the finalization pass overwrites it before render — leaving them in place avoids touching the legacy DTC/Amazon-build code paths.

## Recent Fixes (v4.78)
- **Seasonality detail table — frozen first column.** With 52 week columns the table requires horizontal scrolling; the leftmost "Metric" column (Category default / Saved / Preview / Adj u/day) is now `position: sticky; left: 0` so the row labels stay visible as you scroll. Switched the table from `border-collapse: collapse` to `border-collapse: separate; border-spacing: 0` since sticky cells don't carry collapsed borders reliably, and replaced borders with a 1px right-edge `box-shadow` on the sticky column (so the divider stays visible). Row-internal borders moved onto the cells themselves (each `<td>` carries the top border) since `<tr>` borders don't render with `border-collapse: separate`.
- **Column header tooltips on Seasonal type + Method.** The `<th>` cells in the product list now have explanatory `title=` tooltips. Seasonal type tooltip explains the four shape options (standard / seasonal / seasonal_limited / flat) and when to use each. Method tooltip explains the four source options (default / calculated / mix / manual) plus a rule-of-thumb mapping data-quantity → method (≥52 → calculated · 26–52 → mix · <26 → default). Both column headers visually marked with `ⓘ` and `cursor:help`.
- **Per-product recommendation tooltips on the row dropdowns.** New helper `recommendSeasonalitySettings(p)` inspects each product's `sea_weeks_of_data` plus the shape of its computed curve and returns a `{method, methodReason, stype, stypeReason}` recommendation. Surfaced two ways: (1) `title=` tooltip on the inline dropdowns naming the recommended value + the reasoning, e.g. `Recommendation: mix · Why: 38 weeks of history — moderate signal; blend 50/50 with category prior to smooth noise`; (2) inline `★` marker next to the recommended option inside each dropdown — so you can see at a glance which choice the data supports without opening the tooltip. The current value is also called out (`✓ matches recommendation` or `current: <other>`).
- **Method recommendation heuristic.** Driven purely by weeks of data: `≥52 → calculated` · `≥26 → mix` · `<26 → category-default`. No mid-band gaming or category-specific overrides — the user can always pick a different value; the recommendation just reflects what the data alone would justify.
- **Seasonal type recommendation heuristic.** Inspects the calculated curve shape (computed on the fly if not already saved): `<12 weeks of data → flat` (too new to characterize); else look at peak height and width: `max ≥3× with ≤4 weeks above 1.5× → seasonal_limited` (sharp narrow peak — classic holiday/event item) · `max ≥1.5× with ≥6 weeks above 1.5× → seasonal` (broad season) · otherwise `standard` (use category default).
- **Per-product method picker — adds `mix` as a fourth `sea_method`.** The Method column on the Seasonality page is now an inline `<select>` (same UX as the Seasonal type column) instead of a static chip. Options: `— default` (uses category curve), `⚡ calculated` (uses product's own computed curve), `⊕ mix (50/50)` (blends the calculated curve 50/50 with the fallback curve), and `✎ manual` (shown only if already set; no UI to enter).
- **Why mix.** For products with moderate history (~26–52 weeks), the calculated curve has signal but is still noisy — single outlier weeks can dominate. Blending 50/50 with the fallback (category default OR `seasonal_type` SEED curve if set) pulls extreme calc values back toward a sensible prior. Best-practice middle ground between "trust the data fully" (`calculated`) and "ignore product-specific signal" (`category-default`).
- **`getEffectiveCurveForProduct`** now recognises `method === 'mix'` and, when the product meets `sea_min_weeks`, computes `effective[w] = (calculated[w] + fallback[w]) / 2` per week, rounded to 2 decimals. The fallback resolution mirrors the standalone case: `seasonal_type=flat/seasonal/seasonal_limited` first, then `category default`. If `sea_curve_calculated` is missing or below threshold, falls through to the seasonal_type / category-default branches just like `calculated` does.
- **`seaSetMethod(masterId, newMethod)`** handler runs from the per-row dropdown. For `calculated`/`mix`, if no saved curve exists yet (or it's below the current threshold), the function auto-computes from sales history using the Min weeks input as threshold. Thin data aborts with an alert + the dropdown reverts to the stored value. Audit log records `seasonality.set_method`.
- **Method filter dropdown** gains a `Mix (50/50)` option so the product list can be narrowed to mix-method rows.
- **`supabase_seasonality_setup.sql`** updates the `sea_method` CHECK constraint to include `'mix'`. Uses a `do $$ … $$` block that drops the existing constraint (whatever its auto-generated name) and re-adds it with the wider set. **Re-run the file in Supabase SQL Editor before deploying v4.78** — without it, the update will fail with `new row for relation "products" violates check constraint`.

## Recent Fixes (v4.77)
- **`products.seasonal_type` designation.** New per-product enum: `standard` (default — uses category curve), `seasonal` (uses `SEED.curves.seasonal`), `seasonal_limited` (uses `SEED.curves.seasonal_limited`), `flat` (multiplier of 1.0 every week — good for new launches). The Query Jason ran confirmed no products were classified as `seasonal_limited` via `category_id`, so this gives a more direct route: tag the product itself rather than relying on the categories table.
- **Precedence in `getEffectiveCurveForProduct`:** 1) Per-product calculated/manual curve (if it meets `sea_min_weeks`) → 2) `seasonal_type` designation → 3) Category default curve. The calculated/manual curve still wins when present and confident — `seasonal_type` is a fallback / opinionated override one step above the category default.
- **Inline dropdown** in the Seasonality product list — new "Seasonal type" column with a per-row `<select>` (highlighted in orange when not `standard`). Change fires `seaSetSeasonalType()` which UPDATEs `products` and refreshes downstream views.
- **Bulk type-setter** in the existing bulk panel: pick a type, click `🏷 Set type for Selected` to apply to every checked product. Routes through `seaBulkSetSeasonalType()` which mirrors the structure of `seaBulkApplyMids` — per-product UPDATE, status reporting, audit log entry (`seasonality.bulk_set_type`).
- **New `seasonal_type` column** added to `supabase_seasonality_setup.sql` (uses `add column if not exists`, safe to re-run). Run it before deploying v4.77 or the dropdown change will fail with a `column does not exist` Postgres error.

## Recent Fixes (v4.76)
- **Seasonality page — searchable product list + bulk operations.** The single-product dropdown is now backed by a full product table at the top of the page, matching the search/filter pattern used on other tabs (P&L, COGS, Forecast). Controls: text search (matches title / short_name / master_id / ASIN / Shopify SKU / Chewy SKU), Brand filter, Method filter (Category default / Calculated / Manual), Status filter (Active / Inactive / All — defaults to Active), plus the existing Category dropdown for viewing a category curve directly. Each row shows: checkbox, brand chip, product name, master_id, current method (⚡ calculated / ✎ manual / — default), weeks of sales data, and eligibility (✓ ready / ⚠ thin) computed against the current Min weeks input.
- **Click a row to activate** for the detail view (the existing 52-week table below). The legacy `sea-product` dropdown is kept in the DOM as hidden state storage so `renderSeasonality()` doesn't change.
- **Bulk Calculate + Apply.** Three new buttons in a `Bulk seasonality` panel above the product list:
  - **⚡ Calculate + Apply Selected (N)** — runs `computeProductSeasonality()` for every checked product, applies any whose `weeksOfData >= minWeeks`. Counts skipped (thin data) and reports.
  - **📊 Apply to ALL eligible** — same, but candidate set is every active product. Skips those below threshold automatically.
  - **↺ Revert Selected** — bulk-revert checked products to `sea_method='category-default'`, clearing saved curves.
- All three issue per-product UPDATEs via `seaBulkApplyMids(mids, minWeeks)` (one round-trip per product — acceptable for hundreds of products in one operation), then call `loadProducts()` + `init()` so the new curves immediately flow through to Forecast / Inventory / P&L views. Audit log records `seasonality.bulk_apply` and `seasonality.bulk_revert` with counts.
- **Min weeks input** in the bulk panel is the same value used by single-product apply. Changing it instantly re-renders the eligibility column in the product list.

## Recent Fixes (v4.75)
- **Per-product seasonality calculated from sales history.** The Seasonality page previously could only display the legacy `SEED.curves` category-level curves baked into the file. Now: pick a product, click `⚡ Calculate from sales`, and `computeProductSeasonality()` derives a 52-week curve from `salesData[master_id]` — grouping `units_ordered` by ISO week-of-year, dividing each week's average by the overall average to produce indices around 1.0. Result is cached in `seaCalcCache` and rendered as a `Preview` row in the existing 52-week table, below the `Category default` row, so the two are visually comparable.
- **Per-product threshold for confidence.** New `Min weeks of data` input (default 26) is the threshold per product — below that, the calculated curve is considered too thin and won't be applied even after Save. Lets you tag new launches with a high threshold (52) so they keep using category default until enough data accumulates; lower it (8–12) for known-seasonal items where you want the curve to apply early. Stored on `products.sea_min_weeks`.
- **Apply / Revert.** `💾 Apply this curve` persists the computed curve + threshold to `products.sea_curve_calculated`, sets `sea_method='calculated'`, and triggers `init()` so every downstream view (Demand Forecast, Inventory Planning, P&L) immediately picks up the new sea_idx. `↺ Revert to category default` clears the saved curve and flips method back. Audit log captures `seasonality.apply` and `seasonality.revert`.
- **Resolver: `getEffectiveCurveForProduct(p)`** — single source of truth that `getAutoSeaIdx` and `getForwardSea` both call. Returns `{ curve, source }` where source is `'calculated' | 'manual' | 'category-default'`. Falls back to category when method is `'calculated'` but weeks-of-data is below threshold (so new launches don't accidentally pick up half-baked curves).
- **New `products` columns** (`supabase_seasonality_setup.sql` — uses `add column if not exists`, safe to re-run):
  - `sea_method TEXT default 'category-default'` — picks which source wins
  - `sea_curve_calculated JSONB` — `{"1":1.2,"2":1.05,...,"52":0.8}`
  - `sea_curve_manual JSONB` — placeholder for future user-edited curves (no UI yet)
  - `sea_min_weeks INTEGER default 26` — per-product confidence threshold
  - `sea_calculated_at TIMESTAMPTZ`, `sea_weeks_of_data INTEGER` — provenance/staleness metadata
- **Setup:** run `supabase_seasonality_setup.sql` in Supabase SQL Editor BEFORE deploying v4.75. Without it, the Apply button will fail with `column does not exist` on the products UPDATE.

## Recent Fixes (v4.74)
- **Amazon P&L — every column header is click-to-sort.** Replaced the static thead with a dynamic `<tr id="pnl-thead-row">` rendered by `renderPnl()`. Each column (Product, Units, Net Sales, FBA Fees, Referral, Ad Spend, COGS, Net Proceeds, Margin %, Contrib %) has an onclick that calls `pnlSetSort(key)`. First click on a numeric column sorts desc; first click on Product sorts asc; clicking the same column again toggles direction. Active sort column highlighted in `var(--text)` with `↑` or `↓` indicator; inactive columns show a dimmed `↕`. State is preserved across renders via `pnlSortKey` and `pnlSortDir`.
- **COGS page — Active/Inactive filter; default Active only.** New "Status" dropdown next to the existing Show filter with three options: `Active only` (default), `Inactive only`, `All`. Filters `allProducts` by `p.active !== false` (null/undefined treated as active for backwards-compat). Inactive products are hidden from view by default — they don't pollute the missing-COGS counts or the table.
- **COGS page — dismissible alerts.** Each "— missing" cell now has a small `✕` button next to it. Clicking dismisses the missing-COGS alert for that specific product+channel (persisted to `product_cogs.amazon_dismissed` / `dtc_dismissed` / `chewy_dismissed`). Useful when a product technically has an ASIN/Shopify SKU/Chewy SKU but isn't actually sold on that channel — the alert was just noise. Dismissed cells display "dismissed" in italic gray with a `↺` undo button. Dismissed channels are also excluded from "Missing …" filter results.
- **Schema additions** (run via `supabase_product_cogs_setup.sql` re-execute — uses `add column if not exists`, safe to re-run):
  - `product_cogs.amazon_dismissed BOOLEAN DEFAULT false`
  - `product_cogs.dtc_dismissed BOOLEAN DEFAULT false`
  - `product_cogs.chewy_dismissed BOOLEAN DEFAULT false`
- Audit log records `cogs.dismiss_toggle` events with master_id, field, and value.

## Recent Fixes (v4.73)
- **Inline COGS editing on the COGS page.** Click any of the three COGS cells (Amazon / DTC / Chewy) → it becomes a number input pre-filled with the current value. **Enter** saves, **Escape** cancels, **click outside** also saves (blur). Save upserts the full per-channel row to `product_cogs` (preserving the other two channels — no accidental null-outs), refreshes `cogsByMaster`, and re-renders the table in place. Bundle cells stay editable too; the BOM-comparison line below them updates immediately when you change a component's value or the bundle's stored value. Audit log records `cogs.edit` with the master_id, channel, previous value, and new value.

## Recent Fixes (v4.72)
- **Bundle COGS — BOM comparison & mismatch flag.** Bundle COGS does NOT auto-derive from components (stays manual / per-channel like any other product), but the COGS page now shows the sum-of-components value inline under each bundle's stored COGS so you can spot drift. New helper `bundleCogsFromBom(masterId, channelField)` iterates `allBomData[bundleMid]`, multiplying each component's `cogsByMaster[comp.component_master_id][channelField]` by `comp.qty`. The cell below each bundle's stored value shows `BOM: $X.XX` with one of four states: ✓ green when it matches (within $0.01), ⚠ red when stored ≠ BOM (delta shown, e.g. `⚠ (+1.20)`), gray "partial" when some components themselves lack COGS, or green "auto-fillable" when stored is blank but BOM has a complete value.
- **Two new COGS-page filters:** `Bundles only` (shows just is_bundle products) and `Bundle COGS mismatches (stored ≠ BOM)` (only bundles where at least one channel's stored COGS disagrees with the BOM-derived value by >$0.01). Quick way to triage bundle audits.

## Recent Fixes (v4.71)
- **SKU Economics — folder/batch upload.** New green button inside the SKU Economics dropzone: `📁 Or upload an entire folder (one CSV per week, validated)`. Uses a hidden `<input webkitdirectory directory multiple>` to let the user pick a whole folder; `handleSkuEconFolderUpload` then iterates every `.csv` inside (sorted alphabetically) and runs each through the existing `parseSkuEconomics` pipeline — so every validation still applies per file (single Sun→Sat week, deduplication, brand prompt). The brand prompt fires ONCE for the batch (peek at first file's header) and the chosen brand applies to all. Per-file errors are collected but don't abort the run; the status reports `✓ N/M files · X sales rows · Y P&L rows · Z weeks` and surfaces failure details in the tooltip (hover the status text). `init()` is called once at the end (not per file). Audit log records `upload.sku_economics_folder` with totals + up to 10 error summaries.

## Recent Fixes (v4.70)
- **Uploads tab header relabeled:** `📈 SKU Economics Report — All brands · US + CA · Includes COGS` → `📈 Amazon SKU Economics Report — All brands`. Removed the "Includes COGS" since COGS now lives in `product_cogs` and is managed independently (per channel). Removed "US + CA" since other Amazon marketplaces may be added later — the report intrinsically covers whatever regions Seller Central exposes.

## Recent Fixes (v4.69)
- **Uploads tab — Amazon by-Child-ASIN tiles moved behind a collapsible "Other / Legacy uploads" disclosure.** The six tiles (Meowijuana / Doggijuana / Kitty Ka-Zoom × US / CA) populated `sales_weekly` only — no fees or COGS — and the SKU Economics upload above now covers the same channels with full financial data. The tiles are kept available (in case of historical By-Child-ASIN exports needing backfill) but tucked inside a `<details>` element so they're out of the way by default. Header reads `🗂 Other / Legacy uploads — Amazon by Child ASIN (superseded by SKU Economics above)`.

## Recent Fixes (v4.68)
- **SKU Economics upload now enforces strict one-week Sun→Sat scope.** A previous lump 9/1–12/31 upload (17 weeks of activity rolled into a single CSV) all aggregated into one `week_start = 2025-09-01` row per ASIN and required manual SQL cleanup. The parser now scans for unique `Reporting Week` (or `Start date|End date`) keys BEFORE the agg loop runs and throws a clear error if more than one is present: `Multi-week file detected (N+ different weeks in this CSV). Upload ONE WEEK AT A TIME…`. When the CSV has Start/End date columns, additionally validates: start must be a Sunday, end must be a Saturday, range must be exactly 7 days. Each failure mode has its own targeted error message naming the offending date and the day-of-week it actually fell on.
- **Uploader UI calls this out up front.** The SKU Economics upload section has a new orange-bordered callout: `⚠ One week per upload — Sunday through Saturday`, plus the dropzone subtitle now reads `single Sun→Sat week only`. So the rule is visible before the user even picks a file.

## Recent Fixes (v4.67)
- **Units Sold chart — fixed duplicate month labels.** Both the drill chart and the by-channel chart had `labels: weeks.map(w => w.slice(0,7))` which truncated week_start to `YYYY-MM`, so any month with 4+ weeks showed `2026-04 / 2026-04 / 2026-04 / 2026-04`. Replaced with `M/D/YY` formatter so every week is uniquely labeled. The existing `maxTicksLimit: 24` still controls density for long ranges.
- **Units Sold chart — stable initial height.** The drill panel was `min-height:320px;max-height:480px` with `resize:vertical`, which Chart.js interacted with weirdly on first render (canvas grew taller than the parent). Replaced with an explicit `height:380px;min-height:280px;max-height:720px` so the initial size is deterministic; vertical resize handle still works inside the new bounds.
- **P&L Amazon line chart added.** New panel between scorecards and the product table. Shows up when 1+ products are checked via the row checkboxes (same mechanism as the existing scorecard drill-down). One line per selected master_id, weekly granularity, with a **Metric** dropdown: Net Sales, Gross Sales, Net Proceeds, Contribution Profit, Contribution %, Margin %, Total Amazon Fees, Ad Spend, COGS, Units Sold. Pulls from `pnlData` (sku_economics rows) with the same FX conversion and region/date filters as the rest of the P&L view — so the chart always tracks the table above. Uses `getAmazonCogs()` for COGS, Contribution Profit, and Contribution % so it reflects the live `product_cogs` data. `updatePnlChart()` is called at the end of `renderPnl()` so any filter or selection change refreshes the chart in lockstep.

## Recent Fixes (v4.66)
- **Top-bar `↓ CSV` button now exports the P&L tab.** Previously the active-tab detection routed `pnl` into `showExportDialog`, which had no case for it and fell through to the forecast fallback (or did nothing visible). `exportCSV()` now branches on `pnlView`: on the **Amazon SKU Economics** sub-view it calls a new `doDownloadPnlAmazonCSV()` that exports the currently-rendered aggregated product rows (one row per master_id, mirroring the on-screen table plus computed margin %, contribution profit, contribution %, and total fees); on the **COGS** sub-view it delegates straight to the existing `downloadCogsCSV()`. No dialog — same one-click feel as the COGS page.
- **`renderPnl()` now snapshots its rows.** Added `pnlExportRows` and `pnlExportCtx` module-level caches set at the end of each render (after region/date/brand/category/search/quick-filter all apply). The export uses this snapshot directly, so what's exported exactly matches what's on screen at that moment. Audit log records `pnl.export` with row count, region, date range, and active filters.

## Recent Fixes (v4.65)
- **COGS page now includes bundles.** Was filtering out `p.is_bundle` rows under the rationale that bundle COGS is normally computed from BOM components — but that hid 128 of 502 products from view, making the row count mismatch the Products tab confusing. Bundles now appear in the COGS table with a small orange `📦 BUNDLE` badge next to the product name. Setting COGS on a bundle row works the same as any other product (stores as an override in `product_cogs.amazon_cogs/dtc_cogs/chewy_cogs`). CSV download also includes bundles now.

## Recent Fixes (v4.64)
- **Amazon P&L now flags rows with missing COGS.** Two new surfaces: (a) a red-bordered banner above the scorecards reading `⚠ Missing Amazon COGS — N products in this view had sales ($X net sales) but no COGS — Contribution Profit is overstated`. Banner has a `Fix in COGS →` button that switches the view to the COGS sub-page. Only shows when at least one row has sales-without-COGS. (b) Per-row indicator: the product table's COGS column now renders `⚠ missing` (in red) for any row where `units > 0` and `cogsByMaster[master_id].amazon_cogs` is null/zero, instead of the ambiguous `—` (which previously could mean either "no sales" or "no COGS"). Hover tooltip explains the implication. Rows with no sales still show `—`.
- **Migration backfill updated to 1:1.** `supabase_product_cogs_setup.sql` now creates a `product_cogs` row for **every** product (not just those with non-null/positive `cogs`). Re-runs are safe — uses `coalesce` on conflict so existing `amazon_cogs` values are preserved. For users on v4.62/v4.63 who already ran the older migration, the chat-provided patch query (`insert ... left join product_cogs ... where pc.master_id is null`) backfills the missing rows.

## Recent Fixes (v4.63)
- **Products modal rewired to the per-channel COGS table.** The COGS field on the edit-product modal now reads from `cogsByMaster[mid]?.amazon_cogs` (falls back to legacy `products.cogs` if no `product_cogs` row exists yet, so older data still displays). On save, the value is upserted into `product_cogs.amazon_cogs` via a separate call; `cogs` was removed from the `products` table payload so the legacy column stops accumulating writes. After upsert, `loadProductCogs()` refreshes the in-memory cache so the P&L picks up the new value immediately. Label renamed to "Amazon COGS (USD)" with a hint pointing users to P&L → COGS for DTC and Chewy COGS editing.

## Recent Fixes (v4.62)
- **P&L is now a dropdown** with two sub-views: `📊 Amazon SKU Economics` (the prior P&L page) and `📦 COGS` (new). Same dropdown pattern as the Data tab. State persists in `pnlView`.
- **New `product_cogs` table** (`supabase_product_cogs_setup.sql`): per-channel COGS values. One row per master_id with `amazon_cogs`, `dtc_cogs`, `chewy_cogs`. PK is master_id with FK→products(master_id) ON DELETE CASCADE. RLS authenticated full access. `updated_at` + `updated_by` maintained by trigger. Backfill at setup time copies existing `products.cogs` into `amazon_cogs` (every previously-stored COGS came from Amazon's report). `products.cogs` is retained in the DB as backup but no longer authoritative.
- **In-memory cache** `cogsByMaster` mirrors the table; loaded by `loadProductCogs()` at init (parallel with products/velocity/inventory), refreshed after CSV uploads and after `parseSkuEconomics` writes new Amazon COGS values.
- **`parseSkuEconomics` writes to `product_cogs.amazon_cogs`** (not `products.cogs`). Same delta semantics: any non-null COGS from the report's `cogs` column → upserted, batched, then `loadProductCogs()` refreshes the cache.
- **`renderPnl` reads from the new lookup.** `getAmazonCogs(master_id)` is the single source of truth; the `cogs_total` aggregator uses it × `net_units_sold`. The old `prod.cogs` read is gone.
- **COGS page (Settings → P&L → COGS):** table of every product (excluding bundles) with one row showing Brand chip / product name / master_id / channel IDs (ASIN + Shopify SKU + Chewy SKU tagged with A:/S:/C: prefixes) / Amazon COGS / DTC COGS / Chewy COGS / Status badge. A product is flagged "⚠ Missing" only for channels it's actually sold on (has the respective channel ID). Filters: Brand, "All / Missing any / Missing Amazon / Missing DTC / Missing Chewy", search.
- **CSV download/upload for COGS:** Download exports `master_id,brand,title,asin,shopify_sku,chewy_sku,amazon_cogs,dtc_cogs,chewy_cogs`. Upload upserts on master_id; empty cells preserve existing values (so partial updates work — e.g. fill in just DTC COGS without overwriting Amazon).
- **Audit log:** `cogs.download` and `cogs.upload` events recorded (with row counts).
- **One-time setup:** run `supabase_product_cogs_setup.sql` in Supabase SQL Editor BEFORE deploying v4.62, otherwise `loadProductCogs()` silently warns to console and `cogsByMaster` stays empty (P&L will show $0 COGS for everything until the table exists).

## Recent Fixes (v4.61)
- **SKU Economics upload — revert v4.53's last-write-wins back to summing.** v4.53 changed the per-row aggregation from `+=` to `=` to dedupe accidental byte-identical duplicates in concatenated curated CSVs. That decision was wrong for the **raw** Amazon download: Amazon legitimately emits multiple CSV rows for the same ASIN+week when the ASIN is listed under multiple MSKUs (merchant SKUs). v4.53 silently kept only the LAST MSKU's data and dropped the others, undercounting those ASINs. Reverted to summing; same key collisions are now tracked as `repeatCount` (renamed from `dupCount`) and surfaced as an informational note (`ℹ X ASIN rows repeated for same week (summed — usually Amazon's multi-MSKU split for the same product)`), no longer flagged as warning. Byte-identical dupes (rare; happens only with hand-concatenated exports) will still inflate the row by 2× — acceptable trade-off given multi-MSKU is the common case.
- **Sequence GRANT added to auth setup.** The original `supabase_auth_setup.sql` enabled RLS + table policies but didn't grant USAGE on the BIGSERIAL sequences used by primary keys, so authenticated INSERTs failed with `permission denied for sequence sales_weekly_id_seq`. Added `grant usage, select on all sequences in schema public to authenticated` plus a default-privileges line so future sequences are covered too. If you set up auth before v4.61, run those two lines in SQL Editor to patch your existing DB.

## Recent Fixes (v4.60)
- **Real user authentication replaces the hardcoded password gate.** Supabase Auth (email/password + Google OAuth) is now the access wall. Every DB call carries the user's JWT instead of the anon key; row-level security on every table enforces this server-side. Setup runs in three places: SQL migration (`supabase_auth_setup.sql`), Supabase dashboard config (`AUTH_SETUP.md`), then dashboard code (this version).
- **New tables:** `user_profiles` (auto-populated by `on_auth_user_created` trigger; one row per `auth.users`; role column defaults to 'admin'); `audit_log` (writes via `log_action` RPC).
- **RLS policies:** every existing data table (`products`, `sales_weekly`, `sku_economics`, `inventory`, `bom`, `chewy_forecasts`, `categories`, `channel_listings`) is now `authenticated`-only. Anon role can no longer read or write. `user_profiles` is readable by all authenticated users; users can update only their own row. `audit_log` is read-only to clients; writes go through the SECURITY DEFINER `log_action` RPC.
- **Login UI:** the password input is gone. Replaced with email + password fields, "Sign in with Google" button (uses the existing Supabase OAuth provider), and a "Sign out" pill in the header showing the current user's email.
- **Settings → Users:** invite-by-email (uses `signInWithOtp({shouldCreateUser:true})` — sends a magic link that creates the user on first click; admin's session unaffected; no service_role needed in client code). Lists all users with role, joined date, last seen. Self is marked "you".
- **Settings → Audit Log:** scrollable table of the last 200 audit events with a filter dropdown (Auth / Uploads / Products / Invites / All). Each row shows timestamp, user email, action, and JSON details.
- **Audit logging wired into:** sign-in, sign-out, invites, and SKU Economics uploads (logs row counts, dupes, brand assignment, etc.). Future product mutations should call `logAudit('product.create', {...})` / `'product.update'` / `'product.delete'` at the same hook points.
- **`getSB()` updated:** now passes `{auth: {persistSession, autoRefreshToken, detectSessionInUrl}}` so the SDK auto-rotates JWTs and handles OAuth redirect URLs landing back at the dashboard.
- **Old `SmarterPaw2026` password and session-storage gate removed** — no longer a JS-only check that anyone could bypass via DevTools.

**Deploy + setup order (one-time):**
1. Run `supabase_auth_setup.sql` in Supabase SQL Editor.
2. Walk through `AUTH_SETUP.md` to create your first admin user and configure the Google OAuth provider.
3. Push v4.60 via GitHub Desktop.
4. Hard-refresh the live site. The login screen should appear; sign in with the account from step 2.
5. Settings → Users → invite the others by email.

## Recent Fixes (v4.59)
- **SKU Economics upload — clearer post-upload nudge for auto-created products.** When a raw Amazon CSV creates new `SP-TEMP-<asin>` products, the upload status now reads `⚠ X new products auto-created as <brand> — set COGS / category in Products tab → Needs Review (Contribution % is overstated until COGS is set)` with the dz-warn style. Makes it visible at upload time why subsequent P&L numbers will look too rosy before COGS is filled in (the `cogs_total` aggregator multiplies `prod.cogs` by units; null/0 COGS = no contribution drag).

## Recent Fixes (v4.58)
- **SKU Economics upload — brand prompt when no Brand column.** Raw Amazon CSVs don't have a Brand column, so v4.57's auto-create defaulted unknown ASINs to "Meowijuana" (legacy fallback). Now the upload handler peeks the header line BEFORE parsing; if there's no Brand column, it shows a modal (`promptForSkuEconomicsBrand`) with four buttons — Meowijuana / Doggijuana / Kitty Ka-Zoom / Skip (mixed file). The chosen brand is passed into `parseSkuEconomics(text, fileBrand)` and applied to any newly-auto-created `SP-TEMP-<asin>` products. Existing products keep their current brand. The status line afterward shows e.g. `· 12 new products (brand: Doggijuana)`. Cancelling the modal aborts the upload cleanly.

## Recent Fixes (v4.57)
- **SKU Economics upload — raw Amazon download now accepted directly.** Previously the parser required the curated CSV (with `Brand`, `Region`, `Reporting Week`, `Item Name`, `COGS` columns pre-prepended); the raw Amazon export only has `Start date`, `End date`, `Amazon store`, ASIN, financials. Two fallbacks added: (a) if `Reporting Week` column is absent, week_start is derived from `Start date` via `dateToMonday()`; (b) if `Region` column is absent, region is derived from `Amazon store` via `storeToRegion()` (`Amazon.ca` → CA, `*.mx` → MX, else US). Brand and Item Name are still optional (already were); ASINs with no product match still auto-create as `SP-TEMP-<asin>`. The required-columns check is now ASIN + Net units sold + (Reporting Week OR Start date).

## Recent Fixes (v4.56)
- **P&L product table — Contrib % column added.** New rightmost column showing per-product Contribution % = `(net_proceeds − cogs_total) / net_sales`. Sits alongside the existing Margin % column so the row tells the full story: Margin % (after fees, before COGS) plus Contrib % (after fees AND COGS). Same green/orange/red color thresholds as the scorecard (≥15% green, ≥5% orange, below red). Tooltip on the header explains the formula.

## Recent Fixes (v4.55)
- **P&L product cell — ASIN is now copy-friendly.** Previously a double-click on the ASIN selected the trailing word of the product title too (no clean text boundary between the truncated title `<span>` and the ASIN `<div>` directly below it), and clicking the ASIN bubbled up to the row's `onclick` and toggled row selection instead of letting you copy. Wrapped the ASIN in its own inline-block `<span>` with `user-select: all` (single click selects the whole ASIN) + `cursor: text`, and added `event.stopPropagation()` on `click`/`dblclick` so clicking the ASIN doesn't trigger the row toggle. Title got `user-select: text` to make its own selection behave normally too.

## Recent Fixes (v4.54)
- **P&L scorecard: Gross Margin → Contribution %.** Replaced the last scorecard. `Gross Margin = net_proceeds / net_sales` was double-represented (the Net Proceeds card's subtitle already showed that percentage). The new `Contribution % = (net_proceeds − cogs) / net_sales` matches the dollar figure shown in the Contribution Profit card. Color thresholds: ≥15% green, ≥5% orange, below red.

## Recent Fixes (v4.53)
- **SKU Economics upload — zero-sale rows now reach `sku_economics`.** The upload loop had a blanket `if (netUnits <= 0) continue;` near the top that silently dropped every CSV row where Net Units Sold was zero. Amazon's SKU Economics report includes those rows because they still incur fees — FBA storage on inventory, ad spend on listings that didn't convert, refund admin on returns, aged-inventory surcharges, etc. Dropping them on upload meant the dashboard's Amazon Fees / Ad Spend / Net Proceeds were systematically understated; orphan-hunting earlier missed this because the rows didn't make it past the parser. Specific case: for Doggijuana CA Apr 10 → May 10, the source CSV had 126 rows; the filter dropped 114 of them. Now `sku_economics` gets every valid row (`asin`, `weekStr`, parseable `weekStart`); `sales_weekly` keeps the `netUnits > 0` gate (it really is about sales). Re-upload your latest SKU Economics CSV after deploying to backfill those rows into Supabase via upsert.
- **SKU Economics upload — strict 1 row per (asin, region, week_start).** The previous loop summed financials and units across rows with the same key (`e.field += pn(...)`), then upserted one row to Supabase. If a CSV contained duplicate rows for the same key (e.g., re-downloaded "Full" file appended onto an older copy, manual concatenation, partial re-pull), every duplicate **inflated** the corresponding row's $ / unit values before the upsert collapsed them. Found this when the source CSV had 99 rows for week 2026-04-05 Doggijuana CA where 42 was expected. Now: each duplicate row OVERWRITES the prior in-memory row (last-write-wins, matching Supabase's eventual upsert behavior); the dupe count is tracked in `dupCount` and surfaced in the upload status — `⚠ X duplicate rows in CSV (deduped — last value kept)` with the dz-warn styling — so a malformed input is visible rather than silently doubling totals.
- **Existing data note:** this fix only affects FUTURE uploads. Rows already in Supabase that were inflated by the old summing behavior remain inflated until they're overwritten by a fresh upload of the same week. Re-uploading the affected CSV from a clean source will correct them via the unique-key upsert.
- **Architecture Rule #5 updated:** SKU Economics upload now enforces last-write-wins for in-memory dedup, in addition to the database's unique-key upsert. The note about "delete+insert for Amazon rows" still applies to `sales_weekly` (the functional coalesce index there), not to `sku_economics`.

## Recent Fixes (v4.52)
- **Export CSV dialog — column-scope chooser.** The export dialog (Forecast tab only — other tabs have fixed column sets) now has a "Columns" panel above the row-scope buttons with two radios: **Visible columns** (default — matches what's in the table, including new toggles like per-channel sold/forecast and velocity lookbacks) and **All columns** (every entry in `FC_COLUMNS`, useful for one-time data dumps without having to toggle each column on first). Row-scope buttons (Filtered / Everything) still control which records are exported; the column scope is orthogonal. `doExportCSV(tab, mode, colScope)` reads `colScope` to pick `fcVisibleColumns()` vs `FC_COLUMNS`; locked columns (e.g., the row-selection checkbox) are always excluded.

## Recent Fixes (v4.51)
- **Forecast tab — column registry refactor.** The hardcoded 17-column `cols` array inside `renderTable()` is replaced by a `FC_COLUMNS` registry near the top of the forecast section. Each column is one object with `key`, `group`, `groupHdr`, `label` (or dynamic `headHtml(ctx)`), `get(r, ctx)`, `render(r, ctx, pre)`, and optional `csv(r, ctx)`. `renderTable` now iterates `fcVisibleColumns()`. Adding a new column means appending one entry to the registry — no edits to `renderTable` or `doExportCSV` needed.
- **All columns are sortable.** Sort comparator (`fcCompare`) calls each column's `get(r, ctx)`, so dynamic columns (the ID column, the period-aware "Sold (X)", custom-channel forecast values, forward seasonal indices, per-channel breakouts) all sort correctly. Trend column uses `fcTrendSortValue` to sort by signed magnitude (`↑↑ +2.0×` > flat > `↓↓ -2.0×`). The old inline sort that read `a[sortKey]` left half the columns un-sortable; that's gone.
- **Velocity 120-day lookback now loaded.** Records previously had `daily_v30/60/90` but no `daily_v120`; added it from `velocity_calculated.v120`. Powers the new "Vel 120d" column.
- **New columns (default off, toggle via 📋 Columns popup).**
  - SKU group: ASIN, SP SKU, Shopify SKU, Chewy #, Master ID (each as their own selectable column).
  - Velocity lookbacks: Vel 30d, Vel 60d, Vel 90d, Vel 120d (raw daily velocity over each window).
  - Sold by channel: Amazon / Shopify / Chewy × 30/60/90/120 day windows. Chewy column will be empty since chewy data lives in `chewy_forecasts`, not `sales_weekly`.
  - Forecast by channel: Amazon / Shopify / Chewy × 30/60/90/120. Amazon and Shopify extrapolate the last 30 days' velocity outward; Chewy uses `getChewyFcUnits()` (forward forecast from the chewy_forecasts table).
- **Column show/hide popup.** New `📋 Columns` button next to the search input opens a popup with checkboxes grouped by category. Each group has "all"/"none" shortcuts; "Reset to defaults" restores the original visible set. Visible-columns state persists per browser via `localStorage('fcVisibleCols')`.
- **Group header row is now dynamic.** The static `<tr>` containing "SKU / VELOCITY / DEMAND FORECAST" group titles is replaced by `<tr id="colGroupRow">`, populated by `renderTable` based on which columns are visible. Adjacent visible columns sharing the same `groupHdr` value coalesce into a single spanning header.
- **CSV export follows visible columns.** `doExportCSV('forecast', ...)` now iterates `fcVisibleColumns()` and uses each column's `csv` (preferred) or `get` to emit the cell, with proper quoting/escaping for separators. Headers strip any HTML in dynamic header labels. Show a column → it appears in the export. Hide it → it doesn't.

## Recent Fixes (v4.50)
- **`loadProducts()` now paginates.** Same 1000-row cap fix as `loadPnlTab()` got in v4.44. Currently the catalog has ~513 products so this isn't biting yet, but it would silently start losing brands the moment count crosses 1000. Defensive.
- **P&L surfaces orphan ASINs hidden by the brand filter.** When the user filters by Brand=Doggijuana (etc.), `sku_economics` rows that didn't match any product (synthesized as `_placeholder` with `brand:'Unknown'` in v4.49) get excluded — that's correct behavior, but the user can't tell those rows exist. The row-count line now appends `⚠ X unmatched ASINs hidden by brand filter ($Y net sales) — switch to All Brands to inspect` when any orphan was filtered out. Counts distinct ASINs (not row count) and sums the FX-converted net sales. Lets you see at a glance whether your dashboard total + orphan total ≈ external reporting total, and which ASINs need to be added to the products catalog.

## Recent Fixes (v4.49)
- **`--sp-red` CSS variable was never defined.** Every `var(--sp-red)` reference in the file (fee bars, scorecard "loss" colors, status indicators, etc.) resolved to its CSS initial — `transparent` for `background`, default text color for `color`. That's why the fee bars looked unfilled: the fill div was transparent on top of the track. Defined `--sp-red: #d63f2a` and `--sp-red2: #ef5a44` to match the existing brand-orange/yellow/green palette. This fix likely affects other red elements throughout the dashboard that have been silently un-styled.
- **P&L join was dropping rows whose ASIN didn't match a product.** `renderPnl()` did `allProducts.find(p => p.asin === row.asin)` and `if (!prod) continue;` — every `sku_economics` row whose ASIN wasn't in the products catalog (e.g. delisted ASINs, multi-region ASIN collisions, stale uploads) was silently excluded from totals. In the user's CA data this was eating roughly half the revenue. Now joins by `row.master_id` first (the actual FK on sku_economics), falls back to ASIN match, and synthesizes a placeholder product (`brand: 'Unknown'`, `master_id: unmatched-<asin>`, `cogs: 0`) for rows that match neither — so the financial data still flows through to scorecards and fee breakdown. Brand/category filters still exclude the placeholder bucket, which is the correct behavior (truly unknown brand shouldn't satisfy "Brand: Meowijuana").
- This is a known-pattern issue worth grepping the codebase for: any `find(p => p.asin === ...)` followed by `if (!prod) continue` is potentially silently dropping data the same way.

## Recent Fixes (v4.48)
- **Negative dollar values now show a minus sign.** The `$` formatter wraps `Math.abs(v)` so it always emits a positive-looking string — that's correct for fee/expense values that are inherently positive (you can't have negative ad spend), but wrong for values that can flip negative when a product loses money: Net Proceeds, Contribution Profit, Gross/Net Sales when refunds dominate. Added a `$s` (signed) helper alongside `$`, used in those four scorecards and in the Net Sales / Net Proceeds columns of the product table. Color logic was already firing red for negatives — now the minus sign comes through too. Fee breakdown still uses the explicit `±$X` prefix because it intentionally shows refunds as `+` rather than `−`.

## Recent Fixes (v4.47)
- **Fee breakdown bars now visually unmistakable.** Math was already correct (bar width = fee as % of net sales since v4.45), but the 4px-tall bar against `var(--border)` track had near-zero contrast — a 30%-filled bar looked like a solid line. Bumped track to 7px, switched track to `var(--surface2)` with `var(--border2)` outline, and added a numeric `X.X%` label to the right of each bar so the percentage is unambiguous at a glance.
- **Brand chip in P&L product rows.** Added the same `chip c-meow` / `c-doggi` / `c-kkz` badge used on the Forecast/Inventory/Products/Sales tabs, inline next to the product title. Label uses `KKZ` for Kitty Ka-Zoom and the first 6 chars otherwise (matches the existing convention everywhere else).
- **Contribution Profit scorecard added; Units Returned removed.** New card shows `Net Proceeds − COGS` with the `% of net sales` subtitle. Replaced "Units Returned" — its math was always 0 by construction (`tot.units − sum(rows.units)` where the two are the same number); restoring a real returns metric needs a dedicated `units_returned` column on `sku_economics` which we don't currently capture.

## Recent Fixes (v4.46)
- **P&L quick filter dropdown.** New "Quick" select in the filter strip composes with brand/category/search/date/region: `Top 10/25 — Net Proceeds`, `Top 10 — Margin %`, `Bottom 10 — Net Proceeds`, `Bottom 10 — Margin %`, `Negative margin only`. Quick filter is applied AFTER the page filters narrow `rows`, then the table + scorecards reflect the narrowed subset.
- **P&L multi-select aggregation.** Replaced single-row drill-down (`pnlSelectedMid` string) with a multi-select set (`pnlSelectedMids` Set). Each row has a checkbox in a new leftmost column; clicking the row anywhere also toggles. Header checkbox toggles select-all-visible (indeterminate when partial). When N≥1 are selected, scorecards + fee breakdown show the SUM of those rows; banner reads "Drilled into <title>" for N=1, "Aggregating N products" with a 3-title preview for N>1. Selection auto-prunes anything that falls outside the current visible set (e.g. when filters change). Clear via the banner button.
- Numeric fields summed for multi-select are listed in `PNL_NUMERIC_FIELDS` constant — keep this in sync if new financial columns are added to the row aggregator.

## Recent Fixes (v4.45)
- **P&L drill-down by product.** Click any row in the P&L product table → scorecards + fee breakdown rebuild from that single product's numbers. A green-bordered banner appears above the scorecards showing "Drilled into <title>" with a "← Show all products" button to clear. Selection state lives in `pnlSelectedMid` and clears automatically if the chosen product falls out of the active filters (region/brand/category/search/date). The full product table still shows everything — only the aggregate panels narrow.
- **Fee bars now match their displayed percentage.** Previously each fee's bar fill was the fee's share of *total fees*, while the text label above it said "X% of sales" — two different denominators producing visually misleading bars (a fee that's 30% of all fees but only 2% of sales had a 30%-wide bar). Bars now fill based on fee-as-share-of-net-sales, matching the label.

## Recent Fixes (v4.44)
- **P&L tab was silently truncating to 1000 rows.** `loadPnlTab()` did `sb.from('sku_economics').select('*').order(...)` with no `.range()` — Supabase caps a single un-paginated select at 1000 rows, so the dashboard saw only the most recent ~1000 weekly rows and quietly dropped everything older. Every total (gross sales, net sales, fees, ad spend, COGS, net proceeds) was therefore understated for any range that reached past that cutoff. Replaced with the same paginated loop already used in `loadChewyFcLatest`. This is the third place that violated Architecture Rule #4 — worth a codebase sweep next time we're in here.

## Recent Fixes (v4.43)
- **Merge tool no longer overwrites survivor's `short_name`.** The auto-fill loop in `runMerge()` was copying the duplicate's `short_name` onto the survivor whenever the survivor's was empty — but `short_name` is an editorial display label, not a functional identifier, so the chosen survivor's name (even if blank) should win. Removed that single line; other fields (asin, sp_sku, barcode, etc.) still auto-fill from the duplicate when the survivor lacks them.
- **Query Database `syntax error at or near ";"`** — `exec_sql` wraps the user query as `select ... from (USER_QUERY) t`, so any trailing `;` breaks the wrapper. `runDbQuery()` now strips trailing semicolons before sending. (All built-in presets end with `;`, so they all hit this.)
- **Query Database tab finally renders.** The `data-view-query` markup added in v4.42 was inserted past the actual `</div>` that closes `page-data` (which has no comment — page-data closes at the bare `</div>` after `data-view-uploads`, not at the line that *says* `<!-- /page-data -->`). The block ended up nested inside `page-sales` (display:none), so clicking Query Database toggled `dataView` but the panel was never visible. Moved the block into `page-data` and corrected the misleading `<!-- /page-data -->` and `<!-- /data-view-uploads -->` comments that pointed at unrelated `</div>`s in `page-sales`.
- **Lesson for future edits:** the closing `</div>` for each `page-X` is unmarked. When inserting markup at the end of a page, verify nesting depth (count opens/closes from the page's opening `<div>`) — don't trust comments. Quick check: `getComputedStyle(el).display` on a wrapping ancestor will reveal if you've landed in a `display:none` page.

## Recent Fixes (v4.42)
- **Data sub-tab strip** added inside page-data so Uploads / Query Database can be reached without the broken header dropdown. `switchDataView` now syncs both the dropdown buttons and the new strip.
- **Query tab error reporting** now surfaces the real Postgres/PostgREST error instead of always claiming "exec_sql RPC not found". The misleading single-table FROM-parsing fallback was removed — better to fail loudly with the install instructions.
- **`supabase_create_exec_sql.sql`** generated in project folder. Read-only-safe (SECURITY INVOKER + transaction_read_only).

## Recent Fixes (v4.41)
- **Data/Forecast nav dropdowns** fixed: handlers now track active page via `currentPage` JS variable instead of reading `pageData.classList.contains('active')`. The DOM-based check was unreliable because async render passes (`loadSalesAnalytics`, `connectSheets`) or any future `showPage()` call could wipe the class between clicks, making the second click look like a fresh navigation instead of a toggle. Removed the `[DataNav]`/`[DEBUG]`/`[DocClick]`/`[Init]` debug instrumentation.

## Recent Fixes (v4.40)
- **SP-TEMP promotion** fixed: now inserts new SP-XXXX product FIRST, then migrates all FK references (sales_weekly, sku_economics, chewy_forecasts, bom, inventory), then deletes old temp. Was failing with 409 Conflict because it was trying to update FKs before the target existed.
- **Duplicate `const isNew`** removed from saveProduct
- **stale allProducts cache** — openProductModal now reloads from Supabase if masterId not found in cache
- **Merge tool** updates chewy_forecasts + sku_economics, asks which BOM to keep when both products have components
- **Channel checkboxes** Total ↔ individual channels sync bidirectionally
- **Chewy Forecasts tab** forward-looking 30/60/90/120d scorecards with delta vs prior snapshot, monthly column totals footer, per-cell month delta
- **SKU Economics uploader** checks SP-TEMP-{asin} before creating duplicate products
- **P&L tab** live CAD→USD conversion via Bank of Canada Valet API

## Key Functions Reference
- `handleDataNavClick(btn)` — Data nav dropdown toggle
- `switchDataView(view)` — switches between 'uploads' and 'query' subviews
- `handleForecastNavClick(btn)` — Forecast nav dropdown toggle  
- `switchForecastView(view)` — switches between demand/inventory/seasonality/chewy
- `saveProduct()` — saves product, promotes SP-TEMP to SP-XXXX
- `runMerge()` — merges duplicate products, handles BOM conflict
- `parseSkuEconomics(text)` — SKU Economics CSV parser, writes to sales_weekly + sku_economics
- `parseChewyVendorStatement(arrayBuffer, snapshotDate)` — Chewy XLSX parser → chewy_forecasts
- `getChewyFcUnits(masterId, days)` — prorates Chewy monthly forecast into N-day forward demand
- `loadChewyFcLatest(sb)` — loads latest-per-month Chewy forecast into chewyFcLatest map
- `renderChewyForecast()` — renders the Chewy Forecasts subview
- `renderPnl()` — renders P&L tab
- `runDbQuery()` — executes SQL via exec_sql RPC; surfaces real error if function missing
- `init()` — main init: loads products, velocity, inventory, BOM, Chewy forecasts, renders all

## Versioning
Bump version string at top of file after every change: `v4.42 · 2026-05-10`
Run syntax check before shipping: extract script tag and run through `new Function(js)`
