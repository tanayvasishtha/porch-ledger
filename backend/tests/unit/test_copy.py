from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from porch.domain import (
    BoxFacts,
    CardText,
    House,
    NormBox,
    RainRisk,
    RecipientState,
    Resident,
    Visit,
    VisitKind,
    card_text,
    spoken_inbox,
)

PRIYA = Resident(id="r1", display_name="Priya Shah")
INBOX_RESIDENTS = (
    Resident(id="priya", display_name="Priya Shah"),
    Resident(id="sam", display_name="Sam Okafor"),
    Resident(id="jo", display_name="Jo Lindqvist"),
)
BOX = NormBox(x=0.1, y=0.1, w=0.2, h=0.2)
BANNED = ("stolen", "theft", "thief", "suspicious", "intruder")


def ms(day: int, hour: int, minute: int, tz: str = "Asia/Tokyo") -> int:
    dt = datetime(2026, 1, day, hour, minute, tzinfo=ZoneInfo(tz))
    return round(dt.timestamp() * 1000)


def mkhouse(
    tz: str = "Asia/Tokyo",
    residents: tuple[Resident, ...] = (PRIYA,),
) -> House:
    return House(
        id="h1",
        timezone=tz,
        residents=residents,
        door_polygon=None,
        latitude=35.0,
        longitude=139.0,
    )


def mkvisit(
    kind: VisitKind,
    start_ms: int,
    end_ms: int,
) -> Visit:
    return Visit(
        id="v1",
        house_id="h1",
        device_id="dev-1",
        kind=kind,
        start_ms=start_ms,
        end_ms=end_ms,
        event_ids=("e1",),
        hero_media_key=None,
        clip_media_key=None,
        box=None,
        description=None,
        rain=None,
        provenance="replay",
        trace=(),
        claimed_by=None,
        version=1,
    )


def facts_box(
    state: RecipientState,
    recipient_id: str | None = None,
    blocks_door: bool | None = None,
) -> BoxFacts:
    return BoxFacts(
        box=BOX,
        recipient_id=recipient_id,
        recipient_state=state,
        blocks_door=blocks_door,
        door_overlap=0.4 if blocks_door else None,
    )


@pytest.mark.parametrize(
    ("kind", "title"),
    [
        (VisitKind.DELIVERY, "Delivery"),
        (VisitKind.BOX_GONE, "Box gone"),
        (VisitKind.CAR_STOPPED, "Car stopped"),
        (VisitKind.VISITOR, "Visitor"),
        (VisitKind.CARS_PASSED, "Car passed"),
        (VisitKind.ACTIVITY, "Movement"),
    ],
)
def test_titles(kind: VisitKind, title: str) -> None:
    card = card_text(mkvisit(kind, ms(1, 9, 0), ms(1, 9, 1)), mkhouse())
    assert card.title == title


def test_span_same_minute() -> None:
    card = card_text(mkvisit(VisitKind.VISITOR, ms(1, 14, 14), ms(1, 14, 14)), mkhouse())
    assert card.span == "2:14 pm"


def test_span_same_half_of_day() -> None:
    card = card_text(mkvisit(VisitKind.VISITOR, ms(1, 14, 14), ms(1, 14, 16)), mkhouse())
    assert card.span == "2:14 to 2:16 pm"


def test_span_crossing_noon() -> None:
    card = card_text(mkvisit(VisitKind.VISITOR, ms(1, 11, 58), ms(1, 12, 3)), mkhouse())
    assert card.span == "11:58 am to 12:03 pm"


def test_span_crossing_midnight() -> None:
    card = card_text(mkvisit(VisitKind.VISITOR, ms(1, 23, 58), ms(2, 0, 3)), mkhouse())
    assert card.span == "11:58 pm to 12:03 am"


def test_span_non_utc_timezone() -> None:
    house = mkhouse(tz="America/New_York")
    card = card_text(
        mkvisit(
            VisitKind.VISITOR, ms(1, 9, 14, "America/New_York"), ms(1, 9, 16, "America/New_York")
        ),
        house,
    )
    assert card.span == "9:14 to 9:16 am"


def test_fact_ordering() -> None:
    visit = replace(
        mkvisit(VisitKind.DELIVERY, ms(1, 14, 0), ms(1, 14, 2)),
        box=facts_box("matched", recipient_id="r1", blocks_door=True),
        rain=RainRisk(probability_pct=80, by_local_time="6:30 pm"),
    )
    card = card_text(visit, mkhouse())
    assert card.facts == (
        "Box for Priya Shah",
        "Leaning on the door",
        "Rain likely by 6:30 pm",
    )


def test_unreadable_and_not_ours_facts() -> None:
    unreadable = card_text(
        replace(
            mkvisit(VisitKind.DELIVERY, ms(1, 9, 0), ms(1, 9, 1)),
            box=facts_box("unreadable"),
        ),
        mkhouse(),
    )
    assert unreadable.facts == ("Label not readable",)
    not_ours = card_text(
        replace(
            mkvisit(VisitKind.DELIVERY, ms(1, 9, 0), ms(1, 9, 1)),
            box=facts_box("not_ours"),
        ),
        mkhouse(),
    )
    assert not_ours.facts == ("Not for anyone here",)


