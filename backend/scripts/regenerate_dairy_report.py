"""Backwards-compat thin wrapper around regenerate_site_report.py.

Kept so existing CLAUDE.md / round-protocol references continue to work.
The canonical entry point is now:

    python -m scripts.regenerate_site_report --site dairy_5mw
"""
from __future__ import annotations

from scripts.regenerate_site_report import regenerate


def main() -> None:
    regenerate("dairy_5mw")


if __name__ == "__main__":
    main()
