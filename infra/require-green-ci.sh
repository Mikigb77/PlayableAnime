#!/usr/bin/env bash
# Passes only when the CI workflow succeeded on this exact commit of main (T13). Waits while CI is
# still running, for up to CI_WAIT_SECONDS. Runs in the deploy workflow with GH_TOKEN set.

set -euo pipefail

repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
sha="${GITHUB_SHA:?GITHUB_SHA is not set}"
ref="${GITHUB_REF:?GITHUB_REF is not set}"
workflow="${CI_WORKFLOW_FILE:-ci.yml}"
wait_seconds="${CI_WAIT_SECONDS:-1800}"
poll_seconds="${CI_POLL_SECONDS:-20}"
# CI can take a few seconds to register a run after a push.
missing_grace_seconds="${CI_MISSING_GRACE_SECONDS:-120}"

if [ "$ref" != refs/heads/main ]; then
  echo "::error::Deploys run only from main, and this run is on $ref."
  exit 1
fi

SECONDS=0
while :; do
  # A failed call (a GitHub hiccup) counts as "still waiting", not as an answer.
  if ! run="$(gh api -X GET "repos/$repo/actions/workflows/$workflow/runs" \
    -f head_sha="$sha" -f event=push -f branch=main -f per_page=1 \
    --jq '.workflow_runs[0] // empty | "\(.status) \(.conclusion // "none") \(.html_url)"')"; then
    run="unknown none (GitHub didn't answer)"
  fi
  status="${run%% *}"
  rest="${run#* }"
  conclusion="${rest%% *}"
  url="${rest#* }"

  if [ -z "$run" ]; then
    if [ "$SECONDS" -ge "$missing_grace_seconds" ]; then
      echo "::error::No CI run found for $sha on main. Deploy only a commit that CI has checked."
      exit 1
    fi
    echo "No CI run for $sha yet; waiting."
  elif [ "$status" = completed ]; then
    if [ "$conclusion" = success ]; then
      echo "CI passed on $sha: $url"
      exit 0
    fi
    echo "::error::CI finished as '$conclusion' on $sha, so nothing is deployed: $url"
    exit 1
  else
    echo "CI is $status on $sha; waiting: $url"
  fi

  if [ "$SECONDS" -ge "$wait_seconds" ]; then
    echo "::error::CI didn't finish within $wait_seconds s on $sha."
    exit 1
  fi
  sleep "$poll_seconds"
done
