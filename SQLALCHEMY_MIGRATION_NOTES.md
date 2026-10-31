# SQLAlchemy database migration notes

## What changed in this update

- Database engine creation now uses SQLAlchemy 2.x and `URL.create`, with either `DATABASE_URL` or the existing `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` settings.
- `SessionLocal`, `Base`, and the FastAPI `get_db()` session dependency are available for ORM-based routes.
- Existing routes are temporarily supported by a SQLAlchemy-backed compatibility cursor. This avoids a risky all-at-once rewrite of the many existing SQL statements and keeps the current MySQL schema intact while routes are migrated and tested incrementally.
- The legacy fallback `users` table is created through SQLAlchemy's engine; the existing production tables are not automatically recreated.
- The real `.env` file and virtual environment are intentionally excluded from the update archive. Configure a local `.env` using `.env.example`.

## Important before running

1. Back up the existing MySQL database.
2. Copy `.env.example` to `.env` and set the real connection values and a strong `SESSION_SECRET`.
3. Install dependencies: `pip install -r requirements.txt`.
4. Start from the project root using the same entry point used previously, for example `uvicorn app.main:app --reload` if `app` is at the project root; otherwise use the package path matching your folder layout.
5. Verify login, survey submission, reports, and exports against a development copy of the database first.

## Scope note

This is the database foundation/compatibility migration, not yet a claim that every route has been rewritten into ORM expressions. The existing models must be aligned against the actual live MySQL table definitions before converting record, animal, and report queries to ORM relationships. This staged approach avoids guessing column types or damaging existing data.

## Collection status (Part 1)

On application startup, `ensure_personcv_status()` adds `personcv.status` as
`TINYINT NOT NULL DEFAULT 0` if it is missing. Existing rows receive `0`.
The `ck_personcv_status` database constraint restricts values to `0` or `1`.
Restart the application after this update so the migration runs before saving forms.
The database account needs permission to alter `personcv`.

Enumerator Part 1 saves non-collection visits immediately with status `0`;
completed surveys save with status `1`. Non-collection visits retain location,
household number, and interview date; personal text fields are empty and ages are
zero because the existing schema requires non-null values. They create no animal
records. The retired household registration URL redirects to Part 1.

Run isolated request/database tests with:
`python -m unittest discover -s tests -v`. These tests use temporary SQLite
databases and do not connect to the configured MySQL database.
