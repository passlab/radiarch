"""Radiarch service layer.

Each service converts one well-defined input to one well-defined output
and is fully usable in isolation (no implicit coupling to plans or jobs).

Services:
  geometry.GeometryService         — Raw DICOM (CT + RTSTRUCT) → voxel model.
  beam_model.BeamModelService      — Beam set spec → proton spots / photon beamlets.
  dose.DoseService                 — Geometry + beam model → dose, Dij, scenarios.
  optimization.OptimizationService — Objectives + Dij → optimal fluence weights.
  bao.BAOService                   — Candidate angles → selected beam directions.
  evaluation.EvaluationService     — Dose + masks → DVH, indices, gamma report.
"""
