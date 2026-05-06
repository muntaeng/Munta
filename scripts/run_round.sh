#!/usr/bin/env bash
#
# Supervisor for Builder/Reviewer/Meta-reviewer loop.
#
#   bash scripts/run_round.sh <round_name> [--resume]
#
# Reads plan/reviews/<round_name>/brief.md, then bounces:
#   Builder iter 1 -> Reviewer iter 1 -> [Builder iter 2 -> ...] -> Meta
# CLEAN verdict ends the loop early. Iter-3 cap is hard.
#
# Each session is a fresh `claude -p` invocation: independent context
# (review independence preserved), no polling, no manual nudges.

set -euo pipefail

ROUND="${1:?usage: $0 <round_name> [--resume]}"
RESUME="${2:-}"

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

DIR="plan/reviews/$ROUND"
PROMPTS="scripts/prompts"
N_MAX=3

[[ -d "$DIR" ]]            || { echo "ERR: $DIR missing"; exit 1; }
[[ -f "$DIR/brief.md" ]]   || { echo "ERR: $DIR/brief.md missing"; exit 1; }
[[ -f "$PROMPTS/builder.md"  ]] || { echo "ERR: $PROMPTS/builder.md missing"; exit 1; }
[[ -f "$PROMPTS/reviewer.md" ]] || { echo "ERR: $PROMPTS/reviewer.md missing"; exit 1; }
[[ -f "$PROMPTS/meta.md"     ]] || { echo "ERR: $PROMPTS/meta.md missing"; exit 1; }
command -v claude >/dev/null || { echo "ERR: claude CLI not on PATH"; exit 1; }

# Refuse to clobber a prior round unless --resume.
if [[ "$RESUME" != "--resume" ]] && compgen -G "$DIR/iter_*_build.md" >/dev/null; then
  echo "ERR: $DIR already has iter files. Either:"
  echo "  - move them aside:  mkdir -p $DIR/archive && mv $DIR/iter_*.md $DIR/archive/"
  echo "  - or pass --resume to pick up after the last completed iter"
  exit 1
fi

# Touch actions.md if missing so both roles can append from iter 1.
if [[ ! -f "$DIR/actions.md" ]]; then
  cat > "$DIR/actions.md" <<EOF
# Action log: $ROUND

Append-only. Format: \`[YYYY-MM-DDTHH:MM][role][iter<N>] <action>\`

Roles: \`builder\`, \`reviewer\`, \`meta\`.

---

[$(date -u +%Y-%m-%dT%H:%M)][supervisor][iter0] Round started.
EOF
fi

render_prompt() {
  # $1 = path to prompt template, $2 = iter number
  sed -e "s|{ROUND}|$ROUND|g" -e "s|{N}|$2|g" "$1"
}

run_role() {
  # $1 = role label (for logging), $2 = prompt template path, $3 = iter
  local role="$1" tmpl="$2" n="$3"
  echo
  echo "════════════════════════════════════════════════════"
  echo "  $role  —  round=$ROUND  iter=$n  $(date -u +%H:%M:%SZ)"
  echo "════════════════════════════════════════════════════"
  render_prompt "$tmpl" "$n" | claude -p \
    --model opus \
    --dangerously-skip-permissions \
    --no-session-persistence
}

# Determine starting iter (1, or first iter without a build file when --resume).
START_ITER=1
if [[ "$RESUME" == "--resume" ]]; then
  for n in 1 2 3; do
    if [[ ! -f "$DIR/iter_${n}_build.md" ]]; then
      START_ITER=$n
      break
    fi
    if [[ ! -f "$DIR/iter_${n}_review.md" ]]; then
      # Build done, review missing — re-run Reviewer for this n
      START_ITER=$n
      break
    fi
    # Both exist — check verdict; CLEAN means we go straight to meta
    if grep -q "^## Verdict: CLEAN" "$DIR/iter_${n}_review.md"; then
      echo "iter $n already CLEAN — skipping to META"
      run_role "META" "$PROMPTS/meta.md" 0
      [[ -f "$DIR/META_SUMMARY.md" ]] || { echo "ERR: META did not write META_SUMMARY.md"; exit 6; }
      echo; echo "═══ DONE — see $DIR/META_SUMMARY.md ═══"
      exit 0
    fi
  done
  echo "resuming at iter $START_ITER"
fi

VERDICT=""
LAST_N=$START_ITER
for ((N=START_ITER; N<=N_MAX; N++)); do
  LAST_N=$N

  # ── BUILDER ──
  if [[ ! -f "$DIR/iter_${N}_build.md" ]]; then
    run_role "BUILDER" "$PROMPTS/builder.md" "$N"
    if [[ ! -f "$DIR/iter_${N}_build.md" ]]; then
      echo "ERR: Builder iter $N did not write $DIR/iter_${N}_build.md"
      exit 2
    fi
    # Stamp Builder's commit SHA into the iter file. Builder writes the
    # placeholder `<stamped post-commit>` because the iter file is itself
    # part of the commit and the SHA isn't computable until afterwards.
    SHA=$(git rev-parse HEAD)
    sed -i.bak "s|^## Commit: <stamped post-commit>$|## Commit: $SHA|" \
      "$DIR/iter_${N}_build.md"
    rm -f "$DIR/iter_${N}_build.md.bak"
    if ! git diff --quiet -- "$DIR/iter_${N}_build.md"; then
      git add "$DIR/iter_${N}_build.md"
      git commit -m "[stamp iter $N] $SHA" >/dev/null
      echo "(stamped iter $N SHA: $SHA)"
    fi
  else
    echo "(iter_${N}_build.md exists — skipping Builder)"
  fi

  # ── REVIEWER ──
  run_role "REVIEWER" "$PROMPTS/reviewer.md" "$N"
  if [[ ! -f "$DIR/iter_${N}_review.md" ]]; then
    echo "ERR: Reviewer iter $N did not write $DIR/iter_${N}_review.md"
    exit 3
  fi

  VERDICT=$(awk '/^## Verdict:/{print $3; exit}' "$DIR/iter_${N}_review.md")
  echo
  echo "──── iter $N verdict: ${VERDICT:-<unparsed>} ────"

  if [[ "$VERDICT" == "CLEAN" ]]; then
    break
  fi
  if [[ "$VERDICT" != "ISSUES_FOUND" ]]; then
    echo "ERR: Reviewer verdict not CLEAN or ISSUES_FOUND (got: '$VERDICT')"
    exit 4
  fi
done

if [[ "$VERDICT" != "CLEAN" && $LAST_N -ge $N_MAX ]]; then
  echo "── iter-3 cap reached with ISSUES_FOUND; residuals declared as warnings ──"
fi

# ── META ──
run_role "META" "$PROMPTS/meta.md" 0
[[ -f "$DIR/META_SUMMARY.md" ]] || { echo "ERR: META did not write META_SUMMARY.md"; exit 6; }

echo
echo "════════════════════════════════════════════════════"
echo "  ROUND COMPLETE  —  final verdict: $VERDICT"
echo "  see: $DIR/META_SUMMARY.md"
echo "════════════════════════════════════════════════════"
