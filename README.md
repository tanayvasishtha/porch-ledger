# Porch Ledger

Porch Ledger turns Ring doorbell events into visits you can read on your TV: deliveries, cars that stopped, and whose box is at the door.

Built for the Ring and Fire TV tracks of Build, Ship, Shape: Amazon Developer Hackathon.

## The problem

A doorbell camera reports events, and people care about visits. A van pulls up, the driver drops a box and leaves. The camera often catches the van and, separately, the box, but never the driver, so no package alert fires. In a shared house the next question is whose box it is, and whether it is blocking a door that opens outwards. Meanwhile every passing car is another notification.

## What it does

- **Joins events into visits.** A vehicle event followed by a box appearing becomes one delivery, even when no person was ever on camera.
- **Separates a car that stopped from one that drove past.** Passing cars fold into one quiet line instead of one alert each.
- **Reads whose box it is.** OCR on the label is matched against the household's residents; the label text itself is never stored.
- **Warns when a box is leaning on the door,** using the door's swing area marked once for the camera.
- **Adds the rain forecast** when a box is outside.
- **Describes the whole clip** in one sentence with Amazon Nova.
- **Shows the day on Fire TV** as calm cards you move through with the remote, and answers "anything for me today?" per housemate on an Echo-style screen over MCP.

## Results

From `backend/src/porch/evals/stitching.py` on 50 seeded synthetic days (1,200 scripted scenarios per noise level), compared with a per-event notifier that alerts on every event with a detection. Full output: [`docs/eval/stitching.json`](docs/eval/stitching.json).

| Detection noise | Scenarios classified correctly | Alerts from a per-event notifier | Cards Porch Ledger shows | Fewer interruptions |
|---|---|---|---|---|
| None | 100.0% | 1,617 | 610 | 62.3% |
| Moderate (15% missed box frames, 5% false boxes) | 93.8% | 1,642 | 630 | 61.6% |
| Harsh (30% missed box frames, 12% false boxes) | 77.2% | 1,637 | 690 | 57.9% |

These scenarios are written by us to test the engine's logic under controlled noise. They are not a field accuracy figure. Under harsh noise, delivery precision drops to 48% because a box detected late is credited to a later visit; that limitation is listed below.

## How it works

```
Ring event history -> snapshots + clip -> Rekognition labels -> VisitEngine -> PorchClerk agent -> DynamoDB -> REST (TV) and MCP (iPad)
```

- **VisitEngine** (`backend/src/porch/domain/engine.py`) is a pure function. It groups events less than two minutes apart, tracks boxes on the porch across snapshots by IoU, and classifies each visit. Property tests check that it is idempotent, independent of input order, and gives the same answer run incrementally or in one batch.
- **PorchClerk** is a Strands agent on Amazon Bedrock that decides which tools a visit needs: read the label (Textract), check the door (geometry), check the rain (Open-Meteo), describe the clip (Nova). Every tool is timed into a trace shown on the TV under "How this card was made". If the agent fails, the same steps run deterministically.
- **Fire TV app** (`tv/`): Kotlin and Compose for TV, 3 MB release build, polls with ETags so an unchanged day costs a 304.
- **Echo-style client** (`echo/`): a Preact web app on an iPad that is a real MCP client (protocol 2025-11-25) and speaks answers with Amazon Polly.
- **AWS** (`infra/template.yaml`): API and worker Lambdas, HTTP API, DynamoDB, private S3, EventBridge Scheduler, SSM for secrets, CloudFront for the iPad app, a $5 budget alarm, least-privilege IAM per function.

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), JDK 17 and the Android SDK for the TV app, Node 22+ with pnpm for the iPad client. No AWS account or Ring token is needed for the demo.

```
just demo
```

builds a synthetic household day through the full pipeline (stitching, label matching, door check, rain) with recorded and fake services, then serves the API and MCP server on `http://localhost:8000`. Every demo frame is stamped "SYNTHETIC TEST FRAME".

- **TV app:** start an Android TV emulator (API 30), then `cd tv && ./gradlew installDebug`. The debug build talks to `http://10.0.2.2:8000`, which is the host machine from the emulator.
- **iPad client:** `cd echo && pnpm install && pnpm dev`, and start the demo server with `PORCH_API__CORS_ORIGINS='["http://localhost:5173"]'` so the browser may call it.
- **All checks:** `just check` runs the prose check, backend lint, types and tests, the TV lint, unit and screenshot tests and release build, and the iPad client's checks.

## Limitations

- **Late box detection is credited to the wrong visit.** If the box is missed in the delivery's own snapshots and first seen during a later visit, that later visit becomes the delivery.
- **Simulated Ring events carry no classification.** The Playground reports every scene as a live view session, so detection is ours (Rekognition), and Ring's own person and vehicle signal is only used on real devices.
- **TAKE and end-to-end encryption** can limit what media a partner app may fetch. See [docs/PRIVACY.md](docs/PRIVACY.md).
- **Alexa+ itself is not connected;** its developer tools are in private preview. The iPad client is a simulated Alexa+ screen using the same MCP server.

## What broke and how we fixed it

The first run of the stitching evaluation scored 76% on clean data. Every box picked up during a single event was missed, because the engine checked whether the box appeared anywhere in the last event instead of in its final frame. The stale box then caused false "box gone" cards later in the day. The rule now looks at the final snapshot and requires either a person in the visit or absence across the last two frames; clean accuracy went to 100%.

## Repository

- `backend/` Python package `porch`: domain, adapters, pipeline, API, MCP server, evaluations.
- `tv/` Fire TV app. `echo/` iPad client. `infra/` SAM template. `contracts/` generated API and MCP schemas.
- `docs/` architecture, privacy, product feedback, friction log, evaluation output.

## License

MIT. Fonts are under the SIL Open Font License; their texts ship next to the font files.
