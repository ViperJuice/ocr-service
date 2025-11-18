#!/usr/bin/env python3
"""
Apply Supabase migrations directly using psycopg2.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env file")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)

# Migration file to apply
MIGRATION_FILE = project_root / "supabase/migrations/20250117000000_add_streaming_tokens.sql"

if not MIGRATION_FILE.exists():
    print(f"ERROR: Migration file not found: {MIGRATION_FILE}")
    sys.exit(1)

# Read migration SQL
migration_sql = MIGRATION_FILE.read_text()

print(f"Applying migration: {MIGRATION_FILE.name}")
print("=" * 60)

try:
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()

    # Execute migration
    cursor.execute(migration_sql)

    print("✅ Migration applied successfully!")
    print("=" * 60)
    print("Created:")
    print("  - streaming_tokens table")
    print("  - Indexes for efficient queries")
    print("  - Row Level Security policies")
    print("  - Realtime publication enabled")

    cursor.close()
    conn.close()

except psycopg2.errors.DuplicateTable as e:
    print("⚠️  Table already exists - migration may have been applied previously")
    print(f"Details: {e}")
    sys.exit(0)  # Not a fatal error

except Exception as e:
    print(f"ERROR: Failed to apply migration: {e}")
    sys.exit(1)
