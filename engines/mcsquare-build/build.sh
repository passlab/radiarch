#!/usr/bin/env bash
# build.sh — build engines/mcsquare/MCsquare_radiarch from upstream's source with radiarch's patches (ADR 0023).
#
# Upstream:  https://gitlab.com/openmcsquare/MCsquare, branch gcc (MKL optional, Cilk array notation replaced by
#            OpenMP SIMD loops so that gcc compiles it), commit UPSTREAM_COMMIT below. Apache-2.0.
# Patches:   patches/0001-*.patch .. (git format-patch; each says what it changes and why).
# Compiler:  gcc with OpenMP; static, so that the binary runs in the python:3.12-slim image, which has no libgomp;
#            stripped. x86-64-v3 (AVX2, FMA); fast math but finite-math kept, so that patch 0003's isfinite guard
#            stays (-ffinite-math-only would fold it away); link-time optimization. About 1.25x the time of the
#            Intel build OpenTPS ships (ADR 0023).
# RNG:       Intel oneMKL's VSL (MCG59), as in the binaries OpenTPS ships, from the mkl-static and mkl-include
#            wheels on PyPI (Intel Simplified Software License; ../mcsquare/LICENSE-oneMKL*.txt).
#
# Usage:     engines/mcsquare-build/build.sh [OUT]       (default OUT: engines/mcsquare/MCsquare_radiarch)
#            engines/mcsquare-build/build-in-docker.sh   (the same, in ubuntu:24.04: the toolchain of record)
#            The build is reproducible bit for bit on one toolchain; it ends by comparing the binary's sha256
#            with BUILD.txt, and with RADIARCH_MCSQUARE_EXPECT_RECORD=1 (CI, the image) a difference fails it.
# Needs:     git, gcc with OpenMP and its static libraries (libgomp.a), python3 with venv, network for the clone
#            and the wheels. Built for the record on Ubuntu 24.04 with gcc 13.3 (BUILD.txt).
# Afterwards: pytest tests/test_engine_assets.py tests/test_mcsquare_driver.py

set -euo pipefail

UPSTREAM="https://gitlab.com/openmcsquare/MCsquare.git"
UPSTREAM_COMMIT="3ed27f5773ccedd1352245018e8d48898a4b0f23"     # branch gcc, 2024-11-04, "Fix merge errors"
MKL_VERSION="2024.2.2"
# The sources in a fixed order: the link order sets the binary's layout, and the layout sets what upstream's
# overrunning reads find past the nuclear tables (ADR 0023) - a shell glob would sort by the locale.
SOURCES=(compute_4D.c compute_beam_model.c compute_DVH.c compute_EM_interaction.c compute_Fippel.c
  compute_geometry.c compute_hadron.c compute_math.c compute_nuclear_interaction.c compute_random.c
  compute_range_shifter.c compute_scenario_simulation.c compute_scoring.c compute_semi_infinite_slab.c
  compute_simulation_beamlet.c compute_simulation.c compute_treatment_uncertainties.c data_4D.c data_ascii.c
  data_beam_model.c data_config.c data_contours.c data_ct.c data_ct_mhd.c data_ct_penelope.c data_materials.c
  data_mhd.c data_nuclear.c data_sparse.c data_Stop_Pow.c File_process.c main.c struct.c)
CFLAGS="-std=gnu99 -D_GNU_SOURCE -DUSE_MKL_LIB=1 -fopenmp -w -O3 -march=x86-64-v3 -ffast-math -fno-finite-math-only -flto=auto"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-${HERE}/../mcsquare/MCsquare_radiarch}"
case "${OUT}" in /*) ;; *) OUT="$(pwd)/${OUT}" ;; esac
mkdir -p "$(dirname "${OUT}")"

for tool in git gcc python3; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "==> MCsquare ${UPSTREAM_COMMIT}"
git clone -q "${UPSTREAM}" "${TMP}/src"
git -C "${TMP}/src" checkout -q "${UPSTREAM_COMMIT}"
echo "==> Patches"
for p in "${HERE}"/patches/*.patch; do
  echo "    $(basename "$p")"
  git -C "${TMP}/src" apply --whitespace=nowarn "$p"
done

missing="$(comm -3 <(printf '%s\n' "${SOURCES[@]}" | LC_ALL=C sort) <(cd "${TMP}/src/src" && LC_ALL=C ls *.c))"
[ -z "${missing}" ] || { echo "the source list and src/*.c differ: ${missing}" >&2; exit 2; }

echo "==> oneMKL ${MKL_VERSION} (static, from PyPI)"
python3 -m venv "${TMP}/mkl"
"${TMP}/mkl/bin/pip" install -q "mkl-static==${MKL_VERSION}" "mkl-include==${MKL_VERSION}"
M="${TMP}/mkl"

echo "==> gcc $(gcc -dumpfullversion)"
# shellcheck disable=SC2086
gcc "${SOURCES[@]/#/${TMP}/src/src/}" ${CFLAGS} -I"${M}/include" -static \
  -Wl,--start-group "${M}/lib/libmkl_gf_lp64.a" "${M}/lib/libmkl_sequential.a" "${M}/lib/libmkl_core.a" -Wl,--end-group \
  -lpthread -lm -ldl -s -o "${OUT}" 2> >(grep -v -e "dlopen' in statically linked" -e "in function \`mm_init'" >&2)
chmod 755 "${OUT}"

echo "==> ${OUT}"
SHA="$(sha256sum "${OUT}" | cut -d' ' -f1)"
RECORD="$(awk '$1 == "sha256" {print $2}' "${HERE}/BUILD.txt")"
echo "    sha256 ${SHA}"
if [ "${SHA}" = "${RECORD}" ]; then
  echo "    the build of record (BUILD.txt)"
else
  echo "    differs from the build of record ${RECORD} (BUILD.txt): another toolchain, or a changed recipe." >&2
  echo "    A different binary can change doses (ADR 0023): run the proton validation cases before using it." >&2
  if [ "${RADIARCH_MCSQUARE_EXPECT_RECORD:-0}" = "1" ]; then exit 3; fi
fi
