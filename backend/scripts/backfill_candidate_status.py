"""
One-time backfill script: Update candidates stuck at status='new' that already have scores.

This should be run after deploying the auto-transition fix for scoring.
It handles the gap between existing data and the new behavior by running a
single DB-level UPDATE — no loading of rows into Python.

Constraints (safe by the WHERE clause):
- Only touches candidates with status='new' that have ≥1 score
- Does NOT touch hired, rejected, or archived candidates
- Excludes seed data (is_seed_data=1)
- Excludes soft-deleted candidates (deleted_at IS NOT NULL)

Usage:
    cd backend && source venv/bin/activate && python scripts/backfill_candidate_status.py
"""

import sys
import os

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.database import SessionLocal


def backfill_candidate_statuses() -> int:
    """
    DB-level UPDATE: set status='reviewed' for candidates stuck at 'new'
    that have at least one score. Only affects active (non-deleted, non-seed) candidates.
    """
    db = SessionLocal()
    try:
        # Preview: count affected rows before updating
        preview_sql = text("""
            SELECT COUNT(*) FROM candidates c
            WHERE c.status = 'new'
              AND c.deleted_at IS NULL
              AND c.is_seed_data = 0
              AND EXISTS (
                  SELECT 1 FROM scores s WHERE s.candidate_id = c.id
              )
        """)
        count = db.execute(preview_sql).scalar()

        if count == 0:
            print("No candidates need backfill. ✓")
            return 0

        print(f"Found {count} candidate(s) to backfill.")

        # Run the DB-level UPDATE
        update_sql = text("""
            UPDATE candidates
            SET status = 'reviewed'
            WHERE status = 'new'
              AND deleted_at IS NULL
              AND is_seed_data = 0
              AND id IN (
                  SELECT DISTINCT candidate_id FROM scores
              )
        """)
        result = db.execute(update_sql)
        db.commit()

        affected = result.rowcount
        print(f"Backfilled {affected} candidate(s): status='new' → 'reviewed' ✓")

        # Show which candidates were updated
        details_sql = text("""
            SELECT c.id, c.name, c.email, c.role_applied,
                   (SELECT COUNT(*) FROM scores s WHERE s.candidate_id = c.id) AS score_count
            FROM candidates c
            WHERE c.status = 'reviewed'
              AND c.deleted_at IS NULL
              AND c.is_seed_data = 0
              AND c.id IN (
                  SELECT DISTINCT candidate_id FROM scores
              )
            ORDER BY c.id
        """)
        rows = db.execute(details_sql).fetchall()
        for row in rows:
            print(f"  - ID={row[0]} {row[1]} ({row[2]}) — {row[3]} ({row[4]} score(s))")

        return affected
    finally:
        db.close()


if __name__ == "__main__":
    backfill_candidate_statuses()
