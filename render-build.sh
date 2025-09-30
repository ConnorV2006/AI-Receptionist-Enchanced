#!/usr/bin/env bash
set -o errexit
set -o pipefail

echo "Installing dependencies…"
pip install -r requirements.txt

echo "Applying database migrations…"
flask db upgrade || echo "Warning: could not run migrations. Ensure FLASK_APP is set to app.py."

echo "Build completed."