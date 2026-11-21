#!/usr/bin/env bash
# build-in-docker.sh — build engines/mcsquare/MCsquare_gpu in ubuntu:22.04 with CUDA 12.6's compiler and runtime
# from NVIDIA's apt repository, as the image does: glibc 2.35, so that it runs in the python:3.12-slim image, and
# only nvcc, the CUDA runtime and Thrust's headers (about 0.5 GB, not the multi-GB CUDA images). Needs docker and
# network; no GPU. ADR 0024.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker run --rm -v "${REPO}:/w" -w /w -e NVFLAGS="${NVFLAGS:-}" ubuntu:22.04 bash -c "
    set -e
    engines/mcsquare-gpu/install-cuda.sh
    CUDA_HOME=/usr/local/cuda-12.6 engines/mcsquare-gpu/build.sh
    chown $(id -u):$(id -g) engines/mcsquare/MCsquare_gpu"
