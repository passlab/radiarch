# ADR 0011 — Clinical goals, radiobiology, interpolated gamma, dose-impact comparison

Date: 2026-10-21. Status: accepted. Roadmap R5 ("Evaluation").

## Context

The evaluation reported DVH curves, three target indices and a brute-force
gamma that searched voxel centres only (30 % against pymedphys's 56 % on
a borderline case, R7a). There were no clinical goals with pass or fail,
no biological models, no equivalent dose, and no first-class comparison
of two evaluations, which the SMIS commissioning harness (`dvh_impact`,
B2 Levels 2 and 3) needs.

## Decisions

1. **Clinical goals** are TG-263 style DVH statements (`D95%[Gy] >= 57`,
   `V20Gy[%] <= 37`, `D0.03cc[Gy] <= 50.5`, `Dmean[Gy] < 20`,
   `D1500cc[Gy] <= 11.6`, `V95%[%] >= 95`) with a priority (1 must, 2
   should, 3 would like) and a source. Templates ship in
   `radiarch/goals/`: RTOG 0617, QUANTEC (EQD2), TG-101 SBRT in 3 and 5
   fractions, NCCN / RTOG 1016 head and neck, and a PENTEC pediatric set
   marked **provisional**. Every template is a transcription of a published
   table and says so; the PI or a physicist checks each value against the
   source before it is used as an answer key. Goal structures are resolved
   against the geometry by name, by the template's aliases, by a
   case-insensitive match, or by the request's own mapping; a goal whose
   structure is missing is reported, not failed. With scenario doses every
   goal also reports its worst value and whether it holds in every scenario.
2. **Radiobiology**: EQD2 and BED per voxel (`fractions` on the request),
   gEUD, the LKB NTCP model with twelve parameter sets (QUANTEC lung,
   esophagus, parotid, rectum; Burman 1991; Martel 1998; Dawson 2002) and a
   Poisson TCP with three (Martel 1999 NSCLC, Levegrün 2001 prostate,
   Okunieff 1995 head and neck), each with its source. EQD2 applies when the
   fractions are given, with α/β per structure (request or defaults by
   structure type). These are literature reference points, not a
   commissioning.
3. **Gamma** evaluates on the reference points and searches the evaluated
   dose **interpolated** on a sub-voxel grid (five steps per DTA, within
   twice the DTA), vectorized with an early stop when the distance term
   alone exceeds the worst remaining value. On the harness's synthetic case
   it gives 56.2 % where pymedphys gives 56 % and the old search gave 30 %.
   pymedphys stays the cross-check (`validation/run.py`, run with uv under
   Python 3.12), not a runtime dependency.
4. **Comparison** (`POST /evaluate/compare`): two evaluations, run or
   reused by id — the same dose on two structure sets or two doses on one
   geometry — give per-structure DVH metric differences, index differences
   and the goals that changed state. This is `dvh_impact` for the A2/B2
   harness.

## Consequences

- An evaluation request may carry `goals`, `ntcp`, `tcp` and `fractions`;
  the result carries `goals` (a report with counts by priority and a robust
  verdict), `ntcp` and `tcp`. The cache key includes them.
- The goal templates are data: adding a site or protocol is a JSON file.
- Not done here: NTCP models beyond LKB (e.g. relative seriality), the
  LQ-L model for SBRT equivalent doses, clinical-goal priorities as
  optimizer constraints (that is the planning protocol of R10), a
  structure-set comparison with Dice and surface distances (A2's own).
