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

export DRY_RUN=1 GITHUB_ACTIONS=true GITHUB_SHA=COMMIT_SHA OWNER_EMAILS=owner@example.com
echo "# infra/bootstrap.sh"
"$INFRA/bootstrap.sh" --dry-run 2>&1 | commands
echo
echo "# infra/deploy.sh migrate IMAGE"
"$INFRA/deploy.sh" migrate "$image" 2>&1 | commands
echo
echo "# infra/deploy.sh service IMAGE"
"$INFRA/deploy.sh" service "$image" 2>&1 | commands
echo
echo "# infra/deploy.sh access (API_ACCESS=private removes the same binding instead)"
"$INFRA/deploy.sh" access 2>&1 | commands
echo
echo "# infra/deploy.sh models"
"$INFRA/deploy.sh" models 2>&1 | commands
echo
echo "# infra/deploy.sh covers"
"$INFRA/deploy.sh" covers 2>&1 | commands
echo
echo "# infra/deploy.sh upload-apk APK (BUILD_NUMBER=42, VERSION_NAME=1.0.0)"
printf 'apk\n' >"$ROOT/lucid-saga.apk.print-commands"
BUILD_NUMBER=42 VERSION_NAME=1.0.0 "$INFRA/deploy.sh" upload-apk "$ROOT/lucid-saga.apk.print-commands" 2>&1 |
  commands | sed 's#lucid-saga.apk.print-commands#APK#; s#/[^ ]*/latest.json gs://#MANIFEST gs://#'
rm -f "$ROOT/lucid-saga.apk.print-commands"
echo
echo "# infra/deploy.sh rollback REVISION"
"$INFRA/deploy.sh" rollback REVISION 2>&1 | commands
echo
echo "# ENV_FILE for the service: infra/cloudrun/env.yaml plus what deploy.sh adds"
"$INFRA/deploy.sh" service "$image" 2>&1 | sed -n 's/^\[dry-run\]   //p'
