#!/usr/bin/env python3
"""Render GitHub Secrets into private, raw Compose env files; never print values."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC_ORIGIN = "https://dev.dailycommit.co.za"

REQUIRED = {
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "LEARNHOUSE_AUTH_JWT_SECRET_KEY",
    "NEXTAUTH_SECRET",
    "COLLAB_INTERNAL_KEY",
    "LEARNHOUSE_INITIAL_ADMIN_EMAIL",
    "LEARNHOUSE_INITIAL_ADMIN_PASSWORD",
}
STABLE = {
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "LEARNHOUSE_AUTH_JWT_SECRET_KEY",
    "NEXTAUTH_SECRET",
    "COLLAB_INTERNAL_KEY",
}
OPTIONAL = {
    "LEARNHOUSE_EMAIL_PROVIDER",
    "LEARNHOUSE_SYSTEM_EMAIL_ADDRESS",
    "LEARNHOUSE_SYSTEM_EMAIL_SENDER_NAME",
    "LEARNHOUSE_RESEND_API_KEY",
    "LEARNHOUSE_SMTP_HOST",
    "LEARNHOUSE_SMTP_PORT",
    "LEARNHOUSE_SMTP_USERNAME",
    "LEARNHOUSE_SMTP_PASSWORD",
    "LEARNHOUSE_SMTP_USE_TLS",
}


def validate(values, public_url):
    if (
        not isinstance(values, dict)
        or not REQUIRED.issubset(values)
        or set(values) - REQUIRED - OPTIONAL
    ):
        raise ValueError(
            "DEV_ENV_JSON has missing or unsupported keys; see the deployment guide"
        )
    if any(
        not isinstance(v, str) or any(c in v for c in "\r\n\x00")
        for v in values.values()
    ):
        raise ValueError("All secret values must be single-line strings")
    for key in STABLE:
        # URL-safe credentials also avoid the upstream Alembic URL interpolation issue with % escapes.
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", values[key]):
            raise ValueError(
                "Database/Redis passwords and signing keys must be distinct URL-safe values of at least 32 characters"
            )
    if len({values[k] for k in STABLE}) != len(STABLE):
        raise ValueError(
            "Use a different value for each database/Redis/signing/internal secret"
        )
    email = values["LEARNHOUSE_INITIAL_ADMIN_EMAIL"]
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Initial admin email is invalid")
    password = values["LEARNHOUSE_INITIAL_ADMIN_PASSWORD"]
    if len(password) < 12 or not all(
        re.search(p, password) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    ):
        raise ValueError(
            "Initial admin password needs at least 12 characters, upper/lowercase, a number and a symbol"
        )
    parsed = urlsplit(public_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "dev.dailycommit.co.za"
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError("DEV_PUBLIC_URL must be https://dev.dailycommit.co.za")
    return PUBLIC_ORIGIN, parsed.hostname


def environment(values, public_url):
    public_url, host = validate(values, public_url)
    app = {
        "HOSTNAME": "0.0.0.0",
        "PORT": "8000",
        "LEARNHOUSE_PORT": "9000",
        "COLLAB_PORT": "4000",
        "LEARNHOUSE_API_URL": "http://127.0.0.1:9000",
        "LEARNHOUSE_SQL_CONNECTION_STRING": f"postgresql://learnhouse:{values['POSTGRES_PASSWORD']}@db:5432/learnhouse",
        "LEARNHOUSE_REDIS_CONNECTION_STRING": f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0",
        "LEARNHOUSE_REDIS_URL": f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0",
        "LEARNHOUSE_AUTH_JWT_SECRET_KEY": values["LEARNHOUSE_AUTH_JWT_SECRET_KEY"],
        "NEXTAUTH_SECRET": values["NEXTAUTH_SECRET"],
        "COLLAB_INTERNAL_KEY": values["COLLAB_INTERNAL_KEY"],
        "LEARNHOUSE_INITIAL_ADMIN_EMAIL": values["LEARNHOUSE_INITIAL_ADMIN_EMAIL"],
        "LEARNHOUSE_INITIAL_ADMIN_PASSWORD": values[
            "LEARNHOUSE_INITIAL_ADMIN_PASSWORD"
        ],
        "LEARNHOUSE_INITIAL_ORG_NAME": "Daily Commit",
        "LEARNHOUSE_INITIAL_ORG_SLUG": "default",
        "LEARNHOUSE_SITE_NAME": "DailyCommit",
        "LEARNHOUSE_ENV": "dev",
        "LEARNHOUSE_TENANCY": "single",
        "LEARNHOUSE_SAAS": "false",
        "LEARNHOUSE_DISABLE_EE": "1",
        "LEARNHOUSE_DEVELOPMENT_MODE": "false",
        "LEARNHOUSE_IS_AI_ENABLED": "false",
        "LEARNHOUSE_LOGFIRE_ENABLED": "false",
        "LEARNHOUSE_SSL": "true",
        "LEARNHOUSE_DOMAIN": host,
        "LEARNHOUSE_FRONTEND_DOMAIN": host,
        "LEARNHOUSE_ALLOWED_ORIGINS": public_url,
        "LEARNHOUSE_ALLOWED_REGEXP": "^" + re.escape(public_url) + "$",
        "LEARNHOUSE_COOKIE_DOMAIN": host,
        "NEXTAUTH_URL": public_url,
        "NEXT_PUBLIC_LEARNHOUSE_DOMAIN": host,
        "NEXT_PUBLIC_LEARNHOUSE_TOP_DOMAIN": host,
        "NEXT_PUBLIC_LEARNHOUSE_DEFAULT_ORG": "default",
        "NEXT_PUBLIC_LEARNHOUSE_MULTI_ORG": "false",
        "NEXT_PUBLIC_LEARNHOUSE_HTTPS": "true",
        "NEXT_PUBLIC_LEARNHOUSE_OSS": "true",
        "NEXT_PUBLIC_LEARNHOUSE_BACKEND_URL": public_url + "/",
        "NEXT_PUBLIC_LEARNHOUSE_API_URL": public_url + "/api/v1/",
        "NEXT_PUBLIC_COLLAB_URL": "wss://" + host + "/collab",
    }
    app.update({k: v for k, v in values.items() if k in OPTIONAL})
    return {
        "app.env": app,
        "db.env": {
            "POSTGRES_USER": "learnhouse",
            "POSTGRES_DB": "learnhouse",
            "POSTGRES_PASSWORD": values["POSTGRES_PASSWORD"],
        },
        "redis.env": {"REDIS_PASSWORD": values["REDIS_PASSWORD"]},
    }


def write_private(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-url", required=True)
    args = parser.parse_args()
    try:
        values = json.loads(os.environ.get("DEV_ENV_JSON", ""))
        files = environment(values, args.public_url)
        for name, fields in files.items():
            write_private(
                args.output / name, "".join(f"{k}={v}\n" for k, v in fields.items())
            )
        fingerprints = {
            k: hashlib.sha256(values[k].encode()).hexdigest() for k in sorted(STABLE)
        }
        write_private(
            args.output / "secret-fingerprints.json",
            json.dumps(fingerprints, sort_keys=True) + "\n",
        )
        username, token = (
            os.environ.get("GHCR_USERNAME", ""),
            os.environ.get("GHCR_TOKEN", ""),
        )
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", username)
            or not token
            or any(c in token for c in "\r\n\x00")
        ):
            raise ValueError(
                "GHCR_USERNAME/GHCR_TOKEN are required for private VM pulls"
            )
        write_private(
            args.output / ".registry-auth.json",
            json.dumps({"username": username, "token": token}) + "\n",
        )
        print("Deployment environment validated and rendered; secret values withheld.")
    except (ValueError, OSError):
        # Avoid echoing JSON parsing errors or rejected input: either can contain a secret.
        parser.exit(
            1,
            "Invalid deployment secrets/settings or output directory. See docs/dev-deployment.md; no secret values were printed.\n",
        )


if __name__ == "__main__":
    main()
