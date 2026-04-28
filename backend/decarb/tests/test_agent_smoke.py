"""
End-to-end integration smoke test for the agent loop.
Skipped by default — set RUN_INTEGRATION_TESTS=1 to run.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is on path
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_repo_root / "backend"))
from dotenv import load_dotenv
for _p in Path(__file__).resolve().parents:
    _env = _p / ".env"
    if _env.exists():
        load_dotenv(_env)
        break

SITES_DIR = Path(__file__).resolve().parent / "sites"


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="integration only")
def test_agent_calls_retrieve_reference_docs():
    """
    Run the agent on dairy_5mw.json and assert it calls retrieve_reference_docs
    at least once with n >= 1 in the output.
    """
    from decarb.agent import run_agent

    site_path = SITES_DIR / "dairy_5mw.json"
    site_brief = json.loads(site_path.read_text())

    result = run_agent(site_brief, verbose=False)
    tool_calls = result.get("tool_call_log", [])

    rag_calls = [
        tc for tc in tool_calls
        if tc.tool_name == "retrieve_reference_docs"
    ]
    assert len(rag_calls) >= 1, (
        "Agent should call retrieve_reference_docs at least once. "
        f"Tools called: {[tc.tool_name for tc in tool_calls]}"
    )
    assert any(
        tc.outputs and tc.outputs.get("n", 0) >= 1
        for tc in rag_calls
    ), "At least one retrieve_reference_docs call should return n >= 1"
