"""Add an item from the command line, the same way the Add page does.

    uv run python -m scraper.add <product-url> --category formula            # show what would be added
    uv run python -m scraper.add <product-url> --category formula --save     # add it
    uv run python -m scraper.add --product "Milton sterilising fluid" --store amazon [--save]
                                                    # find an item you already track at another store
    ... --name "Alula Gold RTF" --min-score 85 --also <url> <url>

Matches at other stores scoring at least --min-score are included. --also adds
specific candidate links regardless of score (a different pack size, say).
"""
from __future__ import annotations

import argparse

from core.items import add_listings, save_item, unit_price
from core.models import CATEGORIES, size_word
from core.repo import get_repo
from scraper.adapters import store_rows
from scraper.fetch import Fetcher
from scraper.match import PRETICK_SCORE, find_matches, with_category
from scraper.run import run_match


def extend_product(repo, args) -> None:
    """Search one or more stores for an item already tracked, and add the matches."""
    wanted = args.product.lower()
    found = [p for p in repo.list_products() if wanted in ui_name(p).lower()]
    if len(found) != 1:
        raise SystemExit(f"--product must match exactly one item; '{args.product}' matches: "
                         + (", ".join(ui_name(p) for p in found) or "nothing"))
    product = found[0]
    listings = repo.list_listings(product["id"])
    if not listings:
        raise SystemExit("That item has no listings to compare against.")
    # The listing the item was created from describes it best; fall back to the first.
    model = next((l for l in listings if l.get("match_score") is None and l.get("title")), listings[0])
    target = with_category({"title": model.get("title") or product["name"], "brand": product.get("brand"),
                            "range_name": product.get("range_name"), "size": product.get("size"),
                            "units_per_pack": model["units_per_pack"]}, product["category"])
    target.update(size=product.get("size"), units_per_pack=model["units_per_pack"])
    unit = product.get("unit_label") or "unit"
    fetcher = Fetcher()
    try:
        candidates, errors = find_matches(repo, fetcher, target, only_stores=set(args.store))
    finally:
        fetcher.close()
    print(f"{ui_name(product)} | like: {model.get('title')} ({model['units_per_pack']})")
    entries = []
    for store_id, cands in candidates.items():
        for cand in cands:
            chosen = (cand["score"] >= args.min_score or cand["url"] in args.also) and cand.get("units_per_pack")
            if chosen:
                entries.append(cand)
            per = unit_price(cand.get("price"), cand.get("units_per_pack"))
            print(f"  {'+' if chosen else ' '} {store_id:10} {cand['score']:>3}  R{cand.get('price')} / "
                  f"{cand.get('units_per_pack')} = {'R%.2f' % per if per else '?'} per {unit}  {cand.get('title')}"
                  f"\n{'':8}{cand['url']}")
        if not cands:
            print(f"    {store_id:10} no matches")
    for store_id, error in errors.items():
        print(f"  ! {store_id}: {error}")
    if args.save and entries:
        print(f"\nAdded {add_listings(repo, product, entries)} listings.")
    else:
        print(f"\n{len(entries)} listings marked + would be added. Re-run with --save to add.")


def ui_name(product: dict) -> str:
    size = product.get("size")
    return product["name"] + (f" {size_word(product.get('category'))} {size}" if size else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add an item by product link, or find a tracked item at more stores")
    parser.add_argument("url", nargs="?")
    parser.add_argument("--product", help="name of an item already tracked; search --store for it")
    parser.add_argument("--store", nargs="*", default=[], help="store ids to search with --product")
    parser.add_argument("--category", choices=list(CATEGORIES), default="nappies")
    parser.add_argument("--name")
    parser.add_argument("--units", type=int, help="pack count at the linked store, if it cannot be read")
    parser.add_argument("--min-score", type=int, default=PRETICK_SCORE)
    parser.add_argument("--also", nargs="*", default=[], help="candidate links to include whatever their score")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    repo = get_repo()
    repo.ensure_stores(store_rows())
    if args.product:
        if not args.store:
            parser.error("--product needs --store")
        return extend_product(repo, args)
    if not args.url:
        parser.error("give a product link, or --product with --store")
    fetcher = Fetcher()
    try:
        result = run_match(repo, fetcher, {"url": args.url, "category": args.category})
    finally:
        fetcher.close()
    page = result["page"]
    if page.get("error"):
        raise SystemExit(f"Could not read the page: {page['error']}")
    page["units_per_pack"] = args.units or page.get("units_per_pack")
    unit = page.get("unit_label") or "unit"
    name = args.name or " ".join(p for p in (page.get("brand"), page.get("range_name")) if p) or page.get("title")

    def line(entry, mark):
        per = unit_price(entry.get("price"), entry.get("units_per_pack"))
        return (f"  {mark} {entry['store_id']:10} {str(entry.get('score', 'src')):>3}  "
                f"R{entry.get('price')} / {entry.get('units_per_pack')} = "
                f"{'R%.2f' % per if per else '?'} per {unit}  {entry.get('title')}\n{'':8}{entry['url']}")

    entries = [page] if page.get("units_per_pack") else []
    print(f"{name} | {CATEGORIES[args.category]} | {size_word(args.category)} {page.get('size')} | per {unit}")
    print(line(page, "+" if entries else "!"))
    for store_id, found in result["candidates"].items():
        for cand in found:
            chosen = (cand["score"] >= args.min_score or cand["url"] in args.also) and cand.get("units_per_pack")
            if chosen:
                entries.append(cand)
            print(line(cand, "+" if chosen else " "))
    for store_id, error in result["errors"].items():
        print(f"  ! {store_id}: {error}")
    if not page.get("units_per_pack"):
        raise SystemExit("Pack count could not be read from the linked page; pass --units N.")
    if args.save:
        product = save_item(repo, {**page, "name": name, "category": args.category}, entries, created_by="cli")
        print(f"\nSaved with {len(entries)} listings, target R{product['target_unit_price']} per {unit}.")
    else:
        print(f"\n{len(entries)} listings marked + would be saved. Re-run with --save to add.")


if __name__ == "__main__":
    main()
