-- ============================================================================
-- Add `image_url` column to products (v5.21)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.21.
-- ============================================================================
-- Holds the URL of the product's primary image. Populated by the Catsy
-- importer (from the "Main Image" column of the MasterItems export) and
-- editable manually via the Product modal. Displayed as a thumbnail on
-- the Products table + the Product edit modal.
--
-- TEXT type, nullable, no validation — Amazon S3 / Catsy CDN / Shopify
-- CDN / direct URLs all valid. Length unconstrained.
-- ============================================================================

alter table products add column if not exists image_url text;

-- Verify
--   select count(*) filter (where image_url is not null and image_url <> '') as with_image,
--          count(*) as total
--   from products;
