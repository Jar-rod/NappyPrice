from __future__ import annotations

from dataclasses import asdict, dataclass

CATEGORIES = {"nappies": "Nappies", "wipes": "Wipes", "formula": "Formula", "bin_refills": "Bin refills",
              "sterilising": "Sterilising", "other": "Other"}
# Default unit a price is divided into. A product can override it (Milton tablets are per tablet).
UNIT_LABELS = {"nappies": "nappy", "wipes": "wipe", "formula": "bottle", "bin_refills": "cartridge",
               "sterilising": "100ml", "other": "unit"}
UNIT_CHOICES = ["nappy", "wipe", "bottle", "cartridge", "tablet", "100ml", "100g", "unit"]


def size_word(category: str | None) -> str:
    """What the `size` field means for a category: a nappy size or a formula stage."""
    return "stage" if category == "formula" else "size"
SIZES = ["NB", "1", "2", "3", "4", "4+", "5", "5+", "6", "7", "8"]


@dataclass
class ProductPage:
    """What one store's product page told us."""

    url: str
    store_id: str
    title: str | None = None
    brand: str | None = None
    range_name: str | None = None
    size: str | None = None
    units_per_pack: int | None = None
    price: float | None = None
    was_price: float | None = None
    on_special: bool = False
    in_stock: bool | None = None
    image_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchHit:
    url: str
    title: str
    price: float | None = None
