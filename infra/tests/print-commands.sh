#!/usr/bin/env bash
# Prints every command that bootstrap.sh and deploy.sh run, from their dry runs, in the form
# docs/DEPLOY.md shows them. infra/tests/run.sh fails when that doc's copy is out of date, so after
# changing a script, paste this output between the markers in docs/DEPLOY.md.

set -euo pipefail

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(dirname "$INFRA")"
image="europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:DIGEST"

commands() {
  sed -n 's/^\[dry-run\] \(gcloud .*\)$/\1/p' |
    sed -e 's#--env-vars-file=[^ ]*#--env-vars-file=ENV_FILE#' -e "s#$ROOT/##g"
}

export DRY_RUN=1 GITHUB_ACTIONS=true GITHUB_SHA=COMMIT_SHA
echo "# infra/bootstrap.sh"
"$INFRA/bootstrap.sh" --dry-run 2>&1 | commands
echo
echo "# infra/deploy.sh migrate IMAGE"
"$INFRA/deploy.sh" migrate "$image" 2>&1 | commands
echo
echo "# infra/deploy.sh service IMAGE"
"$INFRA/deploy.sh" service "$image" 2>&1 | commands
echo
echo "# infra/deploy.sh rollback REVISION"
"$INFRA/deploy.sh" rollback REVISION 2>&1 | commands
echo
echo "# ENV_FILE for the service: infra/cloudrun/env.yaml plus what deploy.sh adds"
"$INFRA/deploy.sh" service "$image" 2>&1 | sed -n 's/^\[dry-run\]   //p'
