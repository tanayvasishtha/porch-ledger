from porch.domain import Resident, match_recipient

PRIYA = Resident(id="r1", display_name="Priya Shah", aliases=("P. Shah", "Priya"))
TOM = Resident(id="r2", display_name="Tom Brandt")
MIN_SCORE = 85
MARGIN = 10


def test_exact_match() -> None:
    res = match_recipient(["PRIYA SHAH", "1ST FLOOR"], [PRIYA, TOM], MIN_SCORE, MARGIN)
    assert res.state == "matched"
    assert res.resident_id == "r1"


def test_alias_match() -> None:
    res = match_recipient(["P SHAH RESIDENT"], [PRIYA, TOM], 60, MARGIN)
    assert res.state == "matched"
    assert res.resident_id == "r1"


def test_noisy_ocr_line_still_matches() -> None:
    res = match_recipient(["T0: PR1YA SHAH 42"], [PRIYA, TOM], MIN_SCORE, MARGIN)
    assert res.state == "matched"
    assert res.resident_id == "r1"


def test_digits_only_tokens_contribute_nothing() -> None:
    res = match_recipient(["PRIYA SHAH 4242"], [PRIYA, TOM], MIN_SCORE, MARGIN)
    assert res.state == "matched"
    assert res.resident_id == "r1"
    assert match_recipient(["4242"], [PRIYA], MIN_SCORE, MARGIN).state == "unreadable"


def test_two_similar_names_below_margin_is_not_ours() -> None:
    twin = Resident(id="r3", display_name="Priya Shahh")
    res = match_recipient(["PRIYA SHAH"], [PRIYA, twin], MIN_SCORE, MARGIN)
    assert res.state == "not_ours"
    assert res.resident_id is None


def test_digits_and_punctuation_are_unreadable() -> None:
    res = match_recipient(["420-17", "***", "!!"], [PRIYA], MIN_SCORE, MARGIN)
    assert res.state == "unreadable"


def test_empty_lines_are_unreadable() -> None:
    res = match_recipient([], [PRIYA], MIN_SCORE, MARGIN)
    assert res.state == "unreadable"


def test_single_resident_margin_satisfied() -> None:
    res = match_recipient(["TOM BRANDT"], [TOM], MIN_SCORE, MARGIN)
    assert res.state == "matched"
    assert res.resident_id == "r2"


def test_low_score_is_not_ours() -> None:
    res = match_recipient(["JAMIE COOK"], [PRIYA, TOM], MIN_SCORE, MARGIN)
    assert res.state == "not_ours"


def test_no_residents_is_not_ours() -> None:
    res = match_recipient(["PRIYA SHAH"], [], MIN_SCORE, MARGIN)
    assert res.state == "not_ours"
