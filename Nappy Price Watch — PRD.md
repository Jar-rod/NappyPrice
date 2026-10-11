# Nappy Price Watch — PRD

Oct 11, 2026 · @Jarrod

## Overview

Nappy Price Watch tracks nappy and Angelcare refill prices across South African stores once a day, and alerts us by phone and email when an item drops below our target or goes on special.

**Problem.** Twins use about 16 to 24 nappies a day between them. Prices and pack sizes vary widely between stores, and specials come and go. Checking nine store sites by hand is not realistic with two newborns.

**Goals**

- Know the cheapest price per nappy and per refill cartridge, across all tracked stores, at a glance
- Get an alert within a day when a watched item hits its target price or is marked on special
- See price history so we can tell a real special from a normal price dressed up as one
- Add or remove items in under a minute by pasting a single product link

**Success measures**

- At least 7 of the 9 target stores return prices on a normal day
- No more than one alert per item per special (no repeat spam)
- A broken store scraper is reported within 3 days, never silently ignored
- Running cost R0/month on free tiers

## Highlight functionality

Six features carry the product; everything else in this PRD supports them.

| # | Feature | What it does | Priority |
| --- | --- | --- | --- |
| 1 | Add by link | Paste one product link; the app reads brand, range, size, pack count and price from the page, then searches the other stores for the same product | Must |
| 2 | Match confirmation | Shows candidate matches from other stores with a match score; you tick which to keep so wrong pack sizes never skew prices | Must |
| 3 | Price-per-unit dashboard | Every watched item grouped by category and size, showing cheapest price per nappy or cartridge, the store, a special badge and the change since last week | Must |
| 4 | Price history graph | Per item, one line per store, plotted as price per unit over time | Must |
| 5 | Alert flags | Per item on/off switch and editable target price; alerts fire on below-target or marked-on-special, by push and email to both of you, once per special | Must |
| 6 | Store health | Flags a store whose scraper has failed 3 days running, so breakage is never silent | Should |

Removing an item stops tracking but keeps its history, so re-adding it later brings the graph back.

## Users and key flows

Two users, you and your wife, with equal rights: both can add, remove and edit items, and both receive every alert.

**Access.** Google sign-in through Streamlit's built-in login, restricted to an allowlist of two email addresses in app secrets. Anyone else who reaches the URL sees a sign-in page only.

**Flow 1: Add an item by link**

1. Paste a product link from any supported store.
2. The app fetches the page and extracts name, brand, range, size, pack count, price and image. Fields it cannot read are left blank for you to fill.
3. You check or correct the extracted fields, and pick the category (Nappies, Bin refills, Other).
4. The app searches every other active store for the same product and returns up to 5 candidates per store, each with a match score.
5. You tick the matches to keep. Strong matches (score 85 and up) are pre-ticked; weaker ones are not.
6. The item is saved with alerts on and a suggested target 15% below today's cheapest price per unit. You can edit both straight away.

**Flow 2: Daily check**

1. At 06:45 SAST the job scrapes every active listing.
2. It saves a price check per listing, computing price per unit.
3. It evaluates alert rules for items with alerts on, and sends one combined push and email if anything fired.
4. It records store failures and raises a store-health alert after 3 consecutive failed days.

**Flow 3: Remove an item**

Remove sets the item to inactive after a confirm prompt. Its listings stop being scraped, its history stays, and it moves to an Archived view where it can be restored.

## Screens

Four pages in a Streamlit multipage app, built mobile-first because most checks will happen on a phone during a night feed.

| Page | Contents | Actions |
| --- | --- | --- |
| Dashboard | Items grouped by category, then size (Newborn, 1 to 6). Each row: image, name, cheapest price per unit, store, special badge, change vs 7 days ago, alert toggle. A filter for "alerts on only" and a "last checked" timestamp at the top | Toggle alerts, open item, "Check now" button |
| Item detail | Price history line chart (price per unit, one line per store, 30/90/all days); table of current listings with price, pack price, special, was-price, in stock, link | Edit target price, edit name/size/pack count, add or remove a store listing, remove item |
| Add item | Link field, extracted fields form, candidate matches per store with scores and checkboxes | Save item |
| Alerts and health | Alert log (date, item, store, rule, price); store health table (store, last success, consecutive failures) | Mute a store, retry a store |

**UI rules**

