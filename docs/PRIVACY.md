# Privacy

Porch Ledger watches a front door, so it handles images of the street, of visitors and of shipping labels. These are the rules the code follows.

## What it never does

- **No face recognition.** Rekognition labels are mapped to three classes: vehicle, person and box. There is no face search, no face index and no identity of any kind.
- **No stored label text.** The label reader runs OCR on a crop of the box, matches the text against the household's own residents, and keeps only the result: a resident id, "not readable" or "not for anyone here". The OCR text itself is discarded in `porch/domain/recipient.py` and never reaches the database, the logs or the API.
- **No accusations.** Card wording is fixed in `porch/domain/copy.py`. A box that disappears is "Box gone". The clip describer rejects any answer that contains words like stolen or suspicious, and falls back to the fixed sentence.

## What it stores, and for how long

| Data | Where | Retention |
|---|---|---|
| Snapshots and clips | S3, private bucket, SSE-S3, public access blocked | 14 days (bucket lifecycle rule) |
| Door events | DynamoDB, per-device state item | only until they are stitched into a visit; a visit keeps the event ids, not the events |
| Visits (kind, times, matched resident, door and rain facts, tool trace) | DynamoDB | until the household deletes them |
| Ring access token, webhook secret, house key hash | SSM Parameter Store, SecureString for secrets | until rotated |

Media is only reachable through pre-signed URLs that expire after 10 minutes. The house key is stored as a SHA-256 hash and compared in constant time.

## Our footage in the demo

The demo uses Ring Developer Playground recordings and footage we filmed ourselves. Our own footage shows a doorstep and boxes with invented names, no faces and no real addresses, and every card built from it carries the tag "Our footage, not Ring". The synthetic test day is drawn by a script and stamped "SYNTHETIC TEST FRAME".

## Ring encryption (TAKE and E2EE)

Ring is rolling out TAKE encryption as the default. Amazon's developer news says it "narrows what your integrations can access", and the public material does not yet say which Partner API media endpoints stay available to an installed Appstore app. Porch Ledger degrades in a defined way: if snapshots or clips are not available for an event, the visit is still built from the event itself, the card says less, and nothing is guessed. Accounts with end-to-end encryption turned on do not share media with any partner app, and Porch Ledger does not try to work around that.
