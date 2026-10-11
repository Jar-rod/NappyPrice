-- Nappy Price Watch schema. Run once in the Supabase SQL editor.
-- Safe to re-run: every statement is "if not exists" or "or replace".

create table if not exists stores (
  id            text primary key,          -- 'clicks', 'dischem', 'takealot'
  name          text not null,
  base_url      text not null,
  search_url    text not null,             -- e.g. 'https://.../search?q={q}'
  needs_browser boolean default false,     -- true = use Playwright
  active        boolean default true,
  muted         boolean default false,     -- true = no store-health alerts
  note          text,                      -- why a store is inactive
  consecutive_failures int default 0,
  last_success_at timestamptz
);

create table if not exists products (
  id               uuid primary key default gen_random_uuid(),
  name             text not null,
  brand            text,
  range_name       text,                   -- 'Premium Care', 'Gold'
  category         text not null,          -- 'nappies' | 'bin_refills' | 'other'
  size             text,                   -- 'NB','1'..'8', null for refills
  unit_label       text default 'nappy',   -- 'nappy' | 'cartridge' | 'unit'
  image_url        text,
  alert_enabled    boolean default true,
  target_unit_price numeric(10,4),         -- rand per unit
  active           boolean default true,
  created_by       text,                   -- user email
  created_at       timestamptz default now()
);

create table if not exists listings (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid references products(id),
  store_id    text references stores(id),
  url         text not null unique,
  title       text,                        -- as the store names it
  units_per_pack int not null,
  match_score int,                         -- 0-100, null if added manually
  active      boolean default true
);

create table if not exists price_checks (
  id          bigserial primary key,
  listing_id  uuid references listings(id),
  checked_at  timestamptz default now(),
  ok          boolean not null,            -- false = scrape failed
  price       numeric(10,2),
  unit_price  numeric(10,4),
  was_price   numeric(10,2),
  on_special  boolean,
  in_stock    boolean,
  error       text
);
create index if not exists price_checks_listing_checked_idx
  on price_checks (listing_id, checked_at desc);

create table if not exists alerts_sent (
  id          bigserial primary key,
  listing_id  uuid references listings(id),  -- null for store alerts
  store_id    text references stores(id),    -- null for 'mass_failure'
  rule        text not null,               -- 'below_target' | 'on_special' | 'store_health' | 'mass_failure'
  episode_open boolean default true,       -- closed when condition clears
  sent_at     timestamptz default now(),
  channel     text,                        -- 'push' | 'email'
  status      text,                        -- 'sent' | 'failed'
  price       numeric(10,2),
  unit_price  numeric(10,4)
);
create index if not exists alerts_sent_open_idx on alerts_sent (episode_open) where episode_open;

create table if not exists jobs (
  id         uuid primary key default gen_random_uuid(),
  kind       text not null,          -- 'match' | 'check_now'
  input      jsonb,                  -- e.g. {"url": "https://..."}
  status     text default 'queued',  -- queued | running | done | failed
  result     jsonb,                  -- extracted fields + candidates
  created_at timestamptz default now()
);

-- Latest successful check per active listing; feeds the dashboard.
create or replace view latest_prices with (security_invoker = true) as
select distinct on (pc.listing_id) pc.*
from price_checks pc
join listings l on l.id = pc.listing_id and l.active
where pc.ok
order by pc.listing_id, pc.checked_at desc;

-- Row-level security on, with no policies: only the service key (which
-- bypasses RLS) can read or write. The anon key sees nothing.
alter table stores       enable row level security;
alter table products     enable row level security;
alter table listings     enable row level security;
alter table price_checks enable row level security;
alter table alerts_sent  enable row level security;
alter table jobs         enable row level security;
