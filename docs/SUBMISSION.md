# Devpost submission

Field by field, as submitted. Numbers come from the scripts and run logs cited in the README.

## Project name

Porch Ledger

## Elevator pitch

Ring doorbell events become visits a shared house can read on Fire TV: deliveries, cars that stopped, and whose box is at the door.

## What it does

A doorbell camera reports events, and people care about visits. When a van pulls up and the driver drops a box, the camera often catches the van and then the box, but never the driver, so no package alert fires. In a shared house the next questions are whose box it is and whether it is blocking a door that opens outwards. Meanwhile every passing car is another notification.

Porch Ledger polls the Ring Partner API, joins events into visits, and shows the day on Fire TV as one calm card per visit:

- a vehicle followed by a box becomes one delivery, even with no person on camera
- a car that stopped is told apart from cars that drove past, which fold into one line
- the label is read and matched to the residents, and the label text is thrown away
- a box in the door's swing area gets a warning, and a rain forecast is added while it sits outside
- Amazon Nova describes the whole clip in one sentence

On an iPad styled as an Alexa+ screen, each housemate asks "anything for me?", asks free questions that an agent answers from the saved visits, and claims a box with "It's mine". The TV shows the claim within five seconds.

## How we built it

- **Ring:** a typed client for devices, event history, snapshots and clips, tested against the Developer Playground. It follows the media 303 redirect without leaking the bearer token and skips single frames Ring cannot decrypt.
- **Visit engine:** a pure Python function that groups events under two minutes apart, tracks boxes by IoU across snapshots and classifies each visit. Property tests check it is idempotent, order independent and gives the same answer incrementally or in one batch.
- **Agents:** two Strands agents on Amazon Bedrock with Nova Lite. PorchClerk picks the checks a visit needs (label, door, rain, clip description) and every step is timed into a trace shown on the TV. HouseholdAsk answers questions over MCP and may only cite visits its tools returned. If an agent fails, the same steps run as plain code.
- **AWS:** one SAM template with API and worker Lambdas, HTTP API, DynamoDB, private S3, SSM, EventBridge Scheduler and CloudFront. Rekognition finds vehicles, people and boxes and reads labels; Polly speaks answers.
- **Fire TV:** Kotlin and Compose for TV, a 3 MB release build that polls with ETags, so an unchanged day costs a 304.
- **iPad:** a Preact MCP client at protocol 2025-11-25.
- **No keys needed to try it:** every external call can be recorded and replayed, so `just demo` runs the full pipeline offline on a synthetic day.

## Challenges

- The Ring clip endpoint answered 303 where the docs show 200 or 206, and one frame returned an undocumented 422. Both are handled, tested and contributed upstream.
- Our AWS account turned out to be a Free plan project whose managed policies allow services in one home region only, and the plan excludes Textract. We moved the stack to that region, pinned Bedrock to us-east-1 and switched label reading to Rekognition DetectText.
- The first evaluation run scored 76% on clean data and exposed an engine bug: boxes picked up within a single event were missed. The fix took clean accuracy to 100%.

## Accomplishments

- A live end-to-end run: Ring Playground events, a Lambda worker, Rekognition and Nova, DynamoDB, the Bedrock agent over MCP and the iPad answer, all on the deployed stack.
- On 50 scripted days (1,200 scenarios per noise level), 62% fewer interruptions than alerting on every event, and 93.8% of scenarios classified correctly under moderate detection noise. These are our scripted scenarios, not a field accuracy figure.
- 278 backend tests at 96% coverage, plus TV unit, focus and screenshot tests and iPad client tests, all in CI.

## What's next

Run the label and door evaluation on our own labelled photos, test against a real Ring device and webhooks, and publish the TV app to the Fire TV Appstore.

## Built with

Ring Partner API, Ring Developer Playground, Fire OS, Kotlin, Jetpack Compose for TV, Amazon Bedrock, Amazon Nova, Strands Agents, Model Context Protocol, Amazon Rekognition, Amazon Polly, AWS Lambda, Amazon API Gateway, Amazon DynamoDB, Amazon S3, AWS Systems Manager, Amazon EventBridge Scheduler, Amazon CloudFront, AWS SAM, Python, FastAPI, Preact, TypeScript.

## Links

- Repository (MIT): https://github.com/tanayvasishtha/porch-ledger
- Demo video: (YouTube link added on upload)

## Tracks and mini challenges

Primary tracks: Ring, Fire TV. Mini challenges: AWS Builder, Open Source.

## Product feedback

The full feedback for every tool, with what worked, what did not and requests, is in [FEEDBACK.md](FEEDBACK.md). AWS services used, for the AWS Builder challenge: Lambda, API Gateway HTTP API, DynamoDB, S3, SSM Parameter Store, EventBridge Scheduler, CloudFront, Bedrock (Nova Lite), Rekognition (DetectLabels, DetectText), Polly, Budgets, SAM and CloudFormation.

## Open Source contribution

- Contribution: https://github.com/AmazonAppDev/ring-api-helloworld/pull/42
- Project repository: https://github.com/tanayvasishtha/porch-ledger
- GitHub username: tanayvasishtha
- What, how and why: the official Ring sample had no media example, and media is where we hit the most surprises live. The pull request adds `scripts/download_media.py`, which downloads a snapshot and a clip for one event and prints the matching curl commands like the other scripts. It handles the snapshot 303 to a pre-signed URL without sending the bearer token, the clip 200, 206 and 303 answers, the 416/425 retry schedule from the docs, 429 with Retry-After, and the per-frame 422 we saw on the Playground. It ships with 12 stdlib unittest tests and no new dependencies.

## Existing project

No. Porch Ledger was started during the submission period.

## Friction log

Nineteen entries, each with task, steps, expected and actual result, severity, workaround and suggestion: [FRICTION_LOG.md](FRICTION_LOG.md).

## AI tools used

We used AI coding assistants for planning, code and documentation, with every change reviewed and tested before commit.
