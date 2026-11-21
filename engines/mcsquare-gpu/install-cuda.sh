#!/usr/bin/env bash
# install-cuda.sh — what engines/mcsquare-gpu/build.sh needs on ubuntu:22.04 (as root): gcc, g++, git, python3 with
# venv, and from NVIDIA's apt repository CUDA 12.6's nvcc, runtime (static library), Thrust/CUB and cuRAND
# headers, into /usr/local/cuda-12.6. Used by build-in-docker.sh and the image's build stage.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends gcc g++ libc6-dev git python3 python3-venv ca-certificates wget >/dev/null
wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -O /tmp/cuda-keyring.deb
dpkg -i /tmp/cuda-keyring.deb >/dev/null
rm /tmp/cuda-keyring.deb
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends cuda-nvcc-12-6 cuda-cudart-dev-12-6 cuda-cccl-12-6 libcurand-dev-12-6 >/dev/null
rm -rf /var/lib/apt/lists/*
/usr/local/cuda-12.6/bin/nvcc --version | tail -1
