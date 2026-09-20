#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import boto3, duckdb" >/dev/null 2>&1; then
  echo "Installing Python dependencies..."
  .venv/bin/python -m pip install -r requirements.txt
fi

if ! curl --silent --fail http://localhost:9000/minio/health/live >/dev/null; then
  echo "Starting MinIO..."
  docker compose up -d

  echo "Waiting for MinIO..."
  for _ in {1..30}; do
    if curl --silent --fail http://localhost:9000/minio/health/live >/dev/null; then
      break
    fi
    sleep 2
  done
fi

if ! curl --silent --fail http://localhost:9000/minio/health/live >/dev/null; then
  echo "MinIO did not become ready"
  exit 1
fi

source .venv/bin/activate
python seed_ndjson.py "$@"
