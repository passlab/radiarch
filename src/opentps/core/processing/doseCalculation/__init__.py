"""Dose calculation submodules.

This package marker exists to make ``opentps.core.processing.doseCalculation``
importable as a proper Python package — without it the
``protons.MCsquare`` subpackage can't be resolved, which breaks
``radiarch.services.machine_model._default_mcsquare_path``.

Empty by design: all functionality lives in the submodules.
"""
