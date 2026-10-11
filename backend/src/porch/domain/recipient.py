"""Match OCR lines from a shipping label to a house resident.

Lines and names are normalised the same way (casefold, digit look-alikes
mapped back to letters inside letter-bearing tokens, remaining non-letters
become spaces, whitespace collapsed) and compared with rapidfuzz
token_set_ratio. Raw OCR text never leaves this module.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from porch.domain.models import RecipientState, Resident

MIN_READABLE_LETTERS = 3
DIGIT_LOOKALIKES = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "6": "g",
    "7": "t",
    "8": "b",
}


@dataclass(frozen=True, slots=True)
class RecipientMatch:
    state: RecipientState
    resident_id: str | None


def match_recipient(
    lines: Sequence[str],
    residents: Sequence[Resident],
    min_score: int,
    margin: int,
) -> RecipientMatch:
    """Best resident above min_score and clear of second best by margin."""
    readable = [_normalise(line) for line in lines if _letter_count(line) >= MIN_READABLE_LETTERS]
    if not readable:
        return RecipientMatch(state="unreadable", resident_id=None)
    scored = sorted(
        ((r, _best_score(readable, r)) for r in residents),
        key=lambda item: item[1],
        reverse=True,
    )
    if not scored:
        return RecipientMatch(state="not_ours", resident_id=None)
    best_resident, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if best_score >= min_score and best_score - second_score >= margin:
        return RecipientMatch(state="matched", resident_id=best_resident.id)
    return RecipientMatch(state="not_ours", resident_id=None)


def _normalise(text: str) -> str:
    tokens = (_normalise_token(token) for token in text.split())
    return " ".join(token for token in tokens if token)


def _normalise_token(token: str) -> str:
    """Digits map to letters only in tokens that already contain a letter."""
    if not any(c.isalpha() for c in token):
        return ""
    mapped = (DIGIT_LOOKALIKES.get(c.casefold(), c.casefold()) for c in token)
    letters = (c if c.isalpha() else " " for c in mapped)
    return " ".join("".join(letters).split())


def _letter_count(text: str) -> int:
    return sum(1 for c in text if c.isalpha())


def _best_score(readable: list[str], resident: Resident) -> float:
    names = [_normalise(resident.display_name), *(_normalise(a) for a in resident.aliases)]
    return max(
        (fuzz.token_set_ratio(line, name) for name in names for line in readable if name),
        default=0.0,
    )
