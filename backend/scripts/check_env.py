#!/usr/bin/env python3
"""Validate that all required environment variables are set."""

import os
import sys

REQUIRED = [
    "DATABASE_URL",
    "REDIS_URL",
    "SLACK_CLIENT_ID",
    "SLACK_CLIENT_SECRET",
    "SLACK_SIGNING_SECRET",
    "ANTHROPIC_API_KEY",
    "JWT_SECRET",
]

OPTIONAL = [
    "VOYAGE_API_KEY",
    "JIRA_DOMAIN",
    "GITHUB_TOKEN",
]


def main() -> int:
    missing = []
    print("=== Required Environment Variables ===")
    for var in REQUIRED:
        value = os.environ.get(var)
        if value:
            print(f"  {var}: OK")
        else:
            print(f"  {var}: MISSING")
            missing.append(var)

    print("\n=== Optional Environment Variables ===")
    for var in OPTIONAL:
        value = os.environ.get(var)
        if value:
            print(f"  {var}: set")
        else:
            print(f"  {var}: not set")

    if missing:
        print(f"\nERROR: Missing required variables: {', '.join(missing)}")
        return 1

    print("\nAll required environment variables are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
