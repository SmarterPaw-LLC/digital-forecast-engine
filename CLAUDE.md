# SmarterPaw Forecast Dashboard — Claude Code Handoff

## Project Overview
Single-file HTML dashboard for SmarterPaw LLC (brands: Meowijuana, Doggijuana, Kitty Ka-Zoom).
File: `index.html` (in this repo; was `SmarterPaw_Forecast_v4.html` in the old loose folder) — current version **v5.30**

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

## Setup notes — Supabase RLS + table GRANTs

**Gotcha learned 2026-05-10:** RLS policies are LAYERED on top of Postgres role grants. The `authenticated` role needs explicit `GRANT SELECT/INSERT/UPDATE/DELETE` on the table — without it, PostgREST returns 403 BEFORE RLS gets a chance to evaluate. The first auth setup migration only granted sequences, not tables, so any new table created post-setup (like `product_cogs`) would 403 on read until grants were added. Both `supabase_auth_setup.sql` (5b) and `supabase_product_cogs_setup.sql` now include `grant ... on all tables in schema public to authenticated` + `alter default privileges`. If a NEW table is ever added after this, also run a one-line grant for that table.

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
