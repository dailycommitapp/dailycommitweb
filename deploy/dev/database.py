#!/usr/bin/env python3
"""Deployment-only schema checks. Executed inside the existing application image."""

import argparse
import json
import os


def classify(tables, versions):
    if versions:
        if not {"organization", "user"}.issubset(tables):
            raise ValueError("Versioned database is missing core LearnHouse tables")
        return "versioned"
    if tables - {"alembic_version"}:
        return "unversioned"
    return "fresh"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["inspect", "upgrade", "stamp", "verify"])
    args = parser.parse_args()
    try:
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, inspect, text

        url = os.environ["LEARNHOUSE_SQL_CONNECTION_STRING"]
        engine = create_engine(url, hide_parameters=True)
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names(schema="public"))
            versions = (
                set(
                    conn.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalars()
                )
                if "alembic_version" in tables
                else set()
            )
        state = classify(tables, versions)
        cfg = Config("/app/api/alembic.ini")
        heads = set(ScriptDirectory.from_config(cfg).get_heads())
        if args.operation == "inspect":
            print(
                json.dumps(
                    {
                        "state": state,
                        "versions": sorted(versions),
                        "image_heads": sorted(heads),
                    }
                )
            )
        elif args.operation == "upgrade":
            if state != "versioned":
                raise ValueError(
                    "Refusing to migrate an unversioned database; a verified baseline is required"
                )
            command.upgrade(cfg, "heads")
        elif args.operation == "stamp":
            if state != "unversioned" or not {"organization", "user"}.issubset(tables):
                raise ValueError(
                    "Stamp is only for a just-bootstrapped LearnHouse schema"
                )
            command.stamp(cfg, "heads")
        else:
            if versions != heads:
                raise ValueError("Database migration heads do not match this image")
            print("Database migration heads verified.")
        engine.dispose()
    except Exception as exc:
        # stderr may be captured into a private VM migration log, never include connection URLs.
        print(
            "Database deployment operation failed ("
            + type(exc).__name__
            + "). Inspect the private VM migration log.",
            flush=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
