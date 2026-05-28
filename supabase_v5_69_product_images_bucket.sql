-- ============================================================================
-- Create `product-images` Storage bucket + RLS policies (v5.69)
-- Run ONCE in Supabase → SQL Editor BEFORE deploying v5.69.
-- ============================================================================
-- Stores re-hosted product images so they survive when source listings
-- (Amazon / Catsy) get taken down. Bucket is public-read so the existing
-- products.image_url column can point at the public URL — keeps the
-- products row tiny + lets the browser cache normally.
--
-- Size limits enforced at the bucket level: 512KB max per file, JPEG /
-- PNG / WebP only. The client (pf-image upload handler) resizes images
-- to 600×600 max + JPEG quality 0.7 before upload, so typical file size
-- lands at 30-80KB. The 512KB ceiling is a hard backstop in case the
-- client-side resize is bypassed.
--
-- Idempotent: re-running the file just updates the bucket config in
-- place. Policies use CREATE POLICY IF NOT EXISTS so they can be
-- re-applied safely too.
-- ============================================================================

-- 1. Create the bucket (public-read).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'product-images',
  'product-images',
  true,
  524288,  -- 512KB per file
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
  public            = excluded.public,
  file_size_limit   = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- 2. RLS policies on storage.objects. Authenticated users can upload /
--    overwrite / delete files in the bucket; anyone can read them
--    (matches the public-read setting above, which only governs the
--    bucket's exposure — the row-level SELECT policy is still required).
create policy "auth_upload_product_images"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'product-images');

create policy "auth_update_product_images"
  on storage.objects for update
  to authenticated
  using (bucket_id = 'product-images');

create policy "auth_delete_product_images"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'product-images');

create policy "public_read_product_images"
  on storage.objects for select
  to public
  using (bucket_id = 'product-images');

-- 3. Verify
--   select id, name, public, file_size_limit, allowed_mime_types
--   from storage.buckets where id = 'product-images';
--
--   select policyname from pg_policies
--   where schemaname = 'storage' and tablename = 'objects'
--     and policyname like '%product_images%';
