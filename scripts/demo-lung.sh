#!/usr/bin/env bash
# The lung demo on the Docker Compose stack: a public lung-cancer patient from The Cancer Imaging Archive (a planning
# CT with the tumour, GTV-1, and the organs contoured by the clinic) into the stack's Orthanc, a plan made by the
# shipped demo-lung-imrt protocol (CTV and PTV grown from the GTV, 60 Gy in 30 fractions, seven IMRT fields on
# radiarch's pencil-beam engine, RTOG 0617 dose limits) inside the API container, its RT objects pushed to Orthanc,
# and the link that opens them in the viewer: contours, the dose colour wash and the DVHs. Research use only.
#
#   docker compose --profile viewer up -d --build     # first: the stack with the viewer
#   ./scripts/demo-lung.sh                            # then: a ~60 MB download and some minutes of planning
#
# Environment: PATIENT (default LUNG1-002), COLLECTION (default NSCLC-Radiomics), VIEWER_URL (default
# http://localhost:3000), SPACING_MM (dose grid, default 4), PROTOCOL (default demo-lung-imrt; lung-60gy-30fx-vmat
# plans two VMAT arcs in about twenty minutes). NSCLC-Radiomics is CC BY-NC 3.0: non-commercial use, with its
# citation (docs/demo.md). The download is kept in the stack's artifact volume, not in this repository.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PATIENT="${PATIENT:-LUNG1-002}"
COLLECTION="${COLLECTION:-NSCLC-Radiomics}"
VIEWER_URL="${VIEWER_URL:-http://localhost:3000}"
SPACING_MM="${SPACING_MM:-4}"
PROTOCOL="${PROTOCOL:-demo-lung-imrt}"

echo "RESEARCH USE ONLY. NOT FOR CLINICAL USE."
echo "1) ${COLLECTION} ${PATIENT} (CT and structure set) from TCIA into the stack's Orthanc"
STUDY="$(docker compose exec -T api radiarch fetch-tcia --collection "${COLLECTION}" --patient "${PATIENT}" \
  --cache /data/artifacts/tcia --push | tail -n 1)"
echo "   study ${STUDY}"

echo "2) a plan with ${PROTOCOL}, its RT objects pushed to Orthanc (minutes: each planning round is printed)"
docker compose exec -T api radiarch plan --server http://localhost:8000/api/v1 --protocol "${PROTOCOL}" \
  --study "${STUDY}" --spacing "${SPACING_MM}" --push --poll 2

echo
echo "3) open the plan review in Chrome or Firefox:"
echo "   ${VIEWER_URL}/plan-review?StudyInstanceUIDs=${STUDY}"
