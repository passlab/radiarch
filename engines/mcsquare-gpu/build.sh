#!/usr/bin/env bash
# build.sh — MCsquare_gpu, radiarch's MCsquare with the CUDA transport (engines/mcsquare-gpu/README.md, ADR 0024):
# upstream's gcc branch at the commit engines/mcsquare-build uses, its patches (0001-0005), then patches/0006-0008
# (the GPU path), built with gcc, oneMKL and nvcc. One binary: MCsquare's CPU path by default, the GPU path with
# MCSQUARE_GPU=1 (radiarch's driver sets it for mcsquare_device=gpu; its CPU runs use MCsquare_radiarch).
#
# Usage:  engines/mcsquare-gpu/build.sh [OUT]            (default OUT: engines/mcsquare/MCsquare_gpu, not committed)
#         engines/mcsquare-gpu/build-in-docker.sh        (the same in CUDA 12.6 on ubuntu:22.04, as the image builds it)
#         NVFLAGS=--use_fast_math engines/mcsquare-gpu/build.sh    (the fast-math variant, see the README)
# Code:   SASS for compute capability 8.0 (A100; also runs on 8.6 and 8.9) and PTX for 8.0, which the driver
#         compiles for newer GPUs on first use. Override with GENCODE.
# Links:  oneMKL, libgomp, libstdc++ and the CUDA runtime statically; needs glibc (2.35 or newer for the docker build)
#         and, at run time, the NVIDIA driver (libcuda, R525 or newer for CUDA 12).
# Needs:  git, gcc and g++ with OpenMP (libgomp.a), python3 with venv, CUDA (nvcc; CUDA_HOME, default
#         /usr/local/cuda), network for the clone and the wheels.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REC="${HERE}/../mcsquare-build"
OUT="${1:-${HERE}/../mcsquare/MCsquare_gpu}"
case "${OUT}" in /*) ;; *) OUT="$(pwd)/${OUT}" ;; esac
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
GENCODE="${GENCODE:--gencode arch=compute_80,code=[sm_80,compute_80]}"
UPSTREAM_COMMIT="$(awk -F'"' '/^UPSTREAM_COMMIT=/{print $2}' "${REC}/build.sh")"
MKL_VERSION="$(awk -F'"' '/^MKL_VERSION=/{print $2}' "${REC}/build.sh")"
for tool in git gcc g++ python3 "${CUDA_HOME}/bin/nvcc"; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }
done
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT

echo "==> MCsquare ${UPSTREAM_COMMIT}"
git clone -q https://gitlab.com/openmcsquare/MCsquare.git "${TMP}/src"
git -C "${TMP}/src" checkout -q "${UPSTREAM_COMMIT}"
echo "==> Patches"
for p in "${REC}"/patches/*.patch "${HERE}"/patches/*.patch; do
  echo "    $(basename "$p")"
  git -C "${TMP}/src" apply --whitespace=nowarn "$p"
done

echo "==> oneMKL ${MKL_VERSION} (static, from PyPI)"
python3 -m venv "${TMP}/mkl"
"${TMP}/mkl/bin/pip" install -q "mkl-static==${MKL_VERSION}" "mkl-include==${MKL_VERSION}"
M="${TMP}/mkl"; mkdir -p "${TMP}/obj"

echo "==> gcc $(gcc -dumpfullversion), $("${CUDA_HOME}/bin/nvcc" --version | tail -1)"
CF="-std=gnu99 -D_GNU_SOURCE -DUSE_MKL_LIB=1 -I${M}/include -fopenmp -w -O3 -march=x86-64-v3 -ffast-math -fno-finite-math-only"
for f in "${TMP}"/src/src/*.c; do gcc ${CF} -c "$f" -o "${TMP}/obj/$(basename "${f%.c}").o" & done; wait
# shellcheck disable=SC2086
"${CUDA_HOME}/bin/nvcc" -O3 ${GENCODE} -lineinfo ${NVFLAGS:-} -c "${TMP}/src/src/gpu_transport.cu" -o "${TMP}/obj/gpu_transport.o"
mkdir -p "$(dirname "${OUT}")"
OBJS="$(cd "${TMP}/obj" && LC_ALL=C ls ./*.o | sed "s#^\./#${TMP}/obj/#")"
# shellcheck disable=SC2086
g++ ${OBJS} -static-libstdc++ -static-libgcc "$(gcc -print-file-name=libgomp.a)" \
  -Wl,--start-group "${M}/lib/libmkl_gf_lp64.a" "${M}/lib/libmkl_sequential.a" "${M}/lib/libmkl_core.a" -Wl,--end-group \
  -L"${CUDA_HOME}/lib64" -lcudart_static -lpthread -lm -ldl -lrt -s -o "${OUT}"
chmod 755 "${OUT}"
echo "==> ${OUT}"
echo "    sha256 $(sha256sum "${OUT}" | cut -d' ' -f1)"
echo "    needs: $(ldd "${OUT}" | awk '{print $1}' | tr '\n' ' ')"
