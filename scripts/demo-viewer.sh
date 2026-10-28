#!/usr/bin/env bash
# The viewer demo on the Docker Compose stack: the bundled phantom (CT and structure set) into the stack's Orthanc, a
# plan made by the shipped demo protocol (5-field IMRT, radiarch's pencil-beam engine) inside the API container, its RT
# objects pushed to Orthanc, and the link that opens them in the viewer. Research use only; not for clinical use.
#
#   docker compose --profile viewer up -d --build     # first: the stack with the viewer
#   ./scripts/demo-viewer.sh                          # then: about two minutes
#
# Environment: VIEWER_URL (default http://localhost:3000), SPACING_MM (dose grid, default 4), NEW_EXPORT (1: push the
# plan's RT objects as a marked copy, "copy N", instead of the objects pushed before; README, "Exporting a plan again").
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VIEWER_URL="${VIEWER_URL:-http://localhost:3000}"
SPACING_MM="${SPACING_MM:-4}"

echo "RESEARCH USE ONLY. NOT FOR CLINICAL USE."
echo "1) the phantom's CT and structure set into the stack's Orthanc"
STUDY="$(./scripts/load-phantom.sh | tail -n 1)"
echo "   study ${STUDY}"

NEW_EXPORT_ARG=""
if [[ "${NEW_EXPORT:-0}" == "1" ]]; then NEW_EXPORT_ARG="--new-export"; fi

echo "2) a plan with the demo protocol, its RT objects pushed to Orthanc (a minute or two)"
docker compose exec -T api radiarch plan --server http://localhost:8000/api/v1 --protocol demo-phantom-imrt \
  --study "${STUDY}" --spacing "${SPACING_MM}" --push --poll 1 ${NEW_EXPORT_ARG}

echo
echo "3) open the plan review in Chrome or Firefox:"
echo "   ${VIEWER_URL}/plan-review?StudyInstanceUIDs=${STUDY}"
