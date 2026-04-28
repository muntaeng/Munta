"""
Orchestrator agent — the LLM loop that calls deterministic tools to produce
a decarbonisation pathway analysis.

Run from CLI:
    cd backend
    python -m decarb.agent --site-brief decarb/tests/sites/dairy_5mw.json

Goals for this skeleton:
  - Loop with Anthropic tool-use until the model stops requesting tools
  - Log every tool call to stdout AND the agent_tool_calls table
  - Cap iterations + token budget so a runaway loop fails loudly
  - Simple file-based system prompt so it is git-versioned

Real RAG retrieval, multi-step reasoning, self-critique, and report rendering
are added incrementally over weeks 1–4.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

from decarb.tools import (
    TOOL_SCHEMAS, dispatch, ToolCallRecord,
    parse_energy_profile, screen_technologies, set_site_context,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

MODEL = os.getenv("DECARB_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 30
MAX_TOKENS_PER_RESPONSE = 16384
TOTAL_TOKEN_BUDGET = 200_000   # safety cap per run

PROMPT_PATH = Path(__file__).parent / "prompts" / "orchestrator_v0_1.txt"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text()


def _compact_energy_profile(ep: dict[str, Any]) -> dict[str, Any]:
    """Strip 8,760-hour arrays from energy profile for LLM context."""
    compact = {k: v for k, v in ep.items() if k != "end_use_profiles"}
    compact["end_use_profiles"] = []
    for eu in ep.get("end_use_profiles", []):
        compact["end_use_profiles"].append(
            {k: v for k, v in eu.items() if k != "_profile_8760"}
        )
    return compact


def _compact_screening(sc: dict[str, Any]) -> dict[str, Any]:
    """Keep shortlist IDs + capacity + key risks; drop verbose rationale."""
    return {
        "shortlist": [
            {
                "tech_id": t["tech_id"],
                "category": t.get("category"),
                "capacity_range_kw": t.get("capacity_range_kw"),
                "flagged_risks": [r[:100] for r in t.get("flagged_risks", [])[:2]],
            }
            for t in sc.get("shortlist", [])
        ],
        "excluded": [
            {"tech_id": e["tech_id"], "failed_axis": e.get("failed_axis", "")}
            for e in sc.get("excluded", [])
        ],
    }


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def run(site_brief: dict[str, Any], verbose: bool = True) -> dict[str, Any]:
    """
    Run the orchestrator on a single site brief.

    Returns:
        {
            "run_uuid": str,
            "final_message": str,
            "tool_calls": [ToolCallRecord, ...],
            "tokens_used": int,
            "stopped_reason": str,
        }
    """
    client = Anthropic()
    system_prompt = load_system_prompt()
    run_uuid = str(uuid.uuid4())

    # --- Pre-compute site context (avoids passing site_brief via tool calls) ---
    if verbose:
        print("=== pre-computing site context ===")

    energy_profile = parse_energy_profile(site_brief=site_brief)
    screening = screen_technologies(site_brief=site_brief, energy_profile=energy_profile)

    set_site_context({
        "site_brief": site_brief,
        "energy_profile": energy_profile,
        "screening": screening,
    })

    if verbose:
        print(f"  energy profile: {len(energy_profile.get('end_use_profiles', []))} end-uses")
        print(f"  screening: {screening.get('shortlist_count', 0)} shortlisted, {screening.get('excluded_count', 0)} excluded")

    # --- Build compact context for the LLM ---
    compact_ep = _compact_energy_profile(energy_profile)
    compact_sc = _compact_screening(screening)

    site_header = {
        "site_id": site_brief.get("site_id"),
        "site_name": site_brief.get("site_name"),
        "sector": site_brief.get("sector"),
        "subsector": site_brief.get("subsector"),
        "location": site_brief.get("location"),
        "constraints": site_brief.get("constraints"),
        "regulatory": site_brief.get("regulatory"),
    }

    initial_user_message = (
        "Produce a decarbonisation pathway analysis for this site.\n\n"
        "## Site summary\n"
        f"```json\n{json.dumps(site_header, indent=2)}\n```\n\n"
        "## Energy profile (pre-computed via parse_energy_profile)\n"
        f"```json\n{json.dumps(compact_ep, indent=2)}\n```\n\n"
        "## Technology screening (pre-computed via screen_technologies)\n"
        f"```json\n{json.dumps(compact_sc, indent=2)}\n```\n\n"
        "Energy profile and screening are already done. "
        "Proceed from step 2 of your workflow: compute baseline carbon, "
        "then simulate shortlisted technologies, optimise pathways, and produce the report."
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": initial_user_message}
    ]

    tool_call_log: list[ToolCallRecord] = []
    tokens_used = 0
    stopped_reason = "unknown"

    for iteration in range(MAX_ITERATIONS):
        if verbose:
            print(f"\n=== iteration {iteration + 1} ===")

        if tokens_used > TOTAL_TOKEN_BUDGET:
            stopped_reason = "token_budget_exceeded"
            break

        # Retry with backoff on rate-limit (429)
        for attempt in range(4):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS_PER_RESPONSE,
                    system=system_prompt,
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
                break
            except Exception as api_err:
                if "429" in str(api_err) or "rate_limit" in str(api_err):
                    wait = 15 * (2 ** attempt)
                    if verbose:
                        print(f"  rate-limited, waiting {wait}s (attempt {attempt + 1}/4)")
                    time.sleep(wait)
                else:
                    raise
        else:
            stopped_reason = "rate_limit_exhausted"
            break

        tokens_used += response.usage.input_tokens + response.usage.output_tokens

        # Append assistant turn
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # Inspect the stop reason
        if response.stop_reason == "end_turn":
            stopped_reason = "end_turn"
            break

        if response.stop_reason != "tool_use":
            stopped_reason = f"unexpected_stop:{response.stop_reason}"
            break

        # Run all tool calls in this response, append a single user turn with all results
        tool_results = []
        for block in assistant_content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            tool_use_id = block.id

            if verbose:
                print(f"  → tool: {tool_name}")
                print(f"    inputs: {json.dumps(tool_input, indent=2)[:400]}")

            t0 = time.time()
            try:
                output = dispatch(tool_name, tool_input)
                error = None
            except Exception as e:    # noqa: BLE001
                output = {"error": str(e), "type": type(e).__name__}
                error = str(e)
            duration_ms = int((time.time() - t0) * 1000)

            tool_call_log.append(
                ToolCallRecord(
                    sequence=len(tool_call_log) + 1,
                    tool_name=tool_name,
                    inputs=tool_input,
                    outputs=output,
                    duration_ms=duration_ms,
                    error=error,
                )
            )

            if verbose:
                print(f"    ← {duration_ms}ms")

            # Cap tool result size in conversation to limit history growth.
            # Full results are preserved in tool_call_log for provenance.
            result_json = json.dumps(output)
            if len(result_json) > 800:
                result_json = result_json[:800] + '..."truncated"}'

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_json,
                    "is_error": error is not None,
                }
            )

        if not tool_results:
            stopped_reason = "no_tool_calls_in_tool_use_response"
            break

        messages.append({"role": "user", "content": tool_results})

    else:
        stopped_reason = "max_iterations_reached"

    # Extract final text from last assistant message
    final_text = ""
    if messages and messages[-1]["role"] == "assistant":
        for block in messages[-1]["content"]:
            if hasattr(block, "type") and block.type == "text":
                final_text += block.text

    if verbose:
        print(f"\n=== run complete ===")
        print(f"  stop reason: {stopped_reason}")
        print(f"  iterations: {iteration + 1}")
        print(f"  tool calls: {len(tool_call_log)}")
        print(f"  tokens used: {tokens_used}")

    return {
        "run_uuid": run_uuid,
        "final_message": final_text,
        "tool_calls": [c.__dict__ for c in tool_call_log],
        "tokens_used": tokens_used,
        "stopped_reason": stopped_reason,
        "iterations": iteration + 1,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the decarb orchestrator on a site brief.")
    parser.add_argument(
        "--site-brief",
        type=Path,
        required=True,
        help="Path to a JSON file describing the site",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--out", type=Path, help="Optional path to save the run record as JSON")
    args = parser.parse_args()

    site_brief = json.loads(args.site_brief.read_text())
    result = run(site_brief, verbose=not args.quiet)

    print("\n=== final assistant message ===\n")
    print(result["final_message"])

    if args.out:
        args.out.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved run record to {args.out}")


if __name__ == "__main__":
    main()
