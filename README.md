# Nappy Price Watch

Tracks nappy and bin-refill prices across South African stores once a day and
alerts by push and email when an item drops below its target or goes on special.
The full spec is in `Nappy Price Watch — PRD.md`.

## How it fits together

- `scraper/` runs in GitHub Actions (`.github/workflows/check.yml`): daily at 06:45 SAST, and on demand for "Check now" and add-by-link.
- `app/` is the Streamlit app. It reads and edits the database and starts on-demand runs; it never scrapes.
- `core/` is shared: database access, models, dashboard queries.
- Supabase holds the data (`db/schema.sql`).

## Stores

| Store | How it is read | Status |
| --- | --- | --- |
| Clicks | HTML | On |
| Dis-Chem | HTML (JSON-LD) | On |
| Baby City | HTML (JSON-LD) | On |
| Babies R Us | HTML | On |
| Makro | HTML (JSON-LD) | On |
| Pick n Pay | Site JSON endpoint | On |
| Takealot | Public product JSON | On |
<<<<<<< HEAD
| Amazon.co.za | Headless browser | Manual refresh only: read when you press Check now, skipped by the daily run |
| Checkers Sixty60 | Site JSON endpoint, with a delivery address | On |

Amazon.co.za throttles repeated requests, so the daily run leaves it out. Its prices update only on "Check now", and a price not refreshed in the last two days is shown greyed and never counted as the cheapest or in the average.
=======
| Amazon.co.za | Headless browser | Off: throttles repeated requests with 503 errors |
| Checkers Sixty60 | Site JSON endpoint, with a delivery address | On |

To try Amazon, set `active = true` on its row in the `stores` table.
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
**Two stores price by location.** Set these as repository *variables* (Settings → Secrets and variables → Actions → Variables) if the defaults are not your area:

- `PNP_STORE_CODE`: Pick n Pay region. Default `WC21`, the site's own default.
- `CHECKERS_ADDRESS_JSON`: Checkers Sixty60 delivery address. Default is Sandton City, 83 Rivonia Road. Branches differ: on the day this was built one branch had a 60-pack at R249.99 while the Sandton branch had it at R359.99. To use your own address, copy `DEFAULT_ADDRESS` from `scraper/adapters/checkers.py`, change the address and coordinates, and paste it as one line of JSON. The adapter refuses any price that comes back from a branch other than the ones serving that address.

## Setup

1. **Supabase.** Create a project, open the SQL editor and run `db/schema.sql`. Copy the project URL and the `service_role` key.
2. **ntfy.** Pick a long, hard-to-guess topic name and subscribe to it in the ntfy app on both phones.
3. **Resend.** Create an API key. To email two different addresses you must verify a sending domain in Resend and set `EMAIL_FROM` to an address on it; without a verified domain Resend only delivers to the account owner's own address.
4. **GitHub Actions secrets** (repo → Settings → Secrets and variables → Actions): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `NTFY_TOPIC`, `RESEND_API_KEY`, `EMAIL_FROM`, `ALERT_EMAILS` (both addresses, comma-separated).
5. **GitHub token for the app.** Create a fine-grained personal access token limited to this repo with *Actions: Read and write*. The app uses it to start "Check now" and add-by-link runs.
6. **App password.** Choose a long password; both of you use the same one. It goes in the app secrets as `APP_PASSWORD`.
7. **Streamlit Community Cloud.** Deploy the repo with main file `app/Home.py`, then paste the contents of `.streamlit/secrets.toml.example` into the app's Secrets box and fill it in.
8. Push to `main`, then run the **Price check** workflow once by hand (Actions → Price check → Run workflow) to confirm it reaches Supabase.

The app is protected by the one shared password. With no `APP_PASSWORD` set, nobody can get in. "Remember me on this device" keeps a device signed in for 180 days; "Sign out" at the bottom of the dashboard forgets it, and changing `APP_PASSWORD` signs every device out.

## Running locally

```sh
uv sync
uv run playwright install chromium        # only needed for browser-only stores
uv run pytest
```

With no Supabase settings the scraper and app use a local file, `.local_db.json`:

```sh
uv run python -m scraper.seed             # add a few sample products from live pages
uv run python -m scraper.run daily        # check every listing; alerts print instead of sending
AUTH_BYPASS=1 uv run streamlit run app/Home.py
```

`AUTH_BYPASS` skips the password for local use only; it is ignored as soon as `SUPABASE_URL` is set.

Other commands:

```sh
uv run python -m scraper.run daily --dry-run     # scrape and print, write and send nothing
uv run python -m scraper.run extract <url>       # show what one product page gives
```

## When a store changes its layout

A store whose scraper fails three days running raises one store-health alert. To fix it:

1. `uv run python -m scraper.run extract <product-url>` to see what is now missing.
2. Fix the store's file in `scraper/adapters/`.
3. Re-capture its fixtures so the tests cover the new layout:
   `uv run python -m scraper.capture <product-url>` and
   `uv run python -m scraper.capture --search <store_id> "pampers premium care size 3"`.
   Check the printed values against the live page before committing; they become what the tests expect.

## Adding a store

Add a `StoreAdapter` subclass in `scraper/adapters/`, register it in `scraper/adapters/__init__.py`, give it a colour in `app/charts.py`, and capture a fixture. The store row is created automatically on the next run. Read the store's terms of use first; this project is for personal, low-volume use (one run a day, three seconds between requests, no attempt to get past CAPTCHAs or logins).

## What can be tracked

Each item belongs to a category, and each category compares prices in its own unit:

| Category | Priced per | Notes |
| --- | --- | --- |
| Nappies | nappy | Matched on brand, range, size and pack count |
| Wipes | wipe | "4 x 56" counts as 224 wipes |
| Formula | bottle | Ready-to-feed only; matched on stage. Powder tins are a different product and are not mixed in |
| Bin refills | cartridge | Genuine and compatible refills never match each other |
| Sterilising | 100ml or tablet | Fluid and tablets are separate items |

The dashboard shows each category as a collapsible section, grouped by brand. Opening an item lists every store's price, best first; the graph draws one coloured line per store (its cheapest pack that day).

Items can be added from the Add page, or from the command line:

```sh
uv run python -m scraper.add <product-url> --category wipes          # shows what would be added
uv run python -m scraper.add <product-url> --category wipes --save   # adds it
```

Matches scoring 85 or more are included. `--min-score` lowers that to pull in other pack sizes, and `--also <url>` includes a specific listing.

## Alert rules

- **Below target:** price per unit at any listing is at or below the item's target.
- **On special:** the store shows a was-price above the current price, or marks a promotion.
- Each listing alerts once per rule per episode. An episode ends when a check finds the condition no longer true. Out-of-stock listings do not alert.
- Loyalty-card prices are not counted as specials.
