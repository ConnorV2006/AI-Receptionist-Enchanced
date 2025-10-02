#!/bin/bash
# Usage: ./reset_admin.sh <username> <password> [superadmin] [clinic_id]

USERNAME=$1
PASSWORD=$2
SUPERADMIN=${3:-true}    # defaults to true if not specified
CLINIC_ID=${4:-}         # optional

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
  echo "❌ Usage: ./reset_admin.sh <username> <password> [superadmin] [clinic_id]"
  exit 1
fi

echo "🔄 Resetting/creating admin: $USERNAME"

ADMIN_USERNAME=$USERNAME ADMIN_PASSWORD=$PASSWORD ADMIN_SUPERADMIN=$SUPERADMIN ADMIN_CLINIC_ID=$CLINIC_ID python src/seed_admin.py
