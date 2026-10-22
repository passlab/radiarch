# Validation record R7, 2026-10-22: guide for the reviewing physicist

Radiarch is a research treatment-planning system. These documents record how its dose
engines and evaluation services compare with independent references and with the
commissioning literature. **They are research evidence, not a clinical commissioning:
radiarch is not for clinical use, and signing records a review of research evidence,
not a clinical release.**

All documents in this folder come from one full run of the validation harness on a
clean commit, `20261022-150018-20fc3bf` at commit `20fc3bf`. Every check in them names its target and
its source; ADR 0014 (`docs/adr/0014-validation-report.md`) gives the decisions behind
the cases and the findings in prose.

## What to review and sign

| Document | Contents | Signed by |
|---|---|---|
| [`2026-10-22-ccc-v1.0.0-20fc3bf.md`](2026-10-22-ccc-v1.0.0-20fc3bf.md) | Photon engine (WiscPlan collapsed-cone convolution, radiarch build): water depth dose, profile and penumbra against representative 6 MV data; depth dose, profile, gamma and heterogeneity correction factors (lung and bone slabs) against a Monte Carlo reference; influence matrix against forward dose; the four AAPM TG-119 cases planned and scored; an end-to-end lung case on public CT data | medical physicist and project lead |
| [`2026-10-22-mcsquare-v0.3.0-20fc3bf.md`](2026-10-22-mcsquare-v0.3.0-20fc3bf.md) | Proton engine (MCsquare, radiarch driver): R80 against NIST PSTAR, distal fall-off against range straggling, spot size against the beam model, influence matrix against forward dose | medical physicist and project lead |
| [`2026-10-22-services-v0.1.0-20fc3bf.md`](2026-10-22-services-v0.1.0-20fc3bf.md) | Engine-independent services: DVH against dicompyler-core, gamma against pymedphys, structure volumes against the contour polygons | project lead (a physicist's look is welcome) |

`run-summary.md` lists every check of the run in one table, and `results.json` holds the
run's full numbers (profiles, depth doses, per-structure values) as the harness wrote them.

## Questions we would most like answered

1. **The Monte Carlo reference.** OpenGATE 10.1.1 (Geant4), the Mohan 6 MV spectrum (the
   spectrum the CCC kernels were built from) as a point source collimated by the Elekta
   Versa HD jaws and MLC, no flattening filter or head scatter, slabs of water at lung
   (0.26 g/cm³) and bone (1.85 g/cm³) density, electron steps limited to 0.5 mm and a
   0.1 mm production cut, 5×10⁷ primaries (1.3–2.2 % per voxel on the axis). Is this an
   acceptable reference for testing transport in the phantom? Should a full head model or
   real tissue compositions be used instead? (`src/radiarch/validation/mc_reference.py`,
   ADR 0014 "Findings".) The next roadmap item fits a native photon engine to this
   reference, so an early answer here helps most.
2. **The tolerances.** In-field 2 % and heterogeneity 3 % (AAPM MPPG 5.a/5.b, IAEA
   TECDOC-1583), gamma 3 %/3 mm with a 95 % pass rate, proton R80 within 1 % + 1 mm,
   TG-119 goals with the published multi-institution mean ± 2 SD as the acceptance band
   for goals the participants did not meet on average. Are these the right targets for a
   research system?
3. **The CCC findings.** The engine matches the Monte Carlo reference in water to 15 cm
   (PDD10 68.1 % against 68.0 %, gamma 98 %) and behind bone (within 3 %), but falls off
   too fast beyond 15 cm (7 % low at 25 cm) and is about 5 % off in and far behind lung.
   Does this match your experience of collapsed-cone engines with generic kernels, and
   is the stated limitation adequate for research use?
4. **Anything you would add**: cases, phantoms or references a commissioning physicist
   would expect to see.

## How to sign

Either reply to the covering email with your comments and a statement that you reviewed
the named documents at commit `20fc3bf`, which we then record in the signature table
of each document with the date and a reference to your email; or print the signature
section of a document, sign and date it, and return a scan. Comments that lead to
changes produce a new run and new documents; a signature always refers to one commit.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 20fc3bf
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
# the engines (MCsquare binaries and data, the CCC build and kernels) are in the repository under engines/
.venv/bin/python -m radiarch.validation.run --all --fast    # smoke run; full mode drops --fast
.venv/bin/python -m radiarch.validation.report              # documents from the newest run
# one Monte Carlo reference (about 100 minutes on 18 threads)
uv run --no-project --python 3.12 --with opengate==10.1.1 --with itk \
  python -m radiarch.validation.mc_reference --case water_10x10 --primaries 5e7
```

The cases on public patient data (LCTSC, Pancreatic-CT-CBCT-SEG, the TG-119 package) read
them from a data directory outside the repository, `RADIARCH_VALIDATION_DATA` (default
`../data/public`); without them those cases are skipped. pymedphys and
dicompyler-core run in their own Python 3.12 environments through `uv`.
