# OpenTPS Attribution

This directory contains a vendored copy of **OpenTPS Core** (v3.0.0), an open-source
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

## Modifications

This vendored copy has been modified from the original:

- Removed `opentps_gui` package (not needed for headless service)
- Removed non-Linux MCsquare binaries (Windows, Mac executables)
- Removed Windows DLLs from C libraries and photon dose engine
- Removed `__pycache__` directories
