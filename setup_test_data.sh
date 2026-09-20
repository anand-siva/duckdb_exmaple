#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

echo "====================================="
echo " DuckDB Parquet Example Setup"
echo "====================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found"
  exit 1
fi

echo
echo "[1/4] Creating virtual environment..."
python3 -m venv .venv

echo
echo "[2/4] Installing dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo
echo "[3/4] Starting MinIO..."
docker compose up -d

echo "Waiting for MinIO..."
for _ in {1..30}; do
  if curl --silent --fail http://localhost:9000/minio/health/live >/dev/null; then
    break
  fi
  sleep 2
done

if ! curl --silent --fail http://localhost:9000/minio/health/live >/dev/null; then
  echo "MinIO did not become ready"
  exit 1
fi

echo
echo "[4/4] Seeding Parquet data..."
.venv/bin/python seed_transactions.py "$@"

echo
echo "====================================="
echo "Setup complete"
echo "====================================="
echo
echo "Run the analytical query with:"
echo "  .venv/bin/python query_transactions.py"
echo
echo "MinIO console: http://localhost:9001"
echo "Username: admin"
echo "Password: password123"
