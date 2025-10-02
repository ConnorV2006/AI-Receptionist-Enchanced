#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Conditionally run migrations
if [ "$AUTO_MIGRATE" = "true" ]; then
  echo "🚀 Running flask db upgrade..."
  flask db upgrade
else
  echo "⚠️ AUTO_MIGRATE is disabled. Skipping migrations."
fi

# Conditionally run seeding
if [ "$AUTO_SEED" = "true" ]; then
  echo "🚀 Running seed_all.py..."
  python src/seed_all.py
else
  echo "⚠️ AUTO_SEED is disabled. Skipping seeding."
fi