- Prices always shown as R per unit first, pack price second, so different pack sizes compare fairly
- Special badge only when the store's page marks a promotion or shows a was-price
- Charts with Plotly via `st.plotly_chart`, which supports touch zoom on phones
- No page needs more than one tap from the dashboard

## Alerts

Alerts fire on two rules only, for items with the alert flag on, and arrive as one combined message per day.

| Rule | Fires when | Notes |
| --- | --- | --- |
| Below target | Price per unit at any active listing is at or below the item's target | Target is per unit, so a bigger pack that hits it also counts |
| On special | The store marks the listing as a promotion, or shows a was-price above the current price | Fires even if the special is still above target |

**No repeat spam.** An alert fires once per listing per rule per episode. An episode ends when a daily check finds the condition no longer true, so the next special on that listing alerts again.

**Message content.** Item name and size, store, pack price, price per unit, the rule that fired, the was-price if any, and the product link. Several hits are bundled into one push and one email, cheapest first.

**Delivery**

- Push: ntfy (free). Both phones subscribe to one private, hard-to-guess topic name, kept in secrets. Pushover is the drop-in fallback if ntfy proves unreliable
- Email: Resend free tier, sent to both addresses
- Each send is logged in `alerts_sent`; a failed send is retried once and logged as failed

**Quiet hours.** None by default, since the check runs at 06:45. If "Check now" runs at night, push goes out silently (low priority) and email as normal.

## Tech stack and architecture

All scraping runs in one GitHub Actions job; the Streamlit app only reads and edits the database and starts the job on demand.

&#91;embedded content: architecture · 6 parts\]

Playwright is too heavy for Streamlit Community Cloud, so add-item searches and "Check now" run as on-demand jobs: the app writes a row to `jobs`, starts the workflow through the GitHub API, and polls the row for the result.

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12 | One language for scraper and UI |
| Scraping | httpx + BeautifulSoup (selectolax if speed matters), Playwright for JavaScript-rendered stores | Cheap HTTP first, browser only where needed |
| Matching | rapidfuzz | Fast fuzzy title scoring |
| Scheduler | GitHub Actions cron + workflow\_dispatch | Free, no server |
| Database | Supabase Postgres (supabase-py) | Free tier, SQL, history queries |
| Front end | Streamlit multipage app, Plotly charts, `st.login` with Google | Quickest Python UI with login |
| Hosting | Streamlit Community Cloud | Free, deploys from the repo |
| Push | ntfy (Pushover as fallback) | Free, one HTTP POST |
| Email | Resend | Free tier, simple API |
| Tests | pytest with saved HTML fixtures | Catches store layout changes |

**Extra table for on-demand jobs**

```sql
create table jobs (
  id         uuid primary key default gen_random_uuid(),
  kind       text not null,          -- 'match' | 'check_now'
  input      jsonb,                  -- e.g. {"url": "https://..."}
  status     text default 'queued',  -- queued | running | done | failed
  result     jsonb,                  -- extracted fields + candidates
  created_at timestamptz default now()
);
```

**Repo layout**

```
nappy-price-watch/
  app/                 # Streamlit
    Home.py            # dashboard
    pages/1_Item.py
    pages/2_Add_item.py
    pages/3_Alerts.py
  scraper/
    adapters/          # one file per store
    extract.py         # JSON-LD, meta, selectors
    parse.py           # size, pack count, special
    match.py           # search + scoring
    alerts.py          # rules, dedupe, ntfy, Resend
    run.py             # entry point: daily | match | single
  db/schema.sql
  tests/fixtures/      # saved store pages
  .github/workflows/check.yml
```

## Data model

Five Postgres tables in Supabase. A product is the thing you want (Pampers Premium Care size 2); a listing is that product at one store; a price check is one daily reading of a listing.

```sql
create table stores (
  id            text primary key,          -- 'clicks', 'dischem', 'takealot'
  name          text not null,
  base_url      text not null,
  search_url    text not null,             -- e.g. 'https://.../search?q={q}'
  needs_browser boolean default false,     -- true = use Playwright
  active        boolean default true,
  consecutive_failures int default 0,
  last_success_at timestamptz
);

create table products (
  id               uuid primary key default gen_random_uuid(),
  name             text not null,
  brand            text,
  range_name       text,                   -- 'Premium Care', 'Gold'
  category         text not null,          -- 'nappies' | 'bin_refills' | 'other'
  size             text,                   -- 'NB','1'..'6', null for refills
  unit_label       text default 'nappy',   -- 'nappy' | 'cartridge'
  alert_enabled    boolean default true,
  target_unit_price numeric(10,4),         -- rand per unit
  active           boolean default true,
  created_by       text,                   -- user email
  created_at       timestamptz default now()
);

create table listings (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid references products(id),
  store_id    text references stores(id),
  url         text not null unique,
  title       text,                        -- as the store names it
  units_per_pack int not null,
  match_score int,                         -- 0-100, null if added manually
  active      boolean default true
);

create table price_checks (
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
create index on price_checks (listing_id, checked_at desc);

create table alerts_sent (
  id          bigserial primary key,
  listing_id  uuid references listings(id),
  rule        text not null,               -- 'below_target' | 'on_special' | 'store_health'
  episode_open boolean default true,       -- closed when condition clears
  sent_at     timestamptz default now(),
  channel     text,                        -- 'push' | 'email'
  status      text                         -- 'sent' | 'failed'
);
```

A view `latest_prices` (latest ok check per active listing) feeds the dashboard. Row-level security stays on, and only the job's service key and the app's server-side key can read or write.

## Scraping, extraction and matching

Each store is a small adapter class behind one interface, so a broken store is fixed in one file without touching the rest.

```python
class StoreAdapter(Protocol):
    store_id: str
    needs_browser: bool
    def extract(self, url: str) -> ProductPage: ...        # one product page
    def search(self, query: str) -> list[SearchHit]: ...  # store search results
```

**Extracting a product page** (try in order, stop at the first that gives a price)

1. JSON-LD `schema.org/Product` in the page: `name`, `brand`, `offers.price`, `offers.availability`, `image`
2. Open Graph / meta tags such as `product:price:amount`
3. Store-specific CSS selectors in the adapter
4. Same three steps again on the Playwright-rendered page, for stores that load prices with JavaScript

**Parsing the title** with regex helpers, unit-tested against real titles:

- Size: `newborn|nb|size 0` to NB; `size ?(\d)|s(\d)\b|maxi|midi|mini` mapped to 1 to 6
- Pack count: `(\d+)\s?(s|pack|pc|nappies)\b`, `x\s?(\d+)`, "jumbo 76"
- Special: was-price present, or a promo badge text such as "Save", "Special", "Promo"
- Price per unit = pack price / units per pack

**Finding the same product at other stores**

1. Build a query from brand, range and size, for example `pampers premium care size 2`.
2. Run each active store's search and take the top 10 hits.
3. Extract each hit and score it out of 100: brand 30, range 20, size 25, pack count 15, title similarity 10 (rapidfuzz `token_set_ratio`).
4. Return the best 5 per store to the confirmation screen; 85 and up are pre-ticked.

**Bin refills.** Genuine and compatible cartridges are tracked as separate products, so a cheaper compatible refill never hides inside the genuine price line. The dashboard shows them side by side under Bin refills.

**Expected store approach** (to be confirmed in the Milestone 1 spike)

| Store | Likely method | Risk |
| --- | --- | --- |
| Clicks | HTTP + JSON-LD | Low |
| Dis-Chem | HTTP + JSON-LD | Low |
| Takealot | Playwright, or its public product data in page | Medium |
| Checkers Sixty60 | Playwright | Medium to high, app-first, may need a delivery area |
| Pick n Pay | Playwright | Medium |
| Makro | HTTP or Playwright | Medium |
| Baby City | HTTP + JSON-LD | Low |
| Amazon.co.za | Playwright | High, CAPTCHAs likely; optional |
| Babies R Us | To confirm it sells online in SA | Unknown |

## Scheduling and reliability

One GitHub Actions workflow runs daily at 04:45 UTC (06:45 SAST) and can also be started on demand.

```yaml
on:
  schedule:
    - cron: "45 4 * * *"        # 06:45 SAST
  workflow_dispatch:             # "Check now" and add-item searches
    inputs:
      mode: { default: "daily" }  # daily | match | single
      job_id: { required: false }
```

**Reliability rules**

- GitHub may start scheduled runs late on busy days; a delay of up to an hour is acceptable
- Each listing is retried twice with backoff (5s, 20s) before it is recorded as failed
- A failed store never stops the run; other stores continue
- After 3 consecutive failed days a store raises one store-health alert, then stays quiet until it recovers
- If 3 or more stores fail on the same day, send a single "scraper may be broken" alert instead of one per store
- The workflow fails loudly (GitHub email) if it cannot reach Supabase at all
- GitHub disables scheduled workflows in repos with no commits for 60 days; a monthly no-op commit or a keep-alive action prevents this

