"""Radiarch service layer.

Each service converts one well-defined input to one well-defined output
and is fully usable in isolation (no implicit coupling to plans or jobs).

Services:
  geometry.GeometryService — Raw DICOM (CT + RTSTRUCT) → voxel model.

Future services (dose, optimization, robustness, simulation) land here.
"""
