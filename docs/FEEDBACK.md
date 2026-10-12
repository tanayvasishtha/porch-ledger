# Product feedback

Feedback on every Amazon tool, API and SDK we used, written while building. Each item says what worked, what did not, and one concrete request. The step-by-step friction we hit is in [FRICTION_LOG.md](FRICTION_LOG.md).

## Ring Partner API

**Worked well**
- The API is small and predictable: device discovery, event history, snapshots and clips each have one endpoint with a clear body. Our whole client is about 200 lines.
- The 303 redirect to a pre-signed URL for snapshots keeps the bearer token off the download host, which is the right design.
- The official `ring-api-helloworld` sample made the first call work in minutes.

**Did not work well**
- Package detection, which owners see in the Ring app, is not exposed to partners. Any delivery feature has to rebuild it from images.
- Event history carries no person or vehicle classification; only the webhook does. Polling clients get less information than webhook clients.
- The status codes for fresh media (416, 425) and their retry schedule are documented on the Media Clips page but not in Error Handling, where a developer looks first.

**Requests**
1. Add `package` to the motion `sub_type` values, or document that it is reserved.
2. Include `sub_type` in event history items.
3. Publish a partner FAQ on which media endpoints remain available under TAKE encryption.

## Ring Developer Playground

**Worked well**
- Zero setup: a token and three simulated scenes without registering an app or owning a device. That is the right on-ramp for a hackathon.

**Did not work well**
- Simulated scenes arrive as `on_demand` live view sessions, never as motion events, and no webhooks fire. The documented motion path cannot be tested.
- Tokens expire after 30 minutes with no refresh, so a deployed poller stops working within half an hour.

**Requests**
1. A "fire webhook" button per scene with a chosen `sub_type`.
2. A sandbox token lifetime of at least 24 hours, or a refresh token.

## Fire TV (Fire OS) development

**Worked well**
- Fire OS 8 matches Android 11 closely enough that a standard Android TV emulator image was a faithful test target; our Compose for TV app ran unchanged.
- The device filtering docs state the exact manifest entries (touchscreen and leanback not required), which saved guesswork.

**Did not work well**
- There is no Fire TV emulator image for Windows developers, and the Vega SDK does not support Windows or WSL. A Windows developer cannot test Vega at all.

**Requests**
1. A Fire OS 8 system image for the Android emulator, or a hosted Vega Virtual Device.

## Alexa+

**Did not work well**
- The MCP Toolkit and simulator are in private preview, so we could not connect our MCP server to Alexa+. We built a web client on an iPad that speaks MCP and followed the add-on design guide instead.

**Requests**
1. Open the web simulator to registered developers in a read-only mode, so they can test an MCP server against real Alexa+ routing before applying to publish.

## AWS: Strands Agents

**Worked well**
- The `@tool` decorator plus hooks (`BeforeToolCallEvent`) gave us a hard tool-call budget in a few lines.
- The custom model provider interface let us test the agent with a scripted model, with no Bedrock calls in CI.

**Did not work well**
- Every current release pins `mcp<2.2`, which forced our MCP server down from the 2.3 SDK.
- The event loop calls the model again after every tool result, which is not obvious from the quick start; a scripted model that returns two tool calls in one turn only runs the first.

**Requests**
1. Relax the MCP upper bound or state the supported range in the release notes.
2. Document the one-tool-per-turn behaviour of the default event loop.

## AWS: SAM, Lambda and the Lambda Web Adapter

**Worked well**
- The Lambda Web Adapter ran our unmodified FastAPI app, MCP mount included, with no handler code.
- `sam validate --lint` caught a wrong `!GetAtt` on the CloudFront Origin Access Control before any deploy.

**Did not work well**
- Packaging on Windows drops the executable bit on `run.sh`, so `sam build` output fails at runtime; we zip the package ourselves.
- Passing the HTTP API's own URL into the function's environment creates a circular dependency.

**Requests**
1. Preserve file modes when SAM packages on Windows, or warn when a handler script is not executable.
2. A documented pattern for giving a function its own HTTP API URL.

## AWS: AI services (Rekognition, Textract, Bedrock Nova, Polly)

**Worked well**
- Rekognition's `DetectLabels` returns instance boxes for vehicles, people and boxes, which is all our engine needs.
- Nova accepts a video by S3 URI in the Converse API, so describing a whole clip is one call with no frame extraction on our side.
- `botocore` Stubber let us test every call shape offline.

**Requests**
1. A Rekognition label for "parcel on the ground" distinct from generic "Box", for delivery use cases.
