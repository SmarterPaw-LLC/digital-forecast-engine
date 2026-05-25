-- ============================================================================
-- FBM cleanup — revert ASINs that have BOTH active FBA + FBM listings to FBA
-- Run AFTER v4196_fulfillment_amazon_on_products.sql + v4196b_flip_meowi_fbm.sql.
-- ============================================================================
-- Rule:
--   • Has an active FBA listing on Amazon  → product is FBA (FBA wins)
--   • Only an active FBM listing            → product stays FBM
--
-- Source: Seller Central listings pulled 2026-05-25 (FBA + FBM lists).
--
-- v4196b set 99 ASINs to FBM. Of those, 68 also have an active FBA listing
-- (the seller has both an FBA SKU like "US643" and an FBM SKU like
-- "US643-FBM"). For those 68, FBA wins. The remaining 31 stay FBM.
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- Step 1: FBA wins. Set fulfillment_amazon = 'FBA' for every ASIN with an
-- active FBA listing. This is the source of truth — even if there's also an
-- FBM listing, we count Amazon consumption as FBA.
-- ────────────────────────────────────────────────────────────────────────────
update products set fulfillment_amazon = 'FBA' where asin in (
  -- 69 active FBA Meowijuana ASINs from Seller Central 2026-05-25
  'B0GXM5FTQS','B0GXLWDHL8','B0GXLYYVBT','B0GXLTHJ2R','B0GXLQD7DQ',
  'B0GXMK2H6T','B00UDP42NS','B0G3D17RJ1','B0G3D2DLJW','B0FVG6YHGW',
  'B0FR9SSDB3','B0FR9V5YN6','B0FR9GYG6K','B0FR8XSWS2','B0FR9GXP8K',
  'B0FR9S9G21','B0FR9C8PX5','B0FR9KBCMW','B0FN8FMTZ3','B0FH7LWFBR',
  'B0FGLJHD3N','B0FGLNL5L6','B0FGLJ4MR2','B0FGKNPX45','B0FGL9Q5W2',
  'B0FGKQY7SM','B0FGKK9FFG','B0FGLQ32YD','B0FFTS34FF','B0F69Y3YKP',
  'B0F6B4BXJR','B0DYKD1S8V','B0DQF8R5XL','B0DNNHG3CM','B0DNLVN8JY',
  'B0DNLGFDBJ','B00U869UMK','B00U86E6Z6','B00U6EGXGK','B0DL1LCWQ3',
  'B0DKVHHPDZ','B0DKVHP6MS','B0DKVNCGJ6','B0DKVFG2RF','B0D9ZLLH9C',
  'B0D9PMWYGM','B0D9PN38GG','B0844RR5FH','B017ME6VMW','B0C1T81NMW',
  'B0C1QYBG5Y','B0C1QV5B9P','B0C1QKDPRM','B0C1QWRDT8','B0BV3DYBR3',
  'B0BSMQF7C5','B0BSMBZN6Y','B0BSMP5RL3','B0BSM9K4CH','B0BL5P83QD',
  'B0BL5MM9V5','B00U6DJCR8','B08ZGZDYFG','B08ZHDPPNH','B08ZGL2CNL',
  'B08W24837G','B081ZDBFXP','B07WGHX6M3','B07KPRTSMT'
);

-- ────────────────────────────────────────────────────────────────────────────
-- Step 2: True FBM-only. These 31 ASINs are FBM-only — no active FBA listing
-- for them. (v4196b already flipped these to FBM; this is idempotent — safe
-- to re-run, and serves as a check.)
-- ────────────────────────────────────────────────────────────────────────────
update products set fulfillment_amazon = 'FBM' where asin in (
  'B0FVGCFNVQ',  -- Get Waddled Bundle (Penguin) — MTCM025-FBM
  'B0FVG7WJFK',  -- Knock n Nibble Winter Buddy & Seafood — MTCM023-FBM
  'B0FRTSWB9J',  -- Knock N Nibble Pumpkin — CF292-FBM
  'B0FR9M6H7P',  -- Knock N Nibble Pumpkin & Chicken — MTCM038-FBM
  'B0FR9CD1CG',  -- Sprinkle n Scratch Rainbow Trout — MTCM007-FBM
  'B0FRN7CMR6',  -- Fall Favorites Bundle — MTCM016-FBM
  'B0FRN7PVFJ',  -- Get Spooked Bundle (Scarecrow/Pumpkin/PSL) — MTCM035-FBM
  'B0FRNCSD5T',  -- Get Spooked Scarecrow + Harvest Moon — MTCM034-FBM
  'B0FRNB8QDX',  -- Get Spooked Pumpkin + Harvest Moon — MTCM032-FBM
  'B0FRN7KHHB',  -- Get Spooked PSL + Harvest Moon — MTCM033-FBM
  'B0FRNB2VVV',  -- Get Spooked Scarecrow — CF231-FBM
  'B0FRNBPRG1',  -- Get Spooked Pumpkin — CF232-FBM
  'B0FRN7J7SF',  -- Get Spooked PSL — CF230-FBM
  'B0108I6PZC',  -- 1oz Premium Catnip Spray — 859442005964-FBM
  'B08ZHSFPT4',  -- Sleepy Time Bundle — 714929801241-FBM (out of stock)
  'B0BSMC7RWX',  -- Get a Rise Bundle — Rise Bundle-FBM
  'B0C1T8JFHL',  -- Rainbow Bundle — Rainbow Bundle=FBM
  'B0C1T4VQWV',  -- Blue Blob Bundle — Blue Blob Bundle-FBM
  'B0C1T82JL4',  -- Pepper Bundle — Pepper Bundle-FBM
  'B0BL5KYLQR',  -- Furry and Bright — FurryBright-FBM
  'B0CLPFTC7K',  -- Santa's Secret Stash (candy cane) — 859442005896-FBM (OOS)
  'B0D9PMWC7K',  -- Knock N Nibble Starfish & Seafood — CB061-FBM
  'B0D9PMPR6J',  -- Knock N Nibble Avocado & Chicken — CB060-FBM
  'B0D9MYHP1P',  -- Get Kickin Gummy Worm — 14-3C08-N3V9-FBM
  'B0D9PMWQ44',  -- Get Silly Furry Friend — CF272-FBM
  'B0D9PNDC1Q',  -- Get Hungry Burger & Fries — CF269-FBM
  'B0DNLQ49TS',  -- Catnip Cigar Toy — CF201-FBM
  'B00UDP417A',  -- Crunchie Munchie Chicken — CU-108I-GBHG-FBM
  'B0D9ZHY9TF',  -- Crunchie Munchie Seafood Medley — 6R-817F-JXI4-FBM
  'B01MEEJAML',  -- King Size Catnip Joints — 714929799968-FBM
  'B0DL72SKBS'   -- Sprinkle n Scratch Rainbow Trout — CF475-FBM (OOS)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Verify final state — expect 31 FBM, rest FBA.
-- ────────────────────────────────────────────────────────────────────────────
-- select fulfillment_amazon, count(*) from products group by 1;

-- List the final 31 FBM-only products with their titles for a sanity check:
-- select asin, master_id, fulfillment_amazon, sp_sku
-- from products
-- where fulfillment_amazon = 'FBM'
-- order by asin;
