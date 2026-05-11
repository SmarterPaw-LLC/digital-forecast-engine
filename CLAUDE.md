# SmarterPaw Forecast Dashboard — Claude Code Handoff

## Project Overview
Single-file HTML dashboard for SmarterPaw LLC (brands: Meowijuana, Doggijuana, Kitty Ka-Zoom).
File: `index.html` (in this repo; was `SmarterPaw_Forecast_v4.html` in the old loose folder) — current version **v4.60**

## Supabase
- URL: `https://yjcnuyoaemlipvuinptp.supabase.co`
- Anon key: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlqY251eW9hZW1saXB2dWlucHRwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNTY4NjcsImV4cCI6MjA5MzgzMjg2N30.CACwOGjnC370ZPjKlXG4dDpU9bVwCP4JDBD451WvwaM`
- Dashboard password: `SmarterPaw2026`

## Database Tables
- **products** — PK: `master_id` (SP-XXXX real, SP-TEMP-{ASIN} temporary). Fields: master_id, sp_sku, shopify_sku, chewy_part_no, asin, brand, title, short_name, is_bundle, category_id, barcode, msrp, wholesale, cogs, supplier, active, notes
- **sales_weekly** — (master_id, channel, asin, shopify_sku, week_start). Channels: amazon_us, amazon_ca, shopify, chewy. Unique index: `(channel, asin, coalesce(shopify_sku,''), week_start)`
- **velocity_calculated** — VIEW grouping by master_id+region, returns v30/v60/v90/v120
- **inventory** — asin, region, master_id, fba_available, fba_inbound, warehouse, lead_time_days, safety_stock
- **bom** — bundle_master_id, component_master_id, qty, verified
- **sku_economics** — full P&L per (asin, region, week_start). Unique: (asin, region, week_start)
- **chewy_forecasts** — (chewy_part_no, master_id, forecast_month YYYY-MM, forecast_units, upload_date). Unique: (chewy_part_no, forecast_month, upload_date)
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
5. **SKU Economics upload uses delete+insert** (not upsert) for Amazon rows due to functional coalesce index
6. **Chewy data → chewy_forecasts table only** (not sales_weekly). Velocity uses getChewyFcUnits() forward forecast
7. **Foreign key order matters**: when promoting SP-TEMP → SP-XXXX, insert new product FIRST, then update references, then delete old temp

## Active Issues to Fix

### 1. Install `exec_sql` in Supabase (one-time)
File `supabase_create_exec_sql.sql` lives in the project folder. Open Supabase → SQL Editor → New query → paste the file → Run. Uses `SECURITY INVOKER` + `SET LOCAL transaction_read_only = on` so writes are rejected by the database itself, not just by a string check. Once installed, the Query Database subview runs arbitrary SELECT/WITH queries via `/rest/v1/rpc/exec_sql`. If not installed, the dashboard now surfaces a clear error pointing to this file.

### 2. Header dropdowns invisible (workaround in place)
The Data + Forecast header dropdowns set `display:block` on click but the panel doesn't paint visibly — likely a stacking-context interaction with the sticky header's `backdrop-filter: blur(18px)`. Workaround in v4.42: visible sub-tab strip inside `page-data` (📥 Uploads | 🔍 Query Database) so the dropdown isn't required for navigation. Forecast tab still relies on the dropdown — needs a similar fallback or a real CSS fix.

### 3. Query tab presets to add (once Query tab is reachable)
Suggested presets to write: low inventory alert, velocity leaders (top 50 by v30), stale products (no sales 90d), channel mix per master_id, unverified bundles, products missing identifiers, last-upload timestamps per channel.

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