def test_car_stopped_fact_and_description() -> None:
    visit = mkvisit(VisitKind.CAR_STOPPED, ms(1, 14, 0), ms(1, 14, 10))
    card = card_text(visit, mkhouse())
    assert card.facts == ("Stopped 10 min",)
    assert card.description == "A car stopped outside for 10 min."


def test_car_stopped_rounds_up_to_one_minute() -> None:
    visit = mkvisit(VisitKind.CAR_STOPPED, ms(1, 14, 0), ms(1, 14, 0) + 30_000)
    card = card_text(visit, mkhouse())
    assert card.facts == ("Stopped 1 min",)


def test_provided_description_wins() -> None:
    visit = replace(
        mkvisit(VisitKind.VISITOR, ms(1, 9, 0), ms(1, 9, 1)),
        description="A courier rang.",
    )
    card = card_text(visit, mkhouse())
    assert card.description == "A courier rang."


def test_fallback_descriptions() -> None:
    expected = {
        VisitKind.DELIVERY: "A box was left at the door.",
        VisitKind.BOX_GONE: "A box that was at the door is gone.",
        VisitKind.VISITOR: "Someone came to the door.",
        VisitKind.CARS_PASSED: "A car drove past.",
        VisitKind.ACTIVITY: "Movement near the door.",
    }
    for kind, text in expected.items():
        card = card_text(mkvisit(kind, ms(1, 9, 0), ms(1, 9, 1)), mkhouse())
        assert card.description == text


def test_no_banned_words_in_any_generated_text() -> None:
    visits = [
        replace(
            mkvisit(kind, ms(1, 9, 0), ms(1, 9, 1)),
            box=facts_box(state, "r1", True),
            rain=RainRisk(probability_pct=60, by_local_time="8 pm"),
        )
        for kind in VisitKind
        for state in ("matched", "unreadable", "not_ours", "not_checked")
    ]
    visits.append(mkvisit(VisitKind.CAR_STOPPED, ms(1, 9, 0), ms(1, 10, 0)))
    house = mkhouse()
    for visit in visits:
        card: CardText = card_text(visit, house)
        blob = " ".join([card.title, card.span, card.description, *card.facts]).casefold()
        for word in BANNED:
            assert word not in blob, f"{word!r} in {blob!r}"


def inbox_visit(recipient_id: str, start_ms: int, claimed_by: str | None = None) -> Visit:
    return replace(
        mkvisit(VisitKind.DELIVERY, start_ms, start_ms + 60_000),
        box=facts_box("matched", recipient_id=recipient_id),
        claimed_by=claimed_by,
    )


def test_inbox_nothing() -> None:
    house = mkhouse(residents=INBOX_RESIDENTS)
    priya = house.residents[0]
    assert spoken_inbox(priya, [], house) == "Nothing for you today."


def test_inbox_only_others() -> None:
    house = mkhouse(residents=INBOX_RESIDENTS)
    priya, _, jo = house.residents
    visits = [inbox_visit("sam", ms(1, 9, 0)), inbox_visit("jo", ms(1, 10, 0))]
    assert spoken_inbox(priya, visits, house) == (
        "Nothing for you today. There are boxes for Sam Okafor and Jo Lindqvist."
    )
    assert spoken_inbox(jo, [inbox_visit("sam", ms(1, 9, 0))], house) == (
        "Nothing for you today. There is a box for Sam Okafor."
    )


def test_inbox_mine() -> None:
    house = mkhouse(residents=INBOX_RESIDENTS)
    priya = house.residents[0]
    one = [inbox_visit("priya", ms(1, 14, 14))]
    assert spoken_inbox(priya, one, house) == ("You have a box at the door, left at 2:14 pm.")
    two = [inbox_visit("priya", ms(1, 14, 14)), inbox_visit("priya", ms(1, 16, 5))]
    assert spoken_inbox(priya, two, house) == "You have 2 boxes, the last left at 4:05 pm."


def test_inbox_mine_blocking() -> None:
    house = mkhouse(residents=INBOX_RESIDENTS)
    priya = house.residents[0]
    blocking = replace(
        inbox_visit("priya", ms(1, 14, 14)),
        box=facts_box("matched", recipient_id="priya", blocks_door=True),
    )
    assert spoken_inbox(priya, [blocking], house) == (
        "You have a box at the door, left at 2:14 pm. It's leaning on the door."
    )


def test_inbox_claimed_boxes_do_not_count() -> None:
    house = mkhouse(residents=INBOX_RESIDENTS)
    priya = house.residents[0]
    visits = [
        inbox_visit("priya", ms(1, 9, 0), claimed_by="sam"),
        inbox_visit("sam", ms(1, 10, 0), claimed_by="sam"),
    ]
    assert spoken_inbox(priya, visits, house) == "Nothing for you today."
    mine_claimed = [inbox_visit("priya", ms(1, 9, 0), claimed_by="priya")]
    assert spoken_inbox(priya, mine_claimed, house) == (
        "You have a box at the door, left at 9:00 am."
    )
