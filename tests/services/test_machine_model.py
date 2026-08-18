"""Unit tests for radiarch.services.machine_model.

These tests exercise the factory's dispatch logic without actually
loading the BDL / calibration files — those are heavyweight and only
get touched when ``.bdl`` / ``.calibration`` are accessed.
"""

from __future__ import annotations

import pytest

from radiarch.models.beam_model import Modality
from radiarch.services.machine_model import (
    MachineModelError,
    PhotonMachineModel,
    ProtonMachineModel,
    get_machine_model,
)


class TestProtonMachineModel:
    def test_default_constructor_does_no_io(self) -> None:
        # Should be instant — no disk reads until .bdl / .calibration.
        mm = ProtonMachineModel.from_default()
        assert mm.modality is Modality.proton_pbs
        assert mm.machine_model_id == "default"

    def test_from_id_raises_when_path_missing(self) -> None:
        with pytest.raises(MachineModelError, match="not found"):
            ProtonMachineModel.from_id("definitely-does-not-exist-xyz")


class TestPhotonMachineModel:
    def test_default_has_sensible_values(self) -> None:
        mm = PhotonMachineModel.from_default()
        assert mm.modality is Modality.photon_imrt
        assert mm.machine_model_id == "default"
        assert mm.mlc_leaf_width_mm > 0
        assert mm.max_jaw_opening_mm > 0
        assert mm.beam_quality_mv > 0

    def test_from_id_only_recognizes_default(self) -> None:
        with pytest.raises(MachineModelError, match="not found"):
            PhotonMachineModel.from_id("varian-truebeam-customized")

    def test_from_id_default_returns_default(self) -> None:
        assert PhotonMachineModel.from_id("default").machine_model_id == "default"


class TestFactory:
    def test_dispatches_to_proton_for_proton_modality(self) -> None:
        mm = get_machine_model(Modality.proton_pbs)
        assert isinstance(mm, ProtonMachineModel)

    def test_dispatches_to_photon_for_photon_modality(self) -> None:
        mm = get_machine_model(Modality.photon_imrt)
        assert isinstance(mm, PhotonMachineModel)

    def test_none_id_returns_default(self) -> None:
        mm = get_machine_model(Modality.proton_pbs, None)
        assert mm.machine_model_id == "default"

    def test_explicit_default_id_returns_default(self) -> None:
        mm = get_machine_model(Modality.proton_pbs, "default")
        assert mm.machine_model_id == "default"

    def test_unknown_id_raises_clean_error(self) -> None:
        with pytest.raises(MachineModelError):
            get_machine_model(Modality.proton_pbs, "not-a-real-machine")
