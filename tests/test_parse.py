import pytest

from scraper import parse

# Real titles from Clicks, Dis-Chem, Baby City, Babies R Us and Makro: (title, size, pack count)
TITLES = [
    ("Pampers Premium Care Nappies Size 6 36's", "6", 36),
    ("Pampers Premium Care Nappies Size 1 82's", "1", 82),
    ("Pampers Premium Care Nappies Value Pack Size 3 60's", "3", 60),
    ("Pampers Premium Care Pants Value Pack Size 5 42s", "5", 42),
    ("Pampers Premium Care Size 3 Value Pack - 60's", "3", 60),
    ("Pampers Active Baby Size 4+ Jumbo Pack - 62's", "4+", 62),
    ("Pampers Active Baby Pants Size 7 - 35 S Jumbo Pack", "7", 35),
    ("Huggies Extra Care Size 2 94s", "2", 94),
    ("Huggies Extra Care Disposable Diapers Size 3 60s", "3", 60),
    ("Pampers Premium Care Size 0 Cp - 30's", "NB", 30),
    ("Pampers Premium Care Set Size 2 Value Pack 2x76", "2", 152),
    ("Pampers Premium Care Mega Box Size 4 104", "4", 104),
    ("Pampers Active Pants Mega Box Size 5-100", "5", 100),
    ("Pampers Active Pants Mega Box Size 6 -96", "6", 96),
    ("Pampers Premium Care Mega Box Sz 3 - 120", "3", 120),
    ("Pampers Premium Care Mega Box Set Sz4 104", "4", 104),
    ("Pampers Active Baby Size 5 2 X 50 Set", "5", 100),
    ("Pampers Premium Care Junior 56's Jumbo Pack", "5", 56),
    ("Pampers New Baby Mini S2 JP 94", "2", 94),
    ("Pampers Active Baby Maxi Plus S4+ JP 62", "4+", 62),
    ("PAMPERS PREMIUM CARE VP 60 - SIZE 3", "3", 60),
    ("Pampers Baby Dry Size 6 Jumbo Pack Pants 44", "6", 44),
    ("Pampers Premium Care Size 1 (2-5 kg) 34 Nappies", "1", 34),
    ("pampers Size 2 (3-8 kg) , Jumbo pack 94 Nappies, Lotion with Aloe Tape Diapers", "2", 94),
    ("Pampers Premium Care Newborn Size 2 (76 Pack) Tape Diapers", "2", 76),
    ("pampers Premium Care Mega Box Size 5 (88's) Tape Diapers", "5", 88),
    ("Pampers Active Baby New Born Jumbo Pack 96", "NB", 96),
    ("Pampers Premium Care Size 1 Carry Pack", "1", None),
    ("Angelcare Nappy Bin Refill Cassettes 3 Pack", None, 3),
    ("Sangenic Twist & Click Refill x6", None, 6),
]


@pytest.mark.parametrize("title,size,count", TITLES)
def test_size_and_pack_count(title, size, count):
    assert parse.parse_size(title) == size
    assert parse.parse_pack_count(title) == count


@pytest.mark.parametrize("title,brand,range_name", [
    ("Pampers Premium Care Nappies Size 6 36's", "Pampers", "Premium Care"),
    ("Pampers Premium Care Pants Value Pack Size 5 42s", "Pampers", "Premium Care Pants"),
    ("Pampers Active Baby-dry Jumbo Pack", "Pampers", "Active Baby"),
    ("Huggies Extra Care Size 2 94s", "Huggies", "Extra Care"),
    ("HUGGIES GOLD SIZE 3 76s", "Huggies", "Gold"),
    ("Angelcare Nappy Bin Refill Cassettes 3 Pack", "Angelcare", None),
    ("Dove Body Wash 400ml", None, None),
])
def test_brand_and_range(title, brand, range_name):
    found = parse.parse_brand(title)
    assert found == brand
    assert parse.parse_range(title, found) == range_name


@pytest.mark.parametrize("text,value", [
    ("R219.99", 219.99), ("R 1 299.99", 1299.99), ("R219,99", 219.99), ("1,299.00", 1299.0),
    (269.99, 269.99), ("360.00", 360.0), ("", None), (None, None), ("R0.00", None),
])
def test_price(text, value):
    assert parse.parse_price(text) == value


def test_unit_price():
    assert parse.unit_price(219.99, 82) == 2.6828
    assert parse.unit_price(219.99, None) is None
    assert parse.unit_price(None, 82) is None


def test_special_needs_a_higher_was_price_or_a_badge():
    assert parse.detect_special(219.99, 360.0)
    assert not parse.detect_special(219.99, 219.99)
    assert not parse.detect_special(219.99, None)
    assert parse.detect_special(219.99, None, ["On promo"])
    assert not parse.detect_special(219.99, None, ["Free delivery"])


