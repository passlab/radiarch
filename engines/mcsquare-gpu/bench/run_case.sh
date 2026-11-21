#!/usr/bin/env bash
# run_case.sh CASE MODE(cpu|gpu) TAG [PRIMARIES] [SEED]: one run of the prototype on INPUTS/CASE (prepare_inputs.py)
#   NUCLEAR=1 switches nuclear interactions on (both paths have issue #42's fix since mcsquare-build's patch 0005)
#   BIN (the prototype), INPUTS, RUNS and MATERIALS (engines/mcsquare/Materials) from the environment.
set -u
C=$1; MODE=$2; TAG=$3
W=${RUNS}/$C-$TAG; mkdir -p "${RUNS}"; rm -rf "$W"; cp -r "${INPUTS}/$C" "$W"
orig=$(dirname "$(awk '$1 == "CT_File" {print $2}' "$W/config.txt")")
sed -i "s#${orig}#$W#g" "$W/config.txt"
[ -n "${4:-}" ] && sed -i "s#^Num_Primaries.*#Num_Primaries $4#" "$W/config.txt"
[ -n "${5:-}" ] && sed -i "s#^RNG_Seed.*#RNG_Seed $5#" "$W/config.txt"
ln -s "${MATERIALS}" "$W/Materials"     # a short name: MCsquare's file-name buffers are 100 bytes (ADR 0023)
[ "${NUCLEAR:-0}" = 1 ] && sed -i "s#^Simulate_Nuclear_Interactions.*#Simulate_Nuclear_Interactions True#" "$W/config.txt"
cd "$W"
s=$(date +%s%N)
if [ "$MODE" = gpu ]; then MCSQUARE_GPU=1 MCsquare_Materials_Dir=Materials "${BIN}" config.txt > run.log 2>&1
else MCsquare_Materials_Dir=Materials "${BIN}" config.txt > run.log 2>&1; fi
rc=$?; e=$(date +%s%N)
echo "$C $MODE $TAG rc=$rc wall=$(( (e - s) / 1000000 )) ms | $(grep -h "GPU prototype" run.log | sed 's/GPU prototype: //')"
