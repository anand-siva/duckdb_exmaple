#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Python environment not found. Run ./setup_test_data.sh first."
  exit 1
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
python query_transactions.py "$@"
