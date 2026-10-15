"""Read size, pack count, brand, range and price out of store titles."""
from __future__ import annotations

import re

# Longest names first so "Clicks Made 4 Baby" wins over a bare "Clicks".
BRANDS = [
    "Clicks Made 4 Baby", "Made 4 Baby", "Pick n Pay", "Mother Nature", "Pure Beginnings",
    "Little One", "Baby Things", "Baby Soft", "Nature's Child", "Tommee Tippee",
    "Pampers", "Huggies", "Cuddlers", "Bennetts", "Angelcare", "Sangenic", "Twist & Click",
    "Kiddicare", "Bambo", "Eco Boom", "Biolane", "Lizzy", "Nannys", "Molfix",
    "Alula", "Milton", "Lactogen", "Infacare", "Novalac", "Similac", "Nestle", "Nan",
    "WaterWipes", "Cherubs", "Johnson's", "Nepura",
]

# Per brand, longest first. A title's range is the first one found in it.
RANGES = {
    "pampers": ["Premium Care", "Active Baby-Dry", "Active Baby", "Baby-Dry", "Baby Dry",
                "New Baby", "Harmonie", "Splashers", "Complete Clean", "Sensitive", "Fresh"],
    "alula": ["Gold", "S-26"],
    "huggies": ["Gold Specialty", "Extra Care", "Dry Comfort", "Natural Soft", "Little Swimmers",
                "Pull-Ups", "Gold", "New Born"],
    "cuddlers": ["Sensitive", "Premium", "Comfort"],
    "bennetts": ["Bamboo", "Premium"],
}

_SIZE_WORDS = {"mini": "2", "midi": "3", "maxi": "4", "junior": "5"}

_SIZE_PATTERNS = [
    # An explicit "size N" wins over the word "newborn" ("Newborn Size 2" is a 2).
    (re.compile(r"\b(?:size|sz)\s?(\d)(\s?\+|\s?plus\b)?", re.I),
     lambda m: m.group(1) + ("+" if m.group(2) else "")),
    (re.compile(r"\b(?:newborn|new\s?born|nb)\b", re.I), lambda m: "NB"),
    (re.compile(r"\bs(\d)(\+)?(?=\s|$|[^\w'])", re.I),
     lambda m: m.group(1) + ("+" if m.group(2) else "")),
    (re.compile(r"\b(mini|midi|maxi|junior)(\s?\+|\s?plus\b)?", re.I),
     lambda m: _SIZE_WORDS[m.group(1).lower()] + ("+" if m.group(2) else "")),
]

_UNIT = r"(?:'s|’s|s|pk|pack|pc|pcs|pieces|nappies|nappy|diapers|pants|cassettes|cartridges|refills|count|ct)"
# "6 x 200ml", "24 x 200 ml" -> 6 bottles, 24 bottles: the count, not the volume.
_COUNT_OF_VOLUMES = re.compile(r"\b(\d{1,3})\s?x\s?\d+(?:[.,]\d+)?\s?(?:ml|l|g|kg)\b", re.I)
_PACK_PATTERNS = [
    # "32's (2 Pack)" -> two packs of 32
    (re.compile(rf"(?<![\d.\-])(\d{{1,3}})\s?{_UNIT}\s*\(\s?(\d{{1,2}})\s?(?:pack|pk|x)\s?\)", re.I),
     lambda m: int(m.group(1)) * int(m.group(2))),
    # "2x76", "2 x 76's" -> multipack: packs times count
    (re.compile(rf"\b(\d{{1,2}})\s?x\s?(\d{{1,3}})\s?{_UNIT}?(?![\d.]|\s?(?:kg|g|ml|cm|mm|m)\b)", re.I),
     lambda m: int(m.group(1)) * int(m.group(2))),
    # "60's", "52s", "44pk", "94 nappies", "3 pack"
    (re.compile(rf"(?<![\d.\-])(\d{{1,3}})[\s-]?{_UNIT}\b", re.I), lambda m: int(m.group(1))),
    # "pack of 60", "x 44", "x44"
    (re.compile(r"\bpack\s+of\s+(\d{1,3})\b", re.I), lambda m: int(m.group(1))),
    (re.compile(r"(?<![\d])\bx\s?(\d{1,3})\b(?!\s?(?:kg|g|ml|cm|mm|m)\b)", re.I), lambda m: int(m.group(1))),
    # "jumbo 76", "value pack 60", "mega pack - 104"
    (re.compile(r"\b(?:jumbo|mega|value|carry|giant|bulk|economy|convenience|jp|vp|cp|mb)(?:\s+pack|\s+box)?(?:\s+set)?\s*[-–:]?\s*(\d{1,3})\b", re.I),
     lambda m: int(m.group(1))),
    # Last resort: a bare count of 8 or more ("Jumbo Pack Pants 44").
    (re.compile(r"(?<![\d.\-])\b(\d{1,3})\b(?![\d.]|\s?x\b)(?!.*\b\d{1,3}\b)", re.I),
     lambda m: int(m.group(1)) if int(m.group(1)) >= 8 else 0),
]