**Data retention.** Keep all price checks. At roughly 40 listings × 365 days, that is about 15,000 rows a year, well inside Supabase's free tier.

## Non-functional requirements

The app must stay free to run, private to two people, and polite to the stores it reads.

**Security**

- All secrets (Supabase service key, Resend key, ntfy topic, allowed emails) live in GitHub Actions secrets and Streamlit secrets, never in the repo
- The repo is private
- The Streamlit app uses a server-side Supabase key and never exposes it to the browser
- Only links from stores in the `stores` table are accepted on the Add page

**Scraping etiquette**

- One run a day, plus on-demand checks; no polling
- At least 3 seconds between requests to the same store, run one store at a time
- A real browser user agent, no attempts to defeat CAPTCHAs or logins; a store that blocks us is dropped, not fought
- Read each store's terms of use before adding its adapter; personal, low-volume use only

**Performance**

- Daily run finishes in under 15 minutes for 50 listings (GitHub free tier allows 2,000 minutes a month on private repos)
- Dashboard loads in under 5 seconds once the app is awake; first load after idle can take longer on Streamlit Community Cloud

**Cost**

| Service | Plan | Cost |
| --- | --- | --- |
| GitHub Actions | Free, private repo | R0 |
| Supabase | Free tier | R0 |
| Streamlit Community Cloud | Free | R0 |
| ntfy | Free public server | R0 |
| Resend | Free tier | R0 |
| Pushover (fallback only) | Once-off licence per platform | About R100 once |

## Build plan

Build alerts before the UI: by the end of Milestone 3 you get useful alerts, even if items are still added by hand in SQL. Each milestone is sized for a few evenings.

1. **Setup.** Private repo, Python project (uv or Poetry), Supabase project with the schema, secrets in GitHub. *Done when:* a test script writes a row to Supabase from a GitHub Action.
2. **Spike: two easy stores.** Clicks and Dis-Chem adapters, `extract()` only, plus title-parsing helpers with unit tests on 20 real titles. *Done when:* both return price, pack count and size for 5 nappy links each.
3. **Daily job and alerts.** Scheduled workflow, price checks, unit price, below-target and on-special rules, episode dedupe, ntfy and Resend. Seed 4 to 6 products by SQL. *Done when:* a forced low target produces exactly one push and one email, and none the next day.
4. **Dashboard and history.** Streamlit app with Google login allowlist, dashboard grouped by category and size, alert toggles, item detail with Plotly history, editable target, remove and restore. *Done when:* both of you can sign in on your phones and toggle an alert.
5. **Add by link.** `jobs` table, match mode in the workflow, store `search()` for Clicks and Dis-Chem, match scoring, confirmation screen. *Done when:* pasting one Clicks link finds and saves the Dis-Chem equivalent.
6. **More stores.** Baby City, Makro, Pick n Pay, Takealot, Checkers Sixty60, then Amazon.co.za and Babies R Us if feasible. *Done when:* at least 7 stores return prices on a normal day.
7. **Store health and polish.** Health page, 3-day failure alert, mass-failure alert, keep-alive for the schedule, "Check now" button. *Done when:* disabling one adapter produces a single store-health alert after 3 days.

**Testing.** Save a fixture HTML file per store and unit-test extraction against it, so a store layout change shows up as a failing test with a clear diff.

## Out of scope and open questions

Version 1 tracks online shelf prices only; anything else waits for a later version.

**Out of scope for v1**

- In-store-only specials, printed catalogues and loyalty prices (Clicks ClubCard, Dis-Chem Benefit, Smart Shopper, Xtra Savings) unless shown on the public product page
- Delivery fees and minimum-order rules
- Automatic buying or adding to cart
- Native mobile app; the Streamlit page is added to the home screen instead
- Lowest-in-30-days and back-in-stock alerts (data is stored, so these are easy to add later)

**Open questions**

- [ ] Does Babies R Us sell online in South Africa with product pages we can read?
- [ ] Does Checkers Sixty60 show prices without a delivery address set?
- [ ] Is Amazon.co.za worth keeping if it needs CAPTCHAs on most runs?
- [ ] Should loyalty-card prices count as "on special" when a store shows them publicly?
- [ ] Default target discount: 15% below today's cheapest, or 15% below the 30-day average once history exists?
