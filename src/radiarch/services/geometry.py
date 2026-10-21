"""``GeometryService`` — DICOM (CT + RTSTRUCT) → voxel model.

This is the public entry point for Service 1. One method, one contract:
``build(request) -> GeometryResult``. Everything else is private.

Pipeline
--------
1. Compute ``cache_key`` and short-circuit to the cached geometry if present.
2. Load the CT + structure sets (``radiarch.dicom.case.load_case``;
   respects ``data_root_override``).
3. Convert CT HU → mass density on the *native* CT grid, using the
   requested :class:`HUDensityModel`. This ordering matters: converting
   HU before resampling preserves tissue boundaries better than
   resampling HU and then converting (which smears piecewise-linear
   models across interpolation boundaries).
4. Determine the target :class:`GridSpec` — either the user's explicit
   grid or the CT's own grid (the fast path, no resampling).
5. If the target ≠ native, resample the density with trilinear
   interpolation.
6. Rasterize contours on the target grid (respecting ``structure_name_map``
   aliases). Contours go straight to the target grid to avoid a
   second resampling step that would corrupt label boundaries.
7. Persist density + masks + metadata atomically; update cache index.
8. Return the :class:`GeometryResult`.

Testability
-----------
The service exposes a ``_load`` → ``_process`` seam. ``_load`` is the
DICOM I/O step, which tests stub out with a synthetic CT + fake
contours. ``_process`` does the math and persistence; that's where the
interesting invariants live.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.geometry import (
    CTMetadata,
    GeometryBuildRequest,
    GeometryResult,
    GeometryStage,
    GridSpec,
    HUDensityModel,
)


# Type alias: (stage, progress_fraction_0_to_1, human_message) -> None.
ProgressCallback = Callable[[GeometryStage, float, str], None]
from .hu_density import get_model as get_hu_density_model
from .persistence import (
    CT_FILENAME,
    DENSITY_FILENAME,
    GeometryPaths,
    GeometryStore,
    MASKS_FILENAME,
)
from .rasterization import rasterize_contours
from .resampling import identity_grid_from_affine, resample_to_grid


@dataclass
class _LoadedCT:
    """Internal bundle returned by ``_load`` — keeps the public API narrow."""

    ct: Any             # radiarch.dicom.ct.CTVolume (or test double): imageArray (x, y, z), origin, spacing
    patient: Any        # radiarch.dicom.ct.PatientInfo (or test double)
    contours: list      # Flattened list of contours across all structure sets


class GeometryService:
    """Stateless service (one instance can serve many requests).

    The only persistent state lives on disk, mediated by
    :class:`GeometryStore`. Instantiate directly for tests, or with a
    custom base_dir; the default uses ``{settings.artifact_dir}/geometry``.

    The optional ``adapter`` argument lets tests inject a fake
    ``OrthancAdapterBase``. In production it's left None and the service
    constructs one lazily via ``build_orthanc_adapter()`` the first time
    ``_load`` needs to reach PACS.
    """

    def __init__(
        self,
        base_dir: Optional[str | Path] = None,
        adapter: Optional[Any] = None,
    ) -> None:
        if base_dir is None:
            settings = get_settings()
            base_dir = Path(settings.artifact_dir) / "geometry"
        self.store = GeometryStore(base_dir)
        self._adapter = adapter  # None = lazy

    def _get_adapter(self):
        if self._adapter is None:
            from ..adapters import build_orthanc_adapter  # lazy import
            self._adapter = build_orthanc_adapter()
        return self._adapter

    # -----------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------

    def build(
        self,
        request: GeometryBuildRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> GeometryResult:
        """Run the geometry pipeline for ``request``.

        ``progress_callback`` is invoked as the pipeline advances through
        its stages so async callers (the Celery task) can update job
        status rows in real time. A no-op is used when None.
        """
        on_progress = progress_callback or _noop_progress

        cache_key = request.compute_cache_key()

        cached = self.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            logger.info("Geometry cache hit for key %s → %s", cache_key[:10], cached.geometry_id)
            on_progress(GeometryStage.done, 1.0, "cache hit")
            return cached

        logger.info("Building geometry (cache miss, key %s)", cache_key[:10])
        on_progress(GeometryStage.loading_dicom, 0.05, "Loading CT and RTSTRUCT")
        loaded = self._load(request)
        return self._process(request, loaded, cache_key, on_progress)

    # -----------------------------------------------------------------
    # Derived geometries (R4)
    # -----------------------------------------------------------------

    def derive(self, geometry_id: str, request) -> GeometryResult:
        """A new geometry from ``geometry_id`` plus structure operations (margins,
        booleans, rings, density overrides, a couch); cached like a build."""
        from .geometry_derive import GeometryDeriver  # lazy

        parent = self.store.get_by_id(geometry_id)
        if parent is None:
            raise ValueError(f"geometry_id {geometry_id!r} not found")
        return GeometryDeriver(self.store).derive(parent, request)

    # -----------------------------------------------------------------
    # DICOM loading.
    #
    # Three paths, chosen at request time (in priority order):
    #
    #   1. Upload path — if ``patient_ref.upload_id`` is set, read from
    #      ``{settings.upload_dir}/{upload_id}/``. This is the production
    #      entry point (client uploads a ZIP, gets back an upload_id,
    #      then references it in a build request).
    #   2. PACS path — if the adapter exposes ``can_retrieve_instances()``
    #      (i.e. a real Orthanc / DICOMweb backend), we fetch the study
    #      into a temp dir and read it from there.
    #   3. Disk path — read ``settings.data_root`` (or the request's
    #      ``data_root_override``). Dev-only convenience that keeps the
    #      existing tests + SimpleFantom demo working when Orthanc is
    #      mocked and no upload was provided.
    #
    # This is also the seam that tests stub out (monkeypatch ``_load``
    # to return a synthetic CT + fake contours).
    # -----------------------------------------------------------------

    def _load(self, request: GeometryBuildRequest) -> _LoadedCT:
        # 0. NRRD path — an explicit local file reference (dev/testing on real
        # 3D data before DICOM). Highest priority: the caller named a file.
        if request.patient_ref.nrrd_ct_path:
            return self._load_from_nrrd(request.patient_ref)

        # 1. Upload path — highest priority. The client explicitly
        # uploaded files; we should read those, never silently fall
        # through to anything else.
        if request.patient_ref.upload_id:
            upload_path = self._resolve_upload_path(request.patient_ref.upload_id)
            return self._load_from_disk(str(upload_path))

        # If the caller forced a data_root, honor it — useful for tests
        # and one-off debugging against local fixtures even when Orthanc
        # is reachable.
        if request.data_root_override:
            return self._load_from_disk(request.data_root_override)

        # Prefer PACS when available.
        try:
            adapter = self._get_adapter()
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "Failed to build Orthanc adapter, falling back to disk: %s", exc
            )
            return self._load_from_disk(None)

        from .dicom_fetcher import DicomFetcher  # lazy

        fetcher = DicomFetcher(adapter)
        if not fetcher.can_fetch:
            logger.info(
                "Orthanc adapter is metadata-only (mock mode); "
                "falling back to the data root."
            )
            return self._load_from_disk(None)

        return self._load_from_pacs(fetcher, request)

    # ---- Upload path -------------------------------------------------

    @staticmethod
    def _resolve_upload_path(upload_id: str) -> Path:
        """Map an upload_id to its extracted directory.

        Raises ``ValueError`` (→ 422 at the API) if the upload directory
        doesn't exist — covers the case where a client passes a stale or
        bogus upload_id.
        """
        settings = get_settings()
        base = settings.upload_dir or str(Path(settings.artifact_dir) / "uploads")
        path = Path(base).expanduser().resolve() / upload_id
        if not path.is_dir():
            raise ValueError(
                f"Upload id not found: {upload_id!r}. "
                "POST a ZIP to /api/v1/uploads/dicom first."
            )
        return path

    # ---- NRRD path ----------------------------------------------------

    @staticmethod
    def _load_from_nrrd(ref) -> _LoadedCT:
        """Load a CT (+ optional segmentation) from NRRD/ITK files.

        Produces the same ``_LoadedCT`` bundle as the DICOM paths: a
        ``CTVolume`` and a list of ``ContourLike`` segment adapters, so the
        rest of the pipeline runs unchanged.
        """
        from ..adapters.nrrd_ingest import load_nrrd_case  # lazy

        ct, patient, contours = load_nrrd_case(
            ref.nrrd_ct_path, ref.nrrd_seg_path
        )
        return _LoadedCT(ct=ct, patient=patient, contours=contours)

    # ---- Disk path ----------------------------------------------------

    @staticmethod
    def _load_from_disk(data_root: Optional[str]) -> _LoadedCT:
        from ..dicom.case import load_case  # lazy

        root = data_root or get_settings().data_root
        if not root:
            raise ValueError("no DICOM data root configured (RADIARCH_DATA_ROOT) and no upload or PACS study given")
        case = load_case(root)
        return _LoadedCT(ct=case.ct, patient=case.patient, contours=case.contours)

    # ---- PACS path ----------------------------------------------------

    @staticmethod
    def _load_from_pacs(fetcher, request: GeometryBuildRequest) -> _LoadedCT:
        """Download the study via ``fetcher`` and read it from the temp dir.

        The temp dir is cleaned up before we return — everything is read
        eagerly into memory, so we don't need the files on disk afterwards.
        """
        from ..dicom.case import load_case  # lazy

        with fetcher.fetch(request.patient_ref) as staged:
            series_uid = getattr(request.patient_ref, "dicom_series_uid", None) or None
            try:
                case = load_case(staged.directory, ct_series_uid=series_uid)
            except ValueError as exc:
                raise ValueError(f"staged study {staged.directory}: {exc}") from exc
            return _LoadedCT(ct=case.ct, patient=case.patient, contours=case.contours)

    # -----------------------------------------------------------------
    # Core processing pipeline — tested with stubs.
    # -----------------------------------------------------------------

    def _process(
        self,
        request: GeometryBuildRequest,
        loaded: _LoadedCT,
        cache_key: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GeometryResult:
        on_progress = on_progress or _noop_progress

        ct = loaded.ct
        ct_array = np.asarray(ct.imageArray)
        if ct_array.ndim != 3:
            raise ValueError(f"CT imageArray must be 3D, got shape {ct_array.shape}")

        src_spacing = tuple(float(s) for s in ct.spacing)
        src_origin = tuple(float(o) for o in ct.origin)
        src_size = tuple(int(s) for s in ct_array.shape)

        source_grid = GridSpec(
            spacing_mm=src_spacing,
            origin_mm=src_origin,
            size=src_size,
        )
        source_grid.affine = source_grid.compute_affine()
        src_affine = source_grid.to_numpy_affine()

        # 1. HU → density on the NATIVE grid.
        on_progress(GeometryStage.converting_hu, 0.25, "HU → density")
        hu_model = get_hu_density_model(request.hu_to_density_model)
        density_native = hu_model.convert(ct_array)

        # 2. Pick the target grid.
        target_grid = self._resolve_target_grid(request, source_grid)

        # 3. Resample density AND CT (in HU) if target ≠ source.
        #    The CT is needed downstream by engines like MCsquare that
        #    consume Hounsfield Units directly rather than mass density.
        on_progress(GeometryStage.resampling, 0.45, "Resampling density to target grid")
        density_final = self._maybe_resample(
            density_native, src_affine, source_grid, target_grid
        )
        # Resample the raw HU array with the same trilinear kernel so the
        # CT and density stay perfectly aligned on the persisted grid.
        ct_final = self._maybe_resample(
            ct_array.astype(np.float32, copy=False),
            src_affine, source_grid, target_grid,
        )

        # 4. Rasterize contours directly on the target grid.
        on_progress(GeometryStage.rasterizing_contours, 0.70, "Rasterizing contours")
        masks, structure_index = rasterize_contours(
            loaded.contours,
            target_grid,
            structure_name_map=request.structure_name_map,
        )

        # 5. Persist + build the result.
        on_progress(GeometryStage.persisting, 0.90, "Writing NIfTI + cache index")
        geometry_id = str(uuid.uuid4())
        paths = GeometryPaths.for_id(self.store.base_dir, geometry_id)
        ct_meta = self._ct_metadata(ct)

        result = GeometryResult(
            geometry_id=geometry_id,
            density_grid_uri=str(paths.density),
            structure_masks_uri=str(paths.masks),
            ct_grid_uri=str(paths.ct),
            structure_index=structure_index,
            mask_encoding="bitmask",
            grid_spec=target_grid,
            frame_of_reference_uid=self._frame_of_reference(ct),
            ct_metadata=ct_meta,
            cache_key=cache_key,
            hu_to_density_model=request.hu_to_density_model.value,
        )

        self.store.save(
            geometry_id=geometry_id,
            cache_key=cache_key,
            density=density_final,
            masks=masks,
            ct=ct_final,
            result=result,
        )
        logger.info(
            "Geometry %s built: grid=%s structures=%s",
            geometry_id,
            target_grid.size,
            list(structure_index.keys()),
        )
        on_progress(GeometryStage.done, 1.0, f"geometry_id={geometry_id}")
        return result

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _resolve_target_grid(
        request: GeometryBuildRequest,
        source: GridSpec,
    ) -> GridSpec:
        """Fill in any missing target-grid fields from the source grid."""
        if request.grid_spec is None:
            # Fast path: inherit everything from the source.
            inherited = GridSpec(
                spacing_mm=source.spacing_mm,
                origin_mm=source.origin_mm,
                size=source.size,
            )
            inherited.affine = inherited.compute_affine()
            return inherited

        # Partial inheritance: user gave spacing but left origin / size
        # null → origin comes from the source grid; size is whatever covers
        # the source extent at the requested spacing (a 200 mm phantom at
        # 5 mm is 40 voxels, not the source's 200 — inheriting the voxel
        # count would silently turn a resample into a 1 m grid).
        spec = request.grid_spec
        origin = spec.origin_mm if spec.origin_mm is not None else source.origin_mm
        if spec.size is not None:
            size = spec.size
        else:
            size = tuple(
                max(1, int(np.ceil(n * s_src / s_tgt)))
                for n, s_src, s_tgt in zip(source.size, source.spacing_mm, spec.spacing_mm)
            )

        completed = GridSpec(
            spacing_mm=spec.spacing_mm,
            origin_mm=origin,
            size=size,
        )
        completed.affine = completed.compute_affine()
        return completed

    @staticmethod
    def _maybe_resample(
        density: np.ndarray,
        src_affine: np.ndarray,
        source: GridSpec,
        target: GridSpec,
    ) -> np.ndarray:
        """Skip resampling if target grid == source grid (the fast path)."""
        if (
            source.spacing_mm == target.spacing_mm
            and source.origin_mm == target.origin_mm
            and source.size == target.size
        ):
            return density.astype(np.float32, copy=False)
        return resample_to_grid(density, src_affine, target, order=1, cval=0.0)

    @staticmethod
    def _ct_metadata(ct: Any) -> CTMetadata:
        patient = getattr(ct, "patient", None)
        patient_name = getattr(patient, "name", None) or getattr(patient, "patientName", None) or "ANONYMOUS"
        g = lambda obj, name: str(getattr(obj, name, "") or "")  # noqa: E731
        return CTMetadata(
            patient_name=str(patient_name),
            modality="CT",
            num_slices=int(np.asarray(ct.imageArray).shape[2]),
            study_instance_uid=getattr(ct, "studyInstanceUID", None),
            series_instance_uid=getattr(ct, "seriesInstanceUID", None),
            patient_id=g(patient, "id"),
            patient_birth_date=g(patient, "birth_date"),
            patient_sex=g(patient, "sex"),
            patient_position=g(ct, "patientPosition"),
            study_date=g(ct, "studyDate"),
            study_time=g(ct, "studyTime"),
            study_id=g(ct, "studyID"),
            accession_number=g(ct, "accessionNumber"),
            study_description=g(ct, "studyDescription"),
            sop_instance_uids=[str(u) for u in (getattr(ct, "sopInstanceUIDs", None) or [])],
        )

    @staticmethod
    def _frame_of_reference(ct: Any) -> str:
        for_uid = (
            getattr(ct, "frameOfReferenceUID", None)
            or getattr(ct, "FrameOfReferenceUID", None)
            or ""
        )
        return str(for_uid)


def _noop_progress(stage: GeometryStage, fraction: float, message: str) -> None:
    """Default ``progress_callback`` when none is supplied."""
    del stage, fraction, message  # unused


__all__ = ["GeometryService", "ProgressCallback"]