def test_query():
    q = parse.build_query
    assert q({"brand": "Pampers", "range_name": "Premium Care", "size": "2"}) == "pampers premium care size 2"
    assert q({"brand": "Pampers", "range_name": "Premium Care", "size": "NB"}) == "pampers premium care newborn"
    assert q({"brand": "Angelcare", "category": "bin_refills", "title": "Angelcare Nappy Bin 3 Pack Refill"}) \
        == "angelcare refill"
    assert q({"brand": "Pampers", "range_name": "Sensitive", "category": "wipes"}) == "pampers sensitive wipes"
    assert q({"brand": "Alula", "range_name": "Gold", "size": "1", "category": "formula",
              "title": "Alula Gold Stage 1 Ready to Feed 6 x 200ml"}) == "alula gold stage 1 ready to feed"
    assert q({"brand": "Milton", "category": "sterilising", "title": "Milton Sterilising Tablets 32's"}) \
        == "milton sterilising tablets"
    assert q({"category": "other", "title": "Some Odd Thing"}) == "some odd thing"


# Real titles from the stores: (category, title, size or stage, units)
OTHER_TITLES = [
    ("formula", "Alula Gold Stage 1 0-6 Months Ready to Feed Infant Starter Formula 6 x 200ml", "1", 6),
    ("formula", "Alula Gold Stage 1 0-6 Months Infant Starter Formula 200ml", "1", 1),
    ("formula", "Alula Gold 1 Rtf 200ml", "1", 1),
    ("formula", "Alula Gold No.1 Ready To Feed Formula 200ml", "1", 1),
    ("formula", "Alula Gold Stage 1 Ready To Feed 24 x 200ml", "1", 24),
    ("formula", "Alula Gold Stage 2 6-12 Months Ready to Feed Follow-On Formula 6 x 200ml", "2", 6),
    ("formula", "Alula Gold Stage 3 1-3 Years Ready to Feed Growing-Up Formula 6 x 200ml", "3", 6),
    ("formula", "Alula Gold 1 900g Tin", "1", None),            # powder: no bottle count
    ("formula", "Alula Gold Stage 1 0-6 Months Infant Starter Formula 1.8kg", "1", None),
    ("wipes", "Pampers Baby Wipes Sensitive 4's - 4x56", None, 224),
    ("wipes", "Pampers Sensitive Wet Wipes 224 (4x56) Baby Wipes", None, 224),
    ("wipes", "Pampers Sensitive Baby Wipes 4 x 56 Pack", None, 224),
    ("wipes", "Pampers Sensitive Baby Wipes 56 Pack", None, 56),
    ("wipes", "Pampers Sensitive Wipes - 336 (6x56) - 100% Purified Water Wipes", None, 336),
    ("bin_refills", "Angelcare Nappy Bin 3 Pack Refill", None, 3),
    ("bin_refills", "Angelcare 3pk Bin Refills", None, 3),
    ("bin_refills", "Angelcare Single Pack Nappy Bin Refill", None, 1),
    ("bin_refills", "Angelcare Nappy Bin Refills", None, 1),
    ("bin_refills", "Angelcare Odour Seal Nappy Bin Refills 3-Pack", None, 3),
    ("bin_refills", "12 Pack - Angelcare & Tommee Tippee Compatible Nappy Bin Refills", None, 12),
    ("bin_refills", "Angelcare White Nappy Disposal System", None, None),
    ("sterilising", "Milton Sterilising Fluid 500ml", None, 5),
    ("sterilising", "Milton Sterilising Fluid 1 Litre", None, 10),
    ("sterilising", "Milton Sterilising Fluid 1l", None, 10),
    ("sterilising", "Milton - Sterilizing Fluid - 1 Litre", None, 10),
    ("sterilising", "Milton Sterilising Fluid 200ml", None, 2),
    ("sterilising", "Milton Sterilising Tablets 32's", None, 32),
    ("sterilising", "Milton Sterilising Tablets 8 Pack", None, 8),
    ("sterilising", "Milton Sterilising Tablets 32's (2 Pack)", None, 64),
    ("sterilising", "Milton Sterilising Fluid Antiseptic Liquid", None, None),
]


@pytest.mark.parametrize("category,title,size,units", OTHER_TITLES)
def test_other_categories_read_stage_and_units(category, title, size, units):
    assert parse.describe(title, category) == {"size": size, "units_per_pack": units}


def test_nappies_keep_what_the_adapter_found():
    assert parse.describe("Pampers Premium Care Size 3 Tape Diapers", "nappies") == {}


def test_unit_label_by_category():
    assert parse.unit_label_for("wipes", "x") == "wipe"
    assert parse.unit_label_for("formula", "x") == "bottle"
    assert parse.unit_label_for("sterilising", "Milton Sterilising Fluid 500ml") == "100ml"
    assert parse.unit_label_for("sterilising", "Milton Sterilising Tablets 32's") == "tablet"
