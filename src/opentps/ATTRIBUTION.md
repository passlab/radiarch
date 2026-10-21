# OpenTPS Attribution

This directory contains a vendored copy of **OpenTPS Core** (v3.0.1), an open-source
treatment planning system for advanced proton therapy.

## License

OpenTPS is licensed under the **Apache License 2.0**. A copy of the license
is included in `LICENSE`.

## Original Repository

- **GitLab**: https://gitlab.com/openmcsquare/opentps
- **Website**: http://opentps.org/

## Citation

If you use OpenTPS in a scientific publication, please cite:

```bibtex
@misc{wuyckens2023opentps,
  title={OpenTPS -- Open-source treatment planning system for research in proton therapy},
  author={S. Wuyckens and D. Dasnoy and G. Janssens and V. Hamaide and M. Huet
          and E. Lo\"{y}en and G. Rotsart de Hertaing and B. Macq and E. Sterpin
          and J. A. Lee and K. Souris and S. Deffet},
  year={2023},
  eprint={2303.00365},
  archivePrefix={arXiv},
  primaryClass={physics.med-ph}
}
```

## License of the photon engine

`core/processing/doseCalculation/photons/CCC_DoseEngine` (the WiscPlan collapsed-cone
code and its binary) is GPLv2, as stated in `LICENSE`. Radiarch only runs it as a
separate subprocess over files, never links or imports it.

## Modifications

This vendored copy is produced by `scripts/vendor-opentps.sh <tag>`, which:

- exports `opentps_core/opentps/core` and `LICENSE` at the given tag (the GUI package
  is not vendored; it is GPLv3 and not needed by a headless service)
- removes non-Linux binaries (Windows `.exe`/`.bat`/`.dll`, macOS `MCsquare_mac`,
  `lib_mac`) and `__pycache__` directories
- applies `patches/radiarch-local.patch`: `scipy.interpolate` import fixes and an
  `np.interp`-based HU→density conversion (scipy ≥ 1.14), a voxel-index clip in
  `Image3D`, quieter and more complete `serializedObjectIO.unDictionarize`, a POSIX
  `MCsquare` launcher, a numpy ≥ 1.24 fix in `_DFallOff`, and package markers for
  `processing/doseCalculation` and `processing/doseCalculation/protons`
- adds `Scanners/default` as a copy of `Scanners/UCL_Toshiba`

To update: run the script with the new tag, then `scripts/install-dev.sh` and
`pytest tests/opentps`. If a hunk fails to apply, regenerate the patch against the
new upstream version.
