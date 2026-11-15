#!/usr/bin/env python3
"""Check effective dev branch rules before publishing; does not rerun CI or change rules."""

import json
import sys
from pathlib import Path

REQUIRED_CHECKS = {
    "test",  # API Tests
    "ruff",  # API Lint
    "unit",  # Web Tests
    "next-lint",
    "typecheck",
    "Lockfiles in sync",
    "Build (linux/amd64)",
    "Build (linux/arm64)",
    "Service image (api)",
    "Service image (web)",
    "Service image (collab)",
    "Validate dev deployment",
}


def validate_rules(rules):
    if not isinstance(rules, list):
        raise ValueError("Invalid branch-rule response; deployment stopped.")
    reviews = [
        r.get("parameters") or {} for r in rules if r.get("type") == "pull_request"
    ]
    if not any(r.get("required_approving_review_count", 0) >= 1 for r in reviews):
        raise ValueError(
            "dailycommit-dev must require at least one approving PR review."
        )
    checks = [
        r.get("parameters") or {}
        for r in rules
        if r.get("type") == "required_status_checks"
    ]
    if not checks or not all(
        r.get("strict_required_status_checks_policy") is True for r in checks
    ):
        raise ValueError(
            "Require status checks and an up-to-date branch on dailycommit-dev before deployment."
        )
    contexts = {
        check.get("context")
        for rule in checks
        for check in rule.get("required_status_checks", [])
    }
    missing = REQUIRED_CHECKS - contexts
    if missing:
        raise ValueError("Missing required PR checks: " + ", ".join(sorted(missing)))


def main():
    try:
        validate_rules(json.loads(Path(sys.argv[1]).read_text()))
    except (ValueError, OSError, IndexError, TypeError, AttributeError):
        raise SystemExit(
            "PR deployment protections are incomplete or could not be verified. See docs/dev-deployment.md; deployment stopped."
        ) from None
    print(
        "Reviewed, up-to-date PR and required CI checks are enforced by branch rules."
    )


if __name__ == "__main__":
    main()