# Stripped before pack-count parsing so "3-8 kg" or "size 4" never read as counts.
_NOISE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:-|–|to)\s?\d+(?:[.,]\d+)?\s?\+?\s?kgs?\b"   # 3-8 kg
    r"|\b\d+(?:[.,]\d+)?\s?\+?\s?(?:kgs?|ml|l|cm|mm|g)\b"                # 9kg, 250ml
    r"|\b(?:size|sz)\s?\d\s?\+?|\bs\d\+?(?=\s|$)"                         # size 4, sz4, S4+
    r"|\b\d\s?(?:-|–)\s?\d+\s?(?:months|m)\b",                          # 3-6 months
    re.I,
)

_PROMO_WORDS = re.compile(r"\b(save|special|promo|promotion|on promo|deal|% off|was)\b", re.I)


def parse_size(title: str | None) -> str | None:
    """Nappy size as 'NB' or '1'..'8' (with a trailing '+' where the store has one)."""
    if not title:
        return None
    for pattern, convert in _SIZE_PATTERNS:
        match = pattern.search(title)
        if match:
            size = convert(match)
            return "NB" if size in ("0", "0+") else size
    return None


def parse_pack_count(title: str | None) -> int | None:
    """Units in the pack, multiplying out multipacks ('2x76' is 152)."""
    if not title:
        return None
    volumes = _COUNT_OF_VOLUMES.search(title)
    if volumes:
        return int(volumes.group(1))
    cleaned = _NOISE.sub(" ", title)
    for pattern, convert in _PACK_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            count = convert(match)
            if 0 < count <= 600:
                return count
    return None


def parse_brand(title: str | None) -> str | None:
    if not title:
        return None
    for brand in BRANDS:
        if re.search(rf"(?<!\w){re.escape(brand)}(?!\w)", title, re.I):
            return "Clicks Made 4 Baby" if brand == "Made 4 Baby" else brand
    return None


def parse_range(title: str | None, brand: str | None) -> str | None:
    """Range name, with ' Pants' appended for pull-up pants so they never match taped nappies."""
    if not title:
        return None
    found = None
    for name in RANGES.get((brand or "").lower(), []):
        if re.search(rf"(?<!\w){re.escape(name).replace('\\-', '[- ]?')}(?!\w)", title, re.I):
            found = {"Baby Dry": "Baby-Dry", "Active Baby-Dry": "Active Baby"}.get(name, name)
            break
    is_pants = bool(re.search(r"\bpants?\b", title, re.I))
    if found and is_pants and "pants" not in found.lower():
        return f"{found} Pants"
    return found or ("Pants" if is_pants else None)


