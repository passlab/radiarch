"""Unit tests for radiarch.services.beam_model.BeamModelService.

These tests stub out ``_load_geometry``, ``_load_machine_model``, and
the modality builders so the orchestrator runs end-to-end without
OpenTPS, without MCsquare, and without DICOM. We assert: cache lookup,
modality dispatch, persistence round-trip, validation errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from radiarch.models.beam_model import (
    BeamModelBuildRequest,
    BeamSetSpec,
    BeamSpec,
    DeliveryParams,
    FluenceElementSet,
    Modality,
    PerBeamElements,
)
from radiarch.services.beam_model import BeamModelService, _LoadedGeometry
from radiarch.services.machine_model import (
    PhotonMachineModel,
    ProtonMachineModel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(modality: Modality = Modality.proton_pbs, **overrides) -> BeamModelBuildRequest:
    base = dict(
        geometry_id="g-1",
        modality=modality,
        machine_model_id=None,
        beam_set=BeamSetSpec(
            isocenter_mm=(0, 0, 0),
            beams=[BeamSpec(beam_id="B1", gantry_deg=0)],
        ),
        delivery_params=DeliveryParams(),
    )
    base.update(overrides)
    return BeamModelBuildRequest(**base)


@dataclass
class _MockPlan:
    note: str = "mock plan"


def _stub_loaded_geometry() -> _LoadedGeometry:
    return _LoadedGeometry(
        geometry_id="g-1",
        ct=object(),
        patient=object(),
        target_contour=object(),
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

class TestProtonHappyPath:
    def test_builds_end_to_end(self, tmp_path: Path, monkeypatch):
        service = BeamModelService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load_geometry", lambda gid: _stub_loaded_geometry())

        # Stub the modality builder to return a deterministic result.
        from radiarch.services import beam_model as bm_module

        def _fake_proton(req, geom, mm):
            from radiarch.services.proton_spots import ProtonBuildResult
            return ProtonBuildResult(
                fluence_elements=FluenceElementSet(
                    total_count=15,
                    per_beam=[PerBeamElements(beam_id="B1", element_count=15,
                                              energy_layers=[100.0, 110.0],
                                              spots_per_layer=[7, 8])],
                ),
                plan=_MockPlan(note="proton"),
            )
        monkeypatch.setattr(BeamModelService, "_build_proton", staticmethod(_fake_proton))

        result = service.build(_request())
        assert result.modality is Modality.proton_pbs
        assert result.geometry_id == "g-1"
        assert result.fluence_elements.total_count == 15
        assert result.machine_model_id == "default"
        assert (tmp_path / result.beam_model_id / "plan.pkl").exists()
        assert (tmp_path / result.beam_model_id / "meta.json").exists()


class TestPhotonHappyPath:
    def test_builds_end_to_end(self, tmp_path: Path, monkeypatch):
        service = BeamModelService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load_geometry", lambda gid: _stub_loaded_geometry())

        def _fake_photon(req, geom, mm):
            from radiarch.services.photon_beamlets import PhotonBuildResult
            return PhotonBuildResult(
                fluence_elements=FluenceElementSet(
                    total_count=400,
                    per_beam=[PerBeamElements(beam_id="B1", element_count=400,
                                              grid_dims=(20, 20),
                                              active_beamlets=400)],
                ),
                plan=_MockPlan(note="photon"),
            )
        monkeypatch.setattr(BeamModelService, "_build_photon", staticmethod(_fake_photon))

        result = service.build(_request(modality=Modality.photon_imrt))
        assert result.modality is Modality.photon_imrt
        assert result.fluence_elements.per_beam[0].grid_dims == (20, 20)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_second_build_hits_cache(self, tmp_path: Path, monkeypatch):
        service = BeamModelService(base_dir=tmp_path)
        load_calls = {"n": 0}

        def _counting_load(gid):
            load_calls["n"] += 1
            return _stub_loaded_geometry()
        monkeypatch.setattr(service, "_load_geometry", _counting_load)

        def _fake_proton(req, geom, mm):
            from radiarch.services.proton_spots import ProtonBuildResult
            return ProtonBuildResult(
                fluence_elements=FluenceElementSet(
                    total_count=1,
                    per_beam=[PerBeamElements(beam_id="B1", element_count=1)],
                ),
                plan=_MockPlan(),
            )
        monkeypatch.setattr(BeamModelService, "_build_proton", staticmethod(_fake_proton))

        req = _request()
        r1 = service.build(req)
        r2 = service.build(req)
        assert r1.beam_model_id == r2.beam_model_id
        assert load_calls["n"] == 1, "cache hit must skip _load_geometry"

    def test_modality_change_misses_cache(self, tmp_path: Path, monkeypatch):
        service = BeamModelService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load_geometry", lambda gid: _stub_loaded_geometry())
        monkeypatch.setattr(BeamModelService, "_build_proton", staticmethod(
            lambda req, geom, mm: _build_dummy("proton")))
        monkeypatch.setattr(BeamModelService, "_build_photon", staticmethod(
            lambda req, geom, mm: _build_dummy("photon")))

        r_proton = service.build(_request(modality=Modality.proton_pbs))
        r_photon = service.build(_request(modality=Modality.photon_imrt))
        assert r_proton.beam_model_id != r_photon.beam_model_id


def _build_dummy(label: str):
    from radiarch.services.proton_spots import ProtonBuildResult
    return ProtonBuildResult(
        fluence_elements=FluenceElementSet(
            total_count=1,
            per_beam=[PerBeamElements(beam_id="B1", element_count=1)],
        ),
        plan=_MockPlan(note=label),
    )


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------

class TestErrors:
    def test_unknown_geometry_id_raises(self, tmp_path: Path, monkeypatch):
        """When the upstream geometry doesn't exist, surface a clean error."""
        service = BeamModelService(base_dir=tmp_path)

        def _missing_geometry(gid):
            raise ValueError(f"geometry_id {gid!r} not found")
        monkeypatch.setattr(service, "_load_geometry", _missing_geometry)

        with pytest.raises(ValueError, match="not found"):
            service.build(_request(geometry_id="does-not-exist"))

    def test_proton_modality_with_photon_machine_raises(self, tmp_path: Path, monkeypatch):
        service = BeamModelService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load_geometry", lambda gid: _stub_loaded_geometry())

        # Force the loader to return the wrong machine model type.
        def _wrong_machine(modality, mm_id):
            return PhotonMachineModel.from_default()  # but request is proton
        monkeypatch.setattr(BeamModelService, "_load_machine_model", staticmethod(_wrong_machine))

        with pytest.raises(ValueError, match="Proton modality requires"):
            service.build(_request(modality=Modality.proton_pbs))


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------

class TestProgressCallback:
    def test_callback_fires_for_each_stage(self, tmp_path: Path, monkeypatch):
        service = BeamModelService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load_geometry", lambda gid: _stub_loaded_geometry())
        monkeypatch.setattr(BeamModelService, "_build_proton", staticmethod(
            lambda req, geom, mm: _build_dummy("p")))

        events = []
        def _cb(stage, frac, msg):
            events.append((stage.value, round(frac, 2)))

        service.build(_request(), progress_callback=_cb)
        stages = [e[0] for e in events]
        assert "loading_geometry" in stages
        assert "loading_machine_model" in stages
        assert "building_beams" in stages
        assert "computing_elements" in stages
        assert "persisting" in stages
        assert stages[-1] == "done"
