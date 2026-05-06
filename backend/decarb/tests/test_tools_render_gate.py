"""Tests for the render_report Phase 5 validation gate.

Brief acceptance criterion C5 (validate_pathway round): the dispatcher
must refuse to render when validate_pathway has not been called or has
returned passed=false, and surface the failed error-severity check_ids
to the LLM.
"""
from __future__ import annotations

import pytest

from decarb import tools


@pytest.fixture(autouse=True)
def _reset_site_context():
    saved = dict(tools._site_context)
    tools._site_context.clear()
    yield
    tools._site_context.clear()
    tools._site_context.update(saved)


def _seed_context(validate_result):
    tools._site_context.update(
        {
            "site_brief": {"name": "Test"},
            "engine_results": {
                "validate_pathway": validate_result,
                "parse_energy_profile": {"_stub": True},
                "compute_baseline_carbon": {"_stub": True},
                "screen_technologies": {"_stub": True},
                "simulate_site_dispatch": {"_stub": True},
            },
        }
    )


def test_render_report_blocked_when_validate_failed():
    _seed_context(
        {
            "passed": False,
            "summary": {"errors": 1, "warnings": 0, "infos": 0},
            "checks": [
                {
                    "check_id": "carbon_balance_year_15",
                    "severity": "error",
                    "passed": False,
                    "message": "Year-15 carbon balance off by 3.1pp on balanced",
                    "details": {},
                },
                {
                    "check_id": "shortlist_in_pathway_or_excluded",
                    "severity": "warning",
                    "passed": False,
                    "message": "warning, not surfaced",
                    "details": {},
                },
            ],
            "standards_cited": [],
            "provenance": [],
        }
    )

    result = tools.render_report(format="markdown")

    assert "error" in result
    msg = result["error"]
    assert msg.startswith("render_report blocked: validate_pathway returned passed=false")
    assert "carbon_balance_year_15 (error): Year-15 carbon balance off by 3.1pp on balanced" in msg
    # Warnings must NOT be surfaced in the gate failure list (gate filters
    # for severity == "error" only).
    assert "shortlist_in_pathway_or_excluded" not in msg


def test_render_report_blocked_when_validate_missing():
    tools._site_context.update(
        {
            "site_brief": {"name": "Test"},
            "engine_results": {},
        }
    )

    result = tools.render_report(format="markdown")

    assert "error" in result
    assert result["error"].startswith(
        "render_report blocked: validate_pathway has not been called yet"
    )


def test_render_report_passes_gate_when_validate_passed():
    # Intentionally omit site_brief and the engine-output stubs so the
    # downstream "missing required engine outputs" branch fires. The point
    # is to prove the gate cleared, not to exercise a full render.
    tools._site_context.update(
        {
            "engine_results": {
                "validate_pathway": {
                    "passed": True,
                    "summary": {"errors": 0, "warnings": 0, "infos": 0},
                    "checks": [],
                    "standards_cited": [],
                    "provenance": [],
                },
            },
        }
    )

    result = tools.render_report(format="markdown")

    assert "error" in result
    assert "render_report blocked" not in result["error"]
    assert result["error"].startswith("render_report cannot run — missing required engine outputs")