def parse_price(text: str | float | int | None) -> float | None:
    """'R 1 299.99', 'R219,99' or 219.99 -> 1299.99 / 219.99."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return round(float(text), 2) if text > 0 else None
    match = re.search(r"\d[\d\s,]*(?:[.,]\d{1,2})?", str(text))
    if not match:
        return None
    raw = re.sub(r"\s", "", match.group(0))
    if re.search(r",\d{1,2}$", raw) and "." not in raw:
        raw = raw.replace(",", ".")
    raw = raw.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return round(value, 2) if value > 0 else None


def unit_price(price: float | None, units_per_pack: int | None) -> float | None:
    if not price or not units_per_pack:
        return None
    return round(price / units_per_pack, 4)


def detect_special(price: float | None, was_price: float | None, badges: list[str] | None = None) -> bool:
    """On special when the store shows a higher was-price or a promotion badge."""
    if price and was_price and was_price > price:
        return True
    return any(_PROMO_WORDS.search(text or "") for text in badges or [])


_VOLUME = re.compile(r"(?:(\d{1,3})\s?x\s?)?(\d+(?:[.,]\d+)?)\s?(ml|litres?|liters?|l)\b", re.I)
_STAGE_EXPLICIT = re.compile(r"\b(?:stage|step|no\.?|number)\s?(\d)\b", re.I)
_STAGE_BARE = re.compile(r"(?<![\d.,\-–])(?<!x\s)\b([1-4])\b(?![.,]\d|\s?(?:-|–|x\b|ml\b|l\b|g\b|kg\b|months?\b|years?\b|pack\b))", re.I)


def parse_volume_ml(title: str | None) -> float | None:
    """Total liquid volume in ml: '500ml' -> 500, '1 Litre' -> 1000, '6 x 200ml' -> 1200."""
    match = _VOLUME.search(title or "")
    if not match:
        return None
    amount = float(match.group(2).replace(",", "."))
    if match.group(3).lower() != "ml":
        amount *= 1000
    return amount * int(match.group(1) or 1)


_WEIGHT = re.compile(r"(?:(\d{1,3})\s?x\s?)?(\d+(?:[.,]\d+)?)\s?(kg|g)\b", re.I)


def parse_weight_g(title: str | None) -> float | None:
    """Total weight in grams: '400g' -> 400, '1.8kg' -> 1800, '2 x 900g' -> 1800."""
    match = _WEIGHT.search(title or "")
    if not match:
        return None
    amount = float(match.group(2).replace(",", "."))
    if match.group(3).lower() == "kg":
        amount *= 1000
    return amount * int(match.group(1) or 1)


def parse_stage(title: str | None) -> str | None:
    """Formula stage: 'Stage 1', 'No.1' and 'Alula Gold 1 Rtf' are all stage 1."""
    if not title:
        return None
    match = _STAGE_EXPLICIT.search(title) or _STAGE_BARE.search(title)
    return match.group(1) if match else None


def is_ready_to_feed(title: str | None) -> bool:
    return bool(re.search(r"ready[\s-]to[\s-]feed|read to feed|\brtf\b|\d\s?ml\b", title or "", re.I))


def unit_label_for(category: str, title: str | None) -> str:
    """The unit this product is priced in. Mostly fixed by category; sterilising splits by form."""
    from core.models import UNIT_LABELS

    if category == "sterilising":
        return "tablet" if re.search(r"tablet", title or "", re.I) else "100ml"
    if category == "formula" and not is_ready_to_feed(title):
        return "100g"   # powder is sold by weight; ready-to-feed by the bottle
    return UNIT_LABELS.get(category, "unit")


def describe(title: str | None, category: str) -> dict:
    """Size (or stage) and unit count for a title, read the way its category needs.

    Returns only the keys this category defines, so nappies keep what the
    store adapter already worked out (Makro's count comes from its spec table).
    """
    if category == "nappies" or not title:
        return {}
    count = parse_pack_count(title)
    if category == "formula":
        if is_ready_to_feed(title):
            # Counted in bottles; a lone bottle is 1.
            return {"size": parse_stage(title), "units_per_pack": count or 1}
        # Powder is counted in 100g units, so a 400g tin is 4 and a 1.8kg tin is 18.
        weight = parse_weight_g(title)
        return {"size": parse_stage(title), "units_per_pack": round(weight / 100) if weight and weight >= 100 else None}
    if category == "sterilising" and unit_label_for(category, title) == "100ml":
        volume = parse_volume_ml(title)
        return {"size": None, "units_per_pack": round(volume / 100) if volume and volume >= 100 else None}
    if category == "bin_refills" and count is None and not re.search(r"\bbin\b(?!.*refill)|system", title, re.I):
        count = 1   # "Angelcare Nappy Bin Refills" with no number is the single pack
    return {"size": None, "units_per_pack": count}


def query_variants(target: dict) -> list[str]:
    """Search texts to try in order. Some store searches are strict: Dis-Chem finds nothing
    for 'alula gold stage 1' but every tin for 'alula gold 1', so plainer forms follow."""
    first = build_query(target)
    brand, range_name, size = target.get("brand"), target.get("range_name"), target.get("size")
    plainer = [" ".join(p for p in (brand, range_name, size) if p), " ".join(p for p in (brand, range_name) if p)]
    variants = [first] + [re.sub(r"\s+", " ", v).strip().lower() for v in plainer if brand]
    return list(dict.fromkeys(v for v in variants if v))


def build_query(target: dict) -> str:
    """Search text for other stores, e.g. 'pampers premium care size 2'."""
    category = target.get("category") or "nappies"
    brand, range_name, size = target.get("brand"), target.get("range_name"), target.get("size")
    title = target.get("title") or target.get("name") or ""
    parts: list = [brand, range_name]
    if category == "nappies":
        parts.append(("newborn" if size == "NB" else f"size {size}") if size else None)
    elif category == "formula":
        parts += [f"stage {size}" if size else None, "ready to feed" if is_ready_to_feed(title) else None]
    elif category == "wipes":
        parts.append("wipes")
    elif category == "bin_refills":
        parts.append("refill")
    elif category == "sterilising":
        parts.append("sterilising " + ("tablets" if unit_label_for(category, title) == "tablet" else "fluid"))
    query = " ".join(p for p in parts if p).lower()
    if not brand:
        query = title.lower()
    return re.sub(r"\s+", " ", query).strip()
