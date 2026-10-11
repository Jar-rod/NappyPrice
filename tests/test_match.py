from scraper.match import PRETICK_SCORE, score, with_category

TARGET = {"title": "Pampers Premium Care Nappies Size 2 76's", "brand": "Pampers",
          "range_name": "Premium Care", "size": "2", "units_per_pack": 76}


def cand(title, **fields):
    return {"title": title, "brand": "Pampers", "range_name": "Premium Care", "size": "2",
            "units_per_pack": 76} | fields


def test_same_product_at_another_store_is_preticked():
    assert score(TARGET, cand("Pampers Premium Care Size 2 Value Pack - 76's")) >= PRETICK_SCORE


def test_different_pack_size_is_shown_but_not_preticked():
    value = score(TARGET, cand("Pampers Premium Care Set Size 2 Value Pack 2x76", units_per_pack=152))
    assert 60 <= value < PRETICK_SCORE


def test_wrong_size_range_or_brand_score_low():
    wrong_size = score(TARGET, cand("Pampers Premium Care Size 3 Value Pack - 60's", size="3", units_per_pack=60))
    wrong_range = score(TARGET, cand("Pampers Active Baby Size 2 Jumbo Pack 76", range_name="Active Baby"))
    wrong_brand = score(TARGET, cand("Huggies Extra Care Size 2 76s", brand="Huggies", range_name="Extra Care"))
    assert wrong_size < PRETICK_SCORE and wrong_range < PRETICK_SCORE and wrong_brand < 60


def test_pants_never_match_taped_nappies():
    assert score(TARGET, cand("Pampers Premium Care Pants Size 2 76", range_name="Premium Care Pants")) < PRETICK_SCORE


def test_brand_match_ignores_case():
    assert score(TARGET, cand("PAMPERS PREMIUM CARE SIZE 2 76", brand="PAMPERS")) >= PRETICK_SCORE


def test_refill_without_size_or_range_is_judged_on_brand_pack_and_title():
    target = {"title": "Angelcare Nappy Bin Refill Cassettes 3 Pack", "brand": "Angelcare", "units_per_pack": 3}
    same = {"title": "Angelcare Nappy Bin Refill Cassette - 3 Pack", "brand": "Angelcare", "units_per_pack": 3}
    bin_itself = {"title": "Angelcare Nappy Disposal Bin", "brand": "Angelcare", "units_per_pack": None}
    assert score(target, same) >= PRETICK_SCORE
    assert score(target, bin_itself) < PRETICK_SCORE


def test_compatible_refill_is_never_the_genuine_product():
    target = {"title": "Angelcare Nappy Bin Refill Cassettes 3 Pack", "brand": "Angelcare", "units_per_pack": 3}
    compatible = {"title": "Angelcare Compatible Nappy Bin Refill Cassettes 3 Pack", "brand": "Angelcare", "units_per_pack": 3}
    assert score(target, compatible) <= 50


def formula(title):
    return with_category({"title": title, "brand": "Alula", "range_name": "Gold"}, "formula")


RTF_6 = formula("Alula Gold Stage 1 0-6 Months Ready to Feed Infant Starter Formula 6 x 200ml")


def test_formula_same_six_pack_named_differently_matches():
    assert score(RTF_6, formula("Alula Gold No.1 Ready To Feed Formula 6 x 200ml")) >= PRETICK_SCORE


def test_formula_single_bottle_is_offered_but_not_preticked():
    assert 60 <= score(RTF_6, formula("Alula Gold 1 Rtf 200ml")) < PRETICK_SCORE


def test_formula_other_stage_or_powder_is_not_a_match():
    assert score(RTF_6, formula("Alula Gold Stage 2 6-12 Months Ready to Feed Follow-On Formula 6 x 200ml")) < PRETICK_SCORE
    assert score(RTF_6, formula("Alula Gold 1 900g Tin")) <= 50


def test_milton_tablets_fluid_spray_and_steriliser_are_different_products():
    def milton(title):
        return with_category({"title": title, "brand": "Milton"}, "sterilising")

    fluid = milton("Milton Sterilising Fluid 500ml")
    assert score(fluid, milton("Milton - Sterilizing Fluid - 500ml")) >= PRETICK_SCORE
    assert score(fluid, milton("Milton Sterilising Fluid 1 Litre")) < PRETICK_SCORE      # other size: offered, unticked
    for other in ("Milton Sterilising Tablets 32's", "Milton Sterilising Surface Trigger Spray 500ml",
                  "Milton Sterilising Unit", "Milton Liquid Handwash 300ml"):
        assert score(fluid, milton(other)) <= 50, other


def test_wipes_range_matters():
    def wipes(title, range_name):
        return with_category({"title": title, "brand": "Pampers", "range_name": range_name}, "wipes")

    target = wipes("Pampers Baby Wipes Sensitive 4's - 4x56", "Sensitive")
    assert score(target, wipes("Pampers Sensitive Wet Wipes 224 (4x56) Baby Wipes", "Sensitive")) >= PRETICK_SCORE
    assert score(target, wipes("Pampers Complete Clean Baby Wipes 4 x 64 Pack", "Complete Clean")) < PRETICK_SCORE


def test_nappy_bags_are_not_bin_refill_cartridges():
    target = with_category({"title": "Angelcare Nappy Bin 3 Pack Refill", "brand": "Angelcare"}, "bin_refills")
    bags = with_category({"title": "Angelcare Knot A Bag Nappy Bag Refill 3 Pack", "brand": "Angelcare"}, "bin_refills")
    same = with_category({"title": "Angelcare 3pk Bin Refills", "brand": "Angelcare"}, "bin_refills")
    assert score(target, bags) <= 50
    assert score(target, same) >= PRETICK_SCORE
