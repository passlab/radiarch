"""``BeamModelService`` — geometry + beam set → modality-specific beam model.

This is the public entry point for Service 2. One method, one contract:
``build(request) -> BeamModelResult``.

Pipeline
--------
1. Compute ``cache_key`` and short-circuit if already built.
2. Load the geometry — look it up in the Geometry Service's store (404 →
   422 to the API caller) and read the persisted CT and label volumes
   (``geometry_bundle.load_geometry_arrays``). Nothing is re-read from
   DICOM, so the beam model is built on exactly the geometry the caller
   named.
3. Resolve the machine model.
4. Dispatch to ``_build_proton`` or ``_build_photon`` based on modality.
5. Persist the plan (pickled pydantic model) + meta.json atomically.
6. Return :class:`BeamModelResult`.

Testability
-----------
Same ``_load_*`` / ``_process`` seam as :class:`GeometryService`. Tests
stub out ``_load_geometry`` and ``_load_machine_model`` (or the modality
builders directly) so they never touch the engine assets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from ..config import get_settings
from ..models.beam_model import (
    BeamModelBuildRequest,
    BeamModelResult,
    BeamModelStage,
    FluenceElementSet,
    Modality,
)
from .beam_persistence import BeamModelPaths, BeamModelStore
from .machine_model import (
    MachineModelBase,
    MachineModelError,
    PhotonMachineModel,
    ProtonMachineModel,
    get_machine_model,
)


# Same callback shape as Geometry Service: (stage, fraction, message) → None.
ProgressCallback = Callable[[BeamModelStage, float, str], None]


@dataclass
class _LoadedGeometry:
    """Internal bundle returned by ``_load_geometry``: the persisted arrays
    plus the ``geometry_id`` so the result can reference its upstream input."""

    geometry_id: str
    arrays: Any        # GeometryArrays (or test double)


class BeamModelService:
    """Stateless service. One instance can serve many requests.

    The persistent state lives on disk via :class:`BeamModelStore`. A
    second optional dependency — the geometry store — is resolved lazily
    so tests can construct a service with no env / no settings.
    """

    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        if base_dir is None:
            settings = get_settings()
            base_dir = Path(settings.artifact_dir) / "beam_models"
        self.store = BeamModelStore(base_dir)

    # -----------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------

    def build(
        self,
        request: BeamModelBuildRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> BeamModelResult:
        on_progress = progress_callback or _noop_progress
        cache_key = request.compute_cache_key()

        cached = self.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            logger.info(
                "Beam model cache hit for key {} → {}",
                cache_key[:10], cached.beam_model_id,
            )
            on_progress(BeamModelStage.done, 1.0, "cache hit")
            return cached

        logger.info("Building beam model (cache miss, key {})", cache_key[:10])

        on_progress(BeamModelStage.loading_geometry, 0.05, "Loading geometry")
        geometry = self._load_geometry(request.geometry_id)

        on_progress(BeamModelStage.loading_machine_model, 0.15, "Loading machine model")
        machine_model = self._load_machine_model(request.modality, request.machine_model_id)

        return self._process(request, geometry, machine_model, cache_key, on_progress)

    # -----------------------------------------------------------------
    # Loading — the testability seam
    # -----------------------------------------------------------------

    def _load_geometry(self, geometry_id: str) -> _LoadedGeometry:
        """Read the persisted geometry the builders need.

        The Geometry Service wrote the CT grid, the structure masks and the
        structure index for ``geometry_id``; the beam model is built on
        exactly those. (It used to re-read the data root whatever the id
        was, so every beam model came out of the default phantom.)
        """
        from .geometry import GeometryService  # lazy
        from .geometry_bundle import load_geometry_arrays  # lazy

        geom = GeometryService().store.get_by_id(geometry_id)
        if geom is None:
            raise ValueError(
                f"geometry_id {geometry_id!r} not found — build the geometry "
                "first via POST /api/v1/geometry/build."
            )
        return _LoadedGeometry(geometry_id=geometry_id, arrays=load_geometry_arrays(geom))

    @staticmethod
    def _load_machine_model(
        modality: Modality,
        machine_model_id: Optional[str],
    ) -> MachineModelBase:
        """Resolve the machine model. Wraps the factory so tests can stub."""
        try:
            return get_machine_model(modality, machine_model_id)
        except MachineModelError as exc:
            # Surface as a request-validation error to the API layer.
            raise ValueError(str(exc)) from exc

    # -----------------------------------------------------------------
    # Modality dispatch + persistence
    # -----------------------------------------------------------------

    def _process(
        self,
        request: BeamModelBuildRequest,
        geometry: _LoadedGeometry,
        machine_model: MachineModelBase,
        cache_key: str,
        on_progress: ProgressCallback,
    ) -> BeamModelResult:
        on_progress(BeamModelStage.building_beams, 0.30, f"Building {request.modality.value}")

        if request.modality is Modality.proton_pbs:
            built = self._build_proton(request, geometry, machine_model)
        elif request.modality is Modality.photon_imrt:
            built = self._build_photon(request, geometry, machine_model)
        else:  # pragma: no cover — enum-exhaustive
            raise ValueError(f"Unsupported modality: {request.modality!r}")

        on_progress(
            BeamModelStage.computing_elements,
            0.75,
            f"{built.fluence_elements.total_count} fluence elements",
        )

        beam_model_id = str(uuid.uuid4())
        paths = BeamModelPaths.for_id(self.store.base_dir, beam_model_id)
        result = BeamModelResult(
            beam_model_id=beam_model_id,
            geometry_id=geometry.geometry_id,
            modality=request.modality,
            fluence_elements=built.fluence_elements,
            beam_model_ref_uri=str(paths.plan),
            machine_model_id=machine_model.machine_model_id,
            cache_key=cache_key,
        )

        on_progress(BeamModelStage.persisting, 0.92, "Pickling plan")
        self.store.save(
            beam_model_id=beam_model_id,
            cache_key=cache_key,
            plan=built.plan,
            result=result,
        )

        logger.info(
            "Beam model {} built: modality={} elements={}",
            beam_model_id,
            request.modality.value,
            built.fluence_elements.total_count,
        )
        on_progress(BeamModelStage.done, 1.0, f"beam_model_id={beam_model_id}")
        return result

    @staticmethod
    def _build_proton(
        request: BeamModelBuildRequest,
        geometry: _LoadedGeometry,
        machine_model: MachineModelBase,
    ):
        from .proton_spots import generate_proton_spots  # lazy

        if not isinstance(machine_model, ProtonMachineModel):
            raise ValueError(
                f"Proton modality requires a ProtonMachineModel, "
                f"got {type(machine_model).__name__}"
            )
        return generate_proton_spots(
            geometry=geometry.arrays,
            machine_model=machine_model,
            beam_set=request.beam_set,
            params=request.delivery_params,
        )

    @staticmethod
    def _build_photon(
        request: BeamModelBuildRequest,
        geometry: _LoadedGeometry,
        machine_model: MachineModelBase,
    ):
        from .photon_beamlets import generate_photon_beamlets  # lazy

        if not isinstance(machine_model, PhotonMachineModel):
            raise ValueError(
                f"Photon modality requires a PhotonMachineModel, "
                f"got {type(machine_model).__name__}"
            )
        return generate_photon_beamlets(
            geometry=geometry.arrays,
            machine_model=machine_model,
            beam_set=request.beam_set,
            params=request.delivery_params,
        )


def _noop_progress(stage: BeamModelStage, fraction: float, message: str) -> None:
    """Default ``progress_callback`` when none is supplied."""
    del stage, fraction, message


__all__ = ["BeamModelService", "ProgressCallback"]
