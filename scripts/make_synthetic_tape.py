# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow"]
# ///
"""Generate fixtures/tapes/synthetic-day: a flat doorstep illustration.

Every frame carries a SYNTHETIC TEST FRAME caption so it can never be
mistaken for real footage. Detections in tape.json are pre-annotated and
match the shapes drawn.
"""

import json
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
WALL = (226, 222, 215)
FLOOR = (196, 190, 182)
DOOR = (140, 96, 60)
DOOR_FRAME = (96, 66, 40)
KNOB = (60, 50, 40)
VAN = (110, 128, 148)
VAN_WINDOW = (200, 215, 228)
BOX = (172, 128, 72)
LABEL = (250, 250, 250)
PERSON = (58, 58, 66)
CAPTION = (110, 105, 100)
NAME_INK = (40, 40, 45)

DOOR_POLY = [[0.05, 0.35], [0.38, 0.35], [0.38, 0.98], [0.05, 0.98]]
DAY = datetime(2026, 6, 1, tzinfo=ZoneInfo("America/Los_Angeles"))

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "tapes" / "synthetic-day"
JPEG_KWARGS = {"quality": 85}


def at(hour: int, minute: int, second: int = 0) -> int:
    return int(DAY.replace(hour=hour, minute=minute, second=second).timestamp() * 1000)


