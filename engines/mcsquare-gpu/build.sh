#!/usr/bin/env bash
# build.sh — the MCsquare GPU transport prototype (engines/mcsquare-gpu/README.md): upstream's gcc branch at the
# commit engines/mcsquare-build uses, its four patches, then patches/0005 (the GPU path), built with gcc, oneMKL and
# nvcc. One binary: MCsquare's CPU path by default, the GPU path with MCSQUARE_GPU=1.
#
# Usage:  engines/mcsquare-gpu/build.sh [OUT]      (default OUT: engines/mcsquare-gpu/MCsquare_gpu, not committed)
#         NVFLAGS=--use_fast_math engines/mcsquare-gpu/build.sh    (the fast-math variant, see the README)
# Needs:  git, gcc with OpenMP, g++, python3 with venv, CUDA (nvcc; CUDA_HOME, default /usr/local/cuda), network.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REC="${HERE}/../mcsquare-build"
OUT="${1:-${HERE}/MCsquare_gpu}"
case "${OUT}" in /*) ;; *) OUT="$(pwd)/${OUT}" ;; esac
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
UPSTREAM_COMMIT="$(awk -F'"' '/^UPSTREAM_COMMIT=/{print $2}' "${REC}/build.sh")"
MKL_VERSION="$(awk -F'"' '/^MKL_VERSION=/{print $2}' "${REC}/build.sh")"
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
git clone -q https://gitlab.com/openmcsquare/MCsquare.git "${TMP}/src"
git -C "${TMP}/src" checkout -q "${UPSTREAM_COMMIT}"
for p in "${REC}"/patches/*.patch "${HERE}"/patches/*.patch; do git -C "${TMP}/src" apply --whitespace=nowarn "$p"; done
python3 -m venv "${TMP}/mkl"
"${TMP}/mkl/bin/pip" install -q "mkl-static==${MKL_VERSION}" "mkl-include==${MKL_VERSION}"
M="${TMP}/mkl"; mkdir -p "${TMP}/obj"
CF="-std=gnu99 -D_GNU_SOURCE -DUSE_MKL_LIB=1 -I${M}/include -fopenmp -w -O3 -march=x86-64-v3 -ffast-math -fno-finite-math-only"
for f in "${TMP}"/src/src/*.c; do gcc ${CF} -c "$f" -o "${TMP}/obj/$(basename "${f%.c}").o" & done; wait
"${CUDA_HOME}/bin/nvcc" -O3 -arch=sm_80 -lineinfo ${NVFLAGS:-} -c "${TMP}/src/src/gpu_transport.cu" -o "${TMP}/obj/gpu_transport.o"
mkdir -p "$(dirname "${OUT}")"
g++ "${TMP}"/obj/*.o -fopenmp -Wl,--start-group "${M}/lib/libmkl_gf_lp64.a" "${M}/lib/libmkl_sequential.a" \
  "${M}/lib/libmkl_core.a" -Wl,--end-group -L"${CUDA_HOME}/lib64" -lcudart_static -lpthread -lm -ldl -lrt -o "${OUT}"
echo "==> ${OUT}"
