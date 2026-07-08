-- ============================================================================
-- Chewy Rebates (v7.03)
-- Run ONCE in Supabase → SQL Editor.
-- ============================================================================
-- Stores rebate/chargeback line items from Chewy's AP Invoice PDFs.
-- Chewy sends monthly PDFs to the Vendor Partner Portal. Two shapes exist:
--   A. Single-line lumpsum (promo, ad spend, trade allowance).
--      Example: REB00162368 — HG EverGreen B3G1 $1,181.42.
--   B. Multi-line allowances (Damages / Freight / MDF-Coop / Satisfaction),
--      each with a Rebate % Rate + Transaction Type (usually PURCHASE).
--      Example: REB00175503 — 4 lines summing to $11,030.07.
--
-- One row per REBATE LINE (not per invoice) so invoices with 4 line items
-- produce 4 rows. Unique key (invoice_number, line_number) prevents dupes
-- on re-upload; the parser detects existing rows and skips (via a summary
-- alert asking the user whether to overwrite).
--
-- Brand + category are derived at parse time by pattern-matching against
-- rebate_name + agreement_name. Kept as columns (rather than joined at query
-- time) because rebate names change more often than we'd want to re-derive.
-- ============================================================================

create table if not exists chewy_rebates (
  id                        bigserial primary key,
  invoice_number            text    not null,              -- REB00162368
  invoice_date              date    not null,              -- 07/07/2026 → 2026-07-07
  due_date                  date,
  currency                  text    default 'USD',
  agreement_no              text,                          -- DEAL-028978 or 100-17384
  agreement_name            text,                          -- for audit / debugging
  agreement_period_start    date,                          -- parsed from "3.1.26-3.31.26" or "01/Jun/2026 - 05/Jul/2026"
  agreement_period_end      date,
  agreement_period_label    text,                          -- 'P5-26' or 'LUMPSUM' etc.
  -- Per-line detail
  line_number               int     not null default 1,    -- 1..N within the invoice
  rebate_name               text    not null,              -- 'HG EverGreen B3G1', 'Damages', 'MDF/Coop', etc.
  rebate_pct_rate           numeric(6,3),                  -- 2, 1.5, 16 — null for lumpsum
  transaction_type          text,                          -- 'PURCHASE' — null for lumpsum
  vendor_name               text    default 'SMARTERPAW LLC',
  -- Derived at parse time; user-editable via the retroactive-edit UI (v7.03 later).
  brand                     text,                          -- 'Meowijuana' | 'Doggijuana' | 'Kitty Ka-Zoom' | null
  category                  text,                          -- 'ad_spend' | 'trade_allowance' | 'coop_marketing' | 'promo' | 'damages' | 'freight' | 'satisfaction' | 'other'
  rebate_amount             numeric(12,2) not null,
  -- Audit trail — full raw text of the PDF for later re-parsing if the
  -- categorization rules change. Small (~2KB per invoice).
  raw_extracted_text        text,
  source                    text    default 'chewy-rebate-pdf',
  uploaded_at               timestamptz default now(),
  unique (invoice_number, line_number)
);

create index if not exists chewy_rebates_date_idx     on chewy_rebates(invoice_date desc);
create index if not exists chewy_rebates_brand_idx    on chewy_rebates(brand)    where brand    is not null;
create index if not exists chewy_rebates_category_idx on chewy_rebates(category) where category is not null;

-- RLS + grants (v6.47 hard rule).
alter table chewy_rebates enable row level security;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='chewy_rebates'
      and policyname='chewy_rebates_authenticated_all'
  ) then
    create policy chewy_rebates_authenticated_all
      on chewy_rebates for all to authenticated using (true) with check (true);
  end if;
end $$;
grant select, insert, update, delete on table chewy_rebates to authenticated;
grant usage, select on sequence chewy_rebates_id_seq to authenticated;
revoke all on table chewy_rebates from anon;

-- Verify (post-run):
--   select category, brand, count(*), round(sum(rebate_amount)::numeric, 2) as total
--   from chewy_rebates group by 1, 2 order by 1, 2 nulls last;
