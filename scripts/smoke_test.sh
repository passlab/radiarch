#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000/api/v1}"

echo "Radiarch smoke test"
echo "API_BASE_URL=${API_BASE_URL}"
echo

echo "1) GET /info"
curl -fsS "${API_BASE_URL}/info" | python3 -m json.tool >/dev/null
echo "   OK"
echo

echo "2) POST /plans (create a minimal plan)"
CREATE_RESP="$(
  curl -fsS "${API_BASE_URL}/plans" \
    -H "Content-Type: application/json" \
    -d '{
      "workflow_id": "proton-impt-basic",
      "study_instance_uid": "1.2.826.0.1.3680043.8.1055.1",
      "prescription_gy": 2.0,
      "beam_count": 3,
      "fraction_count": 1,
      "notes": "smoke-test"
    }'
)"
export CREATE_RESP
PLAN_ID="$(python3 - <<'PY'
import json, os, sys
data = json.loads(os.environ["CREATE_RESP"])
print(data["id"])
PY
)"
JOB_ID="$(python3 - <<'PY'
import json, os, sys
data = json.loads(os.environ["CREATE_RESP"])
print(data.get("job_id") or "")
PY
)"
echo "   plan_id=${PLAN_ID}"
echo "   job_id=${JOB_ID}"
echo

if [[ -z "${JOB_ID}" ]]; then
  echo "ERROR: plan response did not include job_id"
  exit 1
fi

echo "3) Poll /jobs/${JOB_ID} until terminal state"
terminal="succeeded failed cancelled"
state=""
for i in $(seq 1 180); do
  JOB_JSON="$(curl -fsS "${API_BASE_URL}/jobs/${JOB_ID}")"
  export JOB_JSON
  state="$(python3 - <<'PY'
import json, os
print(json.loads(os.environ["JOB_JSON"])["state"])
PY
)"
  progress="$(python3 - <<'PY'
import json, os
print(json.loads(os.environ["JOB_JSON"]).get("progress", 0.0))
PY
)"
  printf "   [%3s/180] state=%s progress=%s\r" "$i" "$state" "$progress"
  if [[ " ${terminal} " == *" ${state} "* ]]; then
    echo
    break
  fi
  sleep 1
done
echo "   final state=${state}"
echo

if [[ "${state}" != "succeeded" ]]; then
  echo "ERROR: job did not succeed (state=${state})"
  echo "Job payload:"
  echo "${JOB_JSON}" | python3 -m json.tool || true
  exit 1
fi

echo "4) GET /plans/${PLAN_ID} and check artifacts + qa_summary"
PLAN_JSON="$(curl -fsS "${API_BASE_URL}/plans/${PLAN_ID}")"
export PLAN_JSON
ARTIFACT_COUNT="$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["PLAN_JSON"])
print(len(data.get("artifact_ids") or []))
PY
)"
QA_ENGINE="$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["PLAN_JSON"])
qa = data.get("qa_summary") or {}
print(qa.get("engine") or "")
PY
)"
echo "   artifacts=${ARTIFACT_COUNT}"
echo "   qa_engine=${QA_ENGINE:-<none>}"
echo

if [[ "${ARTIFACT_COUNT}" -lt 1 ]]; then
  echo "ERROR: expected at least 1 artifact id on plan"
  echo "${PLAN_JSON}" | python3 -m json.tool || true
  exit 1
fi

ARTIFACT_ID="$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["PLAN_JSON"])
print((data.get("artifact_ids") or [""])[0])
PY
)"
echo "5) GET /artifacts/${ARTIFACT_ID} (download first artifact)"
TMP_OUT="$(mktemp -t radiarch_artifact.XXXXXX)"
curl -fsS "${API_BASE_URL}/artifacts/${ARTIFACT_ID}" -o "${TMP_OUT}"
echo "   downloaded=$(wc -c < "${TMP_OUT}") bytes to ${TMP_OUT}"
echo

echo "Smoke test succeeded."