def px(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x, y, w, h = box
    return (int(x * W), int(y * H), int((x + w) * W), int((y + h) * H))


def det(label: str, box: tuple[float, float, float, float], conf: float = 0.93) -> dict:
    return {
        "label": label,
        "confidence": conf,
        "box": {"x": box[0], "y": box[1], "w": box[2], "h": box[3]},
    }


def font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def base_scene() -> Image.Image:
    img = Image.new("RGB", (W, H), WALL)
    d = ImageDraw.Draw(img)
    d.rectangle((0, int(0.88 * H), W, H), fill=FLOOR)
    x0, y0 = int(DOOR_POLY[0][0] * W), int(DOOR_POLY[0][1] * H)
    x1, y1 = int(DOOR_POLY[1][0] * W), int(DOOR_POLY[1][1] * H)
    d.rectangle((x0 - 6, y0 - 6, x1 + 6, y1), fill=DOOR_FRAME)
    d.rectangle((x0, y0, x1, y1), fill=DOOR)
    d.ellipse((x1 - 60, (y0 + y1) // 2 - 8, x1 - 44, (y0 + y1) // 2 + 8), fill=KNOB)
    d.text((12, H - 26), "SYNTHETIC TEST FRAME", fill=CAPTION, font=font(16))
    return img


def draw_van(d: ImageDraw.ImageDraw, box: tuple[float, float, float, float]) -> None:
    x0, y0, x1, y1 = px(box)
    d.rounded_rectangle((x0, y0, x1, y1), radius=14, fill=VAN)
    d.rectangle((x0 + 16, y0 + 14, x0 + 70, y0 + 44), fill=VAN_WINDOW)


def draw_box(d: ImageDraw.ImageDraw, box: tuple[float, float, float, float], name: str) -> None:
    x0, y0, x1, y1 = px(box)
    d.rectangle((x0, y0, x1, y1), fill=BOX)
    d.rectangle((x0 + 12, y0 + 12, x1 - 12, y0 + (y1 - y0) // 2), fill=LABEL)
    d.text((x0 + 18, y0 + 16), name, fill=NAME_INK, font=font(20))


def draw_person(d: ImageDraw.ImageDraw, box: tuple[float, float, float, float]) -> None:
    x0, y0, x1, y1 = px(box)
    head_r = (x1 - x0) // 4
    d.ellipse(((x0 + x1) // 2 - head_r, y0, (x0 + x1) // 2 + head_r, y0 + 2 * head_r), fill=PERSON)
    d.rounded_rectangle(
        (x0 + head_r // 2, y0 + 2 * head_r, x1 - head_r // 2, y1), radius=18, fill=PERSON
    )


def shot(event: str, offset_ms: int, file: str, draw, detections: list[dict] | None) -> dict:
    return {
        "event": event,
        "offset_ms": offset_ms,
        "file": file,
        "draw": draw,
        "detections": detections,
    }


def van_shots(event: str, xs: list[float], step_ms: int) -> list[dict]:
    out = []
    for i, x in enumerate(xs):
        box = (x, 0.60, 0.16, 0.12)
        out.append(
            shot(
                event,
                i * step_ms,
                f"{event}-{i}.jpg",
                lambda d, b=box: draw_van(d, b),
                [det("vehicle", box)],
            )
        )
    return out


def box_shots(
    event: str, box: tuple[float, float, float, float], name: str, n: int = 3
) -> list[dict]:
    return [
        shot(
            event,
            i * 5000,
            f"{event}-{i}.jpg",
            lambda d, b=box, t=name: draw_box(d, b, t),
            [det("box", box)],
        )
        for i in range(n)
    ]


def build() -> dict:
    events = [
        {
            "id": "car1",
            "kind": "motion",
            "sub_type": None,
            "start_ms": at(8, 12),
            "end_ms": at(8, 12, 10),
        },
        {
            "id": "car2",
            "kind": "motion",
            "sub_type": None,
            "start_ms": at(9, 40),
            "end_ms": at(9, 40, 10),
        },
        {
            "id": "van1",
            "kind": "motion",
            "sub_type": None,
            "start_ms": at(11, 5),
            "end_ms": at(11, 5, 20),
        },
        {
            "id": "del1",
            "kind": "on_demand",
            "sub_type": None,
            "start_ms": at(11, 6, 30),
            "end_ms": at(11, 6, 45),
        },
        {
            "id": "ring1",
            "kind": "ding",
            "sub_type": "press",
            "start_ms": at(13, 30),
            "end_ms": at(13, 30, 5),
        },
        {
            "id": "del2",
            "kind": "on_demand",
            "sub_type": None,
            "start_ms": at(15, 20),
            "end_ms": at(15, 20, 15),
        },
        {
            "id": "car3",
            "kind": "motion",
            "sub_type": None,
            "start_ms": at(17, 45),
            "end_ms": at(17, 51),
        },
        {
            "id": "gone1",
            "kind": "motion",
            "sub_type": None,
            "start_ms": at(19, 10),
            "end_ms": at(19, 10, 5),
        },
    ]
    priya_box = (0.60, 0.70, 0.12, 0.18)
    jo_box = (0.10, 0.62, 0.16, 0.20)
    person_box = (0.52, 0.40, 0.10, 0.34)
    shots = [
        *van_shots("car1", [0.60, 0.78], 5000),
        *van_shots("car2", [0.55, 0.75], 5000),
        *van_shots("van1", [0.68, 0.68, 0.68], 10000),
        *box_shots("del1", priya_box, "PRIYA SHAH"),
        # The porch boxes stay in frame while they are still on the porch;
        # an event whose final view lacks a tracked box reads as box_gone.
        shot(
            "ring1",
            0,
            "ring1-0.jpg",
            lambda d: (draw_person(d, person_box), draw_box(d, priya_box, "PRIYA SHAH")),
            [det("person", person_box), det("box", priya_box)],
        ),
        # Jo's box lands in the door swing while Priya's still waits;
        # del2's final view must show both so Priya's is not read as gone.
        *[
            shot(
                "del2",
                i * 5000,
                f"del2-{i}.jpg",
                lambda d: (
                    draw_box(d, priya_box, "PRIYA SHAH"),
                    draw_box(d, jo_box, "JO LINDQVIST"),
                ),
                [det("box", priya_box), det("box", jo_box)],
            )
            for i in range(3)
        ],
        *[
            shot(
                "car3",
                i * 180000,
                f"car3-{i}.jpg",
                lambda d, vb=(0.70, 0.60, 0.16, 0.12): (
                    draw_van(d, vb),
                    draw_box(d, priya_box, "PRIYA SHAH"),
                    draw_box(d, jo_box, "JO LINDQVIST"),
                ),
                [
                    det("vehicle", (0.70, 0.60, 0.16, 0.12)),
                    det("box", priya_box),
                    det("box", jo_box),
                ],
            )
            for i in range(3)
        ],
        *[
            shot(
                "gone1",
                i * 2500,
                f"gone1-{i}.jpg",
                lambda d: draw_box(d, jo_box, "JO LINDQVIST"),
                [det("box", jo_box)],
            )
            for i in range(2)
        ],
    ]
    snapshots = []
    event_start = {e["id"]: e["start_ms"] for e in events}
    for s in shots:
        snapshots.append(
            {
                "event_id": s["event"],
                "at_ms": event_start[s["event"]] + s["offset_ms"],
                "file": s["file"],
                "detections": s["detections"],
            }
        )
    return {"events": events, "shots": shots, "snapshots": snapshots}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tape = build()
    for s in tape["shots"]:
        img = base_scene()
        s["draw"](ImageDraw.Draw(img))
        img.save(OUT / s["file"], format="JPEG", **JPEG_KWARGS)
    tape_json = {
        "format": 1,
        "device_id": "synthetic-door-1",
        "provenance": "replay",
        "events": tape["events"],
        "snapshots": tape["snapshots"],
        "clips": [],
        "label_texts": {
            "del1": "PRIYA SHAH",
            "del2": "JO LINDQVIST",
            "gone1": "PRIYA SHAH",
        },
    }
    (OUT / "tape.json").write_text(json.dumps(tape_json, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(tape['shots'])} frames + tape.json to {OUT}")


if __name__ == "__main__":
    main()
