"""Validation harness (roadmap R7a): phantoms, reference data with citations,
case definitions and a runner that writes a dated results folder.

This is not the unit-test suite. Cases take seconds to hours, need the engine
binaries and, for some, public data in ``RADIARCH_VALIDATION_DATA`` (default ``../data/public``). Run::

    python -m radiarch.validation.run --list
    python -m radiarch.validation.run --cases photon_pdd_10x10 photon_profile_10x10
    python -m radiarch.validation.run --all --out validation/results

Results are research targets against the commissioning literature (MPPG 5.a/5.b,
TG-119, TG-218, TECDOC-1583, TG-185); they never constitute a clinical commissioning.
"""
