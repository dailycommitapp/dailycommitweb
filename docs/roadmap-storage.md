# DailyCommit roadmap storage

`src/db/roadmaps.py` defines two independent tables: `roadmaps` and
`roadmap_nodes`. Model discovery loads them automatically; no existing LMS
model or table is changed. The only foreign key is from a node to its roadmap.
Deleting a roadmap deletes that roadmap's nodes, never LMS courses or users.

Roadmaps are site-wide for the current single-organization DailyCommit setup.
They are draft by default. This change adds storage only, with no routes,
publication UI, permissions, course creation or progress tracking.

## Columns and JSON format

- `roadmaps`: UUID `id`, globally unique `slug`, `title`, `summary`, `sections`,
  `status` (`draft` / `published`), timezone-aware `created_at` / `updated_at`.
- `roadmap_nodes`: UUID `id`, required `roadmap_id`, `slug` (unique per roadmap),
  `title`, `summary`, `sections`, `connections`, `course_links`, `layout`, and
  nonnegative `position`. There is an index on `(roadmap_id, position)`.
- `sections`: `[ { "heading": "Why learn this?", "body": "Own explanation" } ]`.
- `connections`: `[ { "target_slug": "git", "relationship": "suggested_next" } ]`.
- `course_links`: `[ { "course_uuid": "existing-lms-course-uuid" } ]`.
- `layout`: `{ "column": 1, "row": 2 }`; `position` is linear reading order.

PostgreSQL stores JSON fields as JSONB. SQLite uses JSON for compatibility with
the existing test suite. Defaults are independent empty lists/objects, not
shared Python mutable values. Replace a JSON field with a new list/object when
editing through SQLModel so SQLAlchemy detects the update.

Future authoring endpoints must validate JSON shapes, referenced slugs within
the same roadmap, cycles, permitted relationship values, and linked course
existence/access. JSON references are not database foreign keys. These tables
alone do not provide API validation or access control. Reused topics currently
have separate rows in each roadmap, as agreed for the two-table MVP.

SQLAlchemy updates `updated_at` on roadmap updates. Raw SQL writers must set
`updated_at = now()` themselves; no database trigger has been added.

## Migration

`dc01a2b3c4d5_add_dailycommit_roadmaps.py` follows `8d2b6f4c1e75`. On an
environment already managed by Alembic, use the usual migration deployment
process (`alembic upgrade head` from `apps/api`). It creates only these tables
and the nodes ordering index. Startup `create_all` may already have created
them; the migration accepts existing matching column sets. It does not repair
drift in existing types, defaults or constraints; investigate any drift before
migrating. Downgrade removes only these new tables and their roadmap data.

The inspected local Docker database has no `alembic_version` table, so do not
blindly run the entire migration chain or stamp its history. For that local
database only, apply this revision's `upgrade()` within a transaction using
Alembic's `MigrationContext` / `Operations` API. This adds the two tables
without changing the migration history or replaying unrelated LMS migrations.
No Azure or remote database is part of this change.

## Verification performed

The two empty tables were created locally. All 64 pre-existing tables retained
their definitions and row counts. The temporary roadmap test suite and local
apply/check helpers were subsequently removed at the user's request. Existing
LearnHouse tests are unchanged.
