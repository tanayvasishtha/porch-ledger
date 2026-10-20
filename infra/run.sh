#!/bin/sh
# Lambda Web Adapter bootstrap: serve the FastAPI app on the LWA port.
# python3 is on PATH in the managed python3.12 runtime; -m picks the package,
# not the bin/ shim, which uv only writes as uvicorn.exe under --target on Windows.
exec python3 -m uvicorn "porch.cli:cloud_app" --factory --host 0.0.0.0 --port "${AWS_LWA_PORT:-8080}"
