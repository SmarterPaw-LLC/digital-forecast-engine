# Chewy Break-Even ROAS: verification for Blake (2026-10-27)

**Blake asked:** verify the BE cost on Chewy for Kitty Ka-Zoom. He sees 600%+ BE ROAS, some 900%+, and concludes the products are "not advertisable in almost any instances, either not workable, or has an error."

**Answer: the numbers are not an error. They are correct. And the conclusion is right for today's performance, though the root cause is wholesale margin, not ad cost.**

---

## 1. Was there an error? No. Three independent checks.

### a) COGS basis is correct on all 16 KKZ SKUs

The model picks COGS from `chewy_cogs` first, falling back to `landed_cost`, then `dtc_cogs`, then `amazon_cogs`. The two later fallbacks are wrong for Chewy: `dtc_cogs` carries DTC shipping and pick/pack, `amazon_cogs` carries the FBA fulfilment fee, and neither applies to a 1P pallet going to a Chewy DC. A SKU on either would read a worse margin and therefore a **higher** BE ROAS than reality.

**All 16 KKZ SKUs resolve to `chewy_cogs`.** Zero are on a wrong-basis fallback. No COGS inflation.

### b) The 26.50% standing allowance cross-checks against the invoices

| Line | Rate | Invoiced | Implied base |
|---|---|---|---|
| MDF / Coop | 16.0% | $35,552.58 | $222,204 |
| Auto Ship | 5.0% | $6,210.11 | $124,202 |
| Damages | 2.0% | $6,859.11 | $342,956 |
| Satisfaction Guarantee | 2.0% | $4,444.06 | $222,203 |
| Freight | 1.5% | $3,333.05 | $222,203 |
| **Standing total** | **26.50%** | | |

MDF/Coop, Satisfaction and Freight all imply the **same** invoice base ($222,203). Three independent lines agreeing on the base is strong evidence the rate model is right. Damages spans more invoices, hence a larger base. Auto Ship is charged only on autoship revenue, which is the smaller base, as expected.

### c) No double-count between the allowance stack and ad spend

"Chewy Onsite Ads" appears on the rebate invoices ($33,569 across brands, $10,156 of it KKZ). That is the **same money** as the per-SKU ad spend in the Promoted Products report. The model correctly assigns that category a 0% rate so it is counted once, per SKU, not twice.

---

## 2. Why 600%+ is normal on Chewy 1P, not a red flag

```
BE ROAS = Chewy retail price  /  our contribution per unit
```

The numerator is Chewy's **retail** revenue (what Chewy's customer paid Chewy). The denominator is our **wholesale** margin. Those are two different sides of the transaction. Chewy retail runs about **2.1x our wholesale price**, consistently across all three brands.

So: **BE ROAS is roughly 2.1 divided by gross margin % on wholesale.**

| Brand | GM % on wholesale | Spend-weighted BE ROAS |
|---|---|---|
| Meowijuana | 50% | 431% |
| Kitty Ka-Zoom | 42% | 485% |
| Doggijuana | 42% | 529% |

A 600% BE ROAS is what a 35% wholesale margin looks like. A 975% BE ROAS is what a 21% wholesale margin looks like. Read through an Amazon 3P lens, where both sides of the ratio are retail-basis, those figures look alarming. On 1P they are arithmetic.

---

## 3. Is KKZ advertisable? Mostly not today. Blake is right.

Realized vs break-even, all-time (2025-05-07 to 2026-10-25, $13,589 KKZ spend):

| Product | Whsl/ea | COGS | Contrib/u | GM% | BE ROAS | Realized | Headroom |
|---|---|---|---|---|---|---|---|
| Super Zoomies Mix 3.67 oz | $5.79 | $1.39 | $2.87 | 49% | 335% | **491%** | **+156** |
| Zoomie Spider Teaser | $3.91 | $1.23 | $1.64 | 42% | 414% | 66% | -349 |
| Zoomie Sea Turtle | $3.91 | $1.30 | $1.57 | 40% | 508% | 153% | -354 |
| Silvervine Fruit Sticks | $3.22 | $1.06 | $1.31 | 41% | 533% | 316% | -217 |
| Grain-Free Chicken | $2.39 | $0.85 | $0.91 | 38% | 539% | 118% | -421 |
| Crunchy Seafood | $2.39 | $0.85 | $0.91 | 38% | 540% | 173% | -368 |
| Zoomie Jelly Fish | $3.22 | $1.15 | $1.22 | 38% | 575% | 301% | -273 |
| Zoomie Shark | $3.22 | $1.15 | $1.22 | 38% | 576% | 381% | -195 |
| Zoomie Crab | $3.22 | $1.19 | $1.18 | 37% | 594% | 227% | -367 |
| Liquid Catnip Spray 4 oz | $3.22 | $1.23 | $1.14 | 35% | 615% | 465% | -150 |
| Craze Catnip 2 oz | $2.43 | $0.98 | $0.81 | 33% | 619% | 382% | -237 |
| Silvervine Surge 2 oz | $2.43 | $0.98 | $0.81 | 33% | 774% | 327% | -447 |
| Valerian Root Roar 2 oz | $2.43 | $0.98 | $0.81 | 33% | 774% | 151% | -623 |
| Zoomie Snake Kicker | $3.22 | $1.49 | $0.88 | 27% | 797% | 231% | -566 |
| Bubbles w/ Built-In Wand | $2.89 | $1.51 | $0.61 | 21% | 975% | 339% | -636 |
| Liquid Catnip Spray 1 oz | $2.43 | $1.00 | $0.79 | 32% | n/a | 107% | n/a |

