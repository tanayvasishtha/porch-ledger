#!/bin/sh
# Lambda Web Adapter bootstrap: serve the FastAPI app on the LWA port.
exec uvicorn "porch.cli:cloud_app" --factory --host 0.0.0.0 --port "${AWS_LWA_PORT:-8080}"
