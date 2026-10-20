# Porch Ledger

Porch Ledger turns Ring doorbell events into visits you can read on your TV: deliveries, cars that stopped, and whose box is at the door.

Built for the Ring and Fire TV tracks of Build, Ship, Shape: Amazon Developer Hackathon, with entries in the AWS Builder and Open Source mini challenges.

| Track | What in this repo answers it |
|---|---|
| Ring | `backend/src/porch/adapters/ring/` calls the Ring Partner API at runtime (devices, event history, snapshots, clips) against the Developer Playground. The use is package management for shared homes, one of the rules' examples of a creative non-security use. Events drive app behaviour: they become visits, cards and spoken answers. |
| Fire TV | `tv/` is a Kotlin and Compose for TV app for Fire OS, driven by the D-pad, shown running on the Android TV emulator in the video. |
| AWS Builder | `infra/template.yaml` deploys Lambda, HTTP API, DynamoDB, S3, SSM, EventBridge Scheduler and CloudFront. Two Strands agents run on Amazon Bedrock (Nova Lite): PorchClerk picks the enrichment steps per visit, and HouseholdAsk answers free questions over MCP. Rekognition and Polly handle vision and speech. |
| Open Source | [AmazonAppDev/ring-api-helloworld pull request 42](https://github.com/AmazonAppDev/ring-api-helloworld/pull/42): a tested Python media download example covering the 303, 206, 416/425, 429 and 422 cases we hit live. |

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

### Live runs against the Ring Playground

- **October 12, local recorder** (`python -m porch record`): 3 events, 8 snapshots and 3 clips downloaded through the Partner API. The run exposed the clip 303 redirect, a per-frame 422 and a Windows TLS issue; all three are fixed and tested.
- **October 20, deployed worker on AWS:** the Lambda pulled 4 new events and 11 snapshots, ran Rekognition on every frame (it found the package as `Package` and `Box`), stored media in S3 and visits in DynamoDB, and Nova described the vehicle clip as "A car arrives, a person gets out, and the car leaves."
- **HouseholdAsk on Bedrock,** called over the deployed MCP endpoint, answered "Did anyone come to the door today?" in 4.6 seconds and cited the visit it read.

Ring's sample footage stays out of this repository because it is not ours to redistribute. Cards on the TV say where their footage came from: "From the Ring doorbell", "Synthetic test day", or an own-footage badge.

## How it works

```
Ring event history -> snapshots + clip -> Rekognition labels -> VisitEngine -> PorchClerk agent -> DynamoDB -> REST (TV) and MCP (iPad)
```

- **VisitEngine** (`backend/src/porch/domain/engine.py`) is a pure function. It groups events less than two minutes apart, tracks boxes on the porch across snapshots by IoU, and classifies each visit. Property tests check that it is idempotent, independent of input order, and gives the same answer run incrementally or in one batch.
- **PorchClerk** is a Strands agent on Amazon Bedrock that decides which tools a visit needs: read the label (Rekognition DetectText), check the door (geometry), check the rain (Open-Meteo), describe the clip (Nova). Every tool is timed into a trace shown on the TV under "How this card was made". If the agent fails, the same steps run deterministically.
- **Fire TV app** (`tv/`): Kotlin and Compose for TV, 3 MB release build, polls with ETags so an unchanged day costs a 304.
- **Echo-style client** (`echo/`): a Preact web app on an iPad that is a real MCP client (protocol 2025-11-25) and speaks answers with Amazon Polly.
- **HouseholdAsk** (`backend/src/porch/pipeline/ask.py`) is a second Strands agent behind the MCP `ask` tool. It reads saved visits through two read-only tools and may only cite visit ids those tools returned.
- **AWS** (`infra/template.yaml`): API and worker Lambdas, HTTP API, DynamoDB, private S3, EventBridge Scheduler, SSM for secrets, CloudFront for the iPad app, a $5 budget alarm, least-privilege IAM per function. The stack runs in ap-southeast-2 (the account's home region) and calls Bedrock in us-east-1; [friction log entries 16 to 18](docs/FRICTION_LOG.md) explain why.

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), JDK 17 and the Android SDK for the TV app (with `ANDROID_HOME` set, or `sdk.dir` in `tv/local.properties`), Node 22+ with pnpm for the iPad client. No AWS account or Ring token is needed for the demo.

```
just demo
```

builds a synthetic household day through the full pipeline (stitching, label matching, door check, rain) with recorded and fake services, then serves the API and MCP server on `http://localhost:8000`. Every demo frame is stamped "SYNTHETIC TEST FRAME".

- **TV app:** start an Android TV emulator (API 30), then `cd tv && ./gradlew installDebug` (`.\gradlew.bat installDebug` in PowerShell). The debug build talks to `http://10.0.2.2:8000`, which is the host machine from the emulator.
- **iPad client:** allow the browser origin when starting the demo server, then run the client:

  ```
  # bash or zsh
  PORCH_API__CORS_ORIGINS='["http://localhost:5173"]' just demo
  # PowerShell
  $env:PORCH_API__CORS_ORIGINS='["http://localhost:5173"]'; just demo
  ```

  then `cd echo && pnpm install && pnpm dev` and open `http://localhost:5173`.
- **Deploy to AWS** (needs credentials; copy `infra/samconfig.toml.example` to `infra/samconfig.toml` first): `just deploy`, then `just house-key` (prints the house key once and stores only its hash), `just ring-token` (stores a Playground token in SSM without echoing it) and `just echo-deploy`. Open the iPad client once as `<EchoUrl>/#key=<house key>`; the key moves to the browser's storage and never ships in the public bundle. Build the TV app against the stack with `./gradlew installDebug -PporchApiBaseUrl=<ApiUrl> -PporchHouseKey=<house key>`.
- **All checks:** `just check` runs the prose check, backend lint, types and tests, the TV lint, unit and screenshot tests and release build, and the iPad client's checks.

## Limitations

- **Late box detection is credited to the wrong visit.** If the box is missed in the delivery's own snapshots and first seen during a later visit, that later visit becomes the delivery.
- **Simulated Ring events carry no classification.** The Playground reports every scene as a live view session, so detection is ours (Rekognition), and Ring's own person and vehicle signal is only used on real devices.
- **Playground scenes come from different cameras.** Clicking scenes less than two minutes apart merges them into one visit, and the box seems to leave when the next camera's scene starts. We stage scenes with a gap.
- **No field accuracy number for label reading and the door check yet.** The evaluation script (`backend/src/porch/evals/footage.py`) is written and tested; it needs our own labelled photos.
- **TAKE and end-to-end encryption** can limit what media a partner app may fetch. See [docs/PRIVACY.md](docs/PRIVACY.md).
- **Alexa+ itself is not connected;** its developer tools are in private preview. The iPad client is a simulated Alexa+ screen using the same MCP server.

## What broke and how we fixed it

The first run of the stitching evaluation scored 76% on clean data. Every box picked up during a single event was missed, because the engine checked whether the box appeared anywhere in the last event instead of in its final frame. The stale box then caused false "box gone" cards later in the day. The rule now looks at the final snapshot and requires either a person in the visit or absence across the last two frames; clean accuracy went to 100%.

The first deploy found four bugs that no local test could: the API's start script picked a Windows-only `uvicorn` shim, a stub package the adapters import at runtime was a dev dependency, DynamoDB rejected a two-sided condition on the sort key (our fake client accepted it), and S3 returned 403 instead of 404 for missing media without `ListBucket`. Each fix has a test or a template rule now.

## Repository

- `backend/` Python package `porch`: domain, adapters, pipeline, API, MCP server, evaluations.
- `tv/` Fire TV app. `echo/` iPad client. `infra/` SAM template. `contracts/` generated API and MCP schemas.
- `docs/` architecture, privacy, product feedback, friction log, evaluation output.

## License

MIT. Fonts are under the SIL Open Font License; their texts ship next to the font files.