Realized ROAS includes direct sales plus **incremental** autoship (recurring orders only). First autoship orders are already inside Direct, so counting the gross autoship figure would double-count them.

### Dollars at stake

| Brand | Ad spend | Contribution earned | Net | ROI |
|---|---|---|---|---|
| Meowijuana | $33,419 | $34,931 | **+$1,512** | 105% |
| Kitty Ka-Zoom | $13,589 | $12,094 | **-$1,495** | 89% |
| Doggijuana | $2,568 | $1,371 | **-$1,197** | 53% |
| **Total** | **$49,576** | **$48,396** | **-$1,180** | **98%** |

Within KKZ: **Super Zoomies earned +$2,223. The other 15 SKUs lost $3,718 combined.**

**Worth flagging that Blake did not raise: Doggijuana is worse than KKZ.** 53% ROI, and 156% direct ROAS over the last 90 days against a 529% break-even.

---

## 4. Root cause: wholesale margin, not ad efficiency

KKZ's ad efficiency is not the problem. Over the last 90 days KKZ ran **400% direct ROAS** against Meowijuana's 463%. Close. The gap is on the margin side: KKZ carries 42% GM on wholesale against Meowijuana's 50%.

For KKZ to clear break-even at its current 386% realized ROAS, GM on wholesale would need to be about **53%**. At current COGS that means roughly a 25% wholesale price increase, a 30% COGS reduction, or a blend.

Bubbles is the clearest case: $2.89 wholesale against $1.51 COGS is **21% GM**, the thinnest in the line, and it is what produces the 975% break-even. There is only $0.61 per unit to pay for everything.

---

## 5. The one thing that could change the conclusion: autoship LTV

KKZ ads drove **714 autoship signups at $19.03 cost per signup** (11.9% of 5,980 ad-driven units). Those customers reorder. The break-even model prices the first order plus recurring orders **already observed in the window**. It does not price future reorders.

So a SKU at 400% against a 500% break-even is not automatically unprofitable in LTV terms. Whether 12% autoship conversion covers a 100-point first-purchase gap depends on an autoship retention / LTV figure we do not currently hold in the dashboard. **That is the number to get before cutting the SKUs that sit close to break-even.**

---

## 6. Recommended sequence

1. **Zero the 7 deep-negative, low-volume SKUs.** Spider Teaser (90% ROAS last 90d), Snake Kicker (88%), Valerian Root (128%), Crunchy Seafood (140%), Grain-Free Chicken (166%), Sea Turtle (196%), Crab (215%). Together those are $652 of last-90-day spend producing 157 units. Low cost to stop, real dollars recovered. Per-SKU samples here are small (4 to 104 units each over 90 days), so treat the ranking as directional; the direction is consistent with the 18-month history.
2. **Hold Super Zoomies and fund it.** 487% ROAS last 90 days against a 335% break-even. It is already 52% of KKZ's last-90-day spend and it carries the brand's ad P&L.
3. **Fix the wholesale price or COGS on the four near-miss SKUs** before deciding on them: Liquid Spray 4 oz (-150), Shark (-195), Silvervine Fruit (-217), Craze (-237). A modest margin improvement flips these rather than losing the placements.
4. **Separately, look at Bubbles' cost structure.** 21% GM on wholesale is not an advertising problem.
5. **Get an autoship LTV figure from Chewy** so items 1 and 3 can be judged on full customer value rather than first-purchase contribution alone.
6. **Run the same read on Doggijuana.** It is the weakest of the three and has not been flagged.

---

## 7. Known modelling caveats (both small, roughly offsetting)

- **Auto Ship 5% is applied to every unit** in the model, but the invoices show it is charged only on autoship revenue (implied base $124,202 against $222,203 for the sitewide lines). Applying it universally slightly overstates the allowance. Effective standing rate on that basis is nearer 24.3%, which would make every BE ROAS about 8% **better**.
- **FTAS trade allowances are not in the model at all.** $5,500.04 invoiced across 25 lines, because the rate lives in the rebate name ("Treats 35% FTAS") rather than the rate field, so it parses as null. That is about 2.5 points on the same base, pushing BE ROAS **worse**.

Net effect is close to a wash. **26.50% is the right working number.**

---

## Sources

- `chewy_catalog.cost` + `purchase_uom` + `products.case_qty` for wholesale per each
- `product_cogs.chewy_cogs` (landed + Chewy fulfilment + labour) for COGS
- `chewy_rebates` for the allowance stack: 68 invoices, 2026-04-08 to 2026-10-07
- `chewy_ad_spend` for spend and realized performance: 20,570 rows, 2025-05-07 to 2026-10-25
- Per-SKU detail for all 144 Chewy SKUs: `chewy_be_audit.csv`
- Reproduce with: `python chewy_be_audit.py`
