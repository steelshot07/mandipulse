#!/usr/bin/env bash
# Build the Lambda deployment zip for the daily ingestion job.
# Usage (from repo root): bash infra/aws/build_lambda.sh  ->  dist/ingest-lambda.zip
# Installs Linux x86_64 wheels for Python 3.11 (the Lambda runtime), whatever OS builds it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD="$ROOT/dist/lambda"
ZIP="$ROOT/dist/ingest-lambda.zip"
rm -rf "$BUILD" "$ZIP"
mkdir -p "$BUILD"

# Only what the ingestion path imports (no FastAPI/uvicorn/alembic). Bounds match pyproject.toml.
python -m pip install --quiet --target "$BUILD" \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all: \
  "httpx>=0.27" "sqlalchemy>=2.0" "psycopg[binary]>=3.2" "pydantic>=2.7" "pydantic-settings>=2.3"

cp -r "$ROOT/backend/app" "$ROOT/backend/ingestion" "$BUILD/"
find "$BUILD" -name "__pycache__" -type d -prune -exec rm -rf {} +

(cd "$BUILD" && python -c "import shutil; shutil.make_archive('../ingest-lambda', 'zip', '.')")
echo "Built $ZIP ($(du -h "$ZIP" | cut -f1))"
