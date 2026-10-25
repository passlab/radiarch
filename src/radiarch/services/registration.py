"""Registration Service (roadmap R9): rigid and deformable registration of two geometries' CTs, contour
propagation and the mapping of volumes (doses) between their grids.

Method
------
Both CTs are clipped to a HU window and resampled to an isotropic working spacing, each over its own extent
(a cone-beam CT's short field of view stays short: points outside an image are excluded from the metrics,
not compared with air).

* **Rigid** (``Euler3DTransform``): Mattes mutual information, regular-step gradient descent, a pyramid of
  ``levels`` resolutions; initialised by the identity when the two share a frame of reference (4DCT phases),
  else by the volume centres or the body's centres of mass.
* **Demons** (``DiffeomorphicDemonsRegistrationFilter``), for the same modality and calibration: the moving CT,
  rigidly resampled onto the fixed working grid, is registered level by level, the field smoothed by a
  Gaussian of ``demons_sigma_mm`` and carried up the pyramid.
* **B-spline** (``BSplineTransform``, control points every ``bspline_grid_mm``), for CT to cone-beam CT: normalised
  correlation (invariant to a linear HU calibration) with L-BFGS-B over the same pyramid, on top of the rigid transform.

The composed transform ``T(x) = R(D(x))`` is written as one displacement field on the fixed geometry's grid,
so every later mapping samples one field. Metric sampling uses fixed seeds: a registration is repeatable.

Quality (AAPM TG-132): inside the fixed body (HU > -500, where the moving image is defined), the mean
absolute HU difference and the normalised cross-correlation for the initial, the rigid and the final
transform; the Jacobian determinant of ``T`` (folding where it is not positive); landmark errors between
structure centroids. These are the numbers a reviewer needs to accept or reject a registration; the
service does not judge them.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import SimpleITK as sitk
from loguru import logger

from ..config import get_settings
from ..models.geometry import GeometryResult
from ..models.registration import (
    DeformableMethod, JacobianStats, LandmarkError, PropagateRequest, RegistrationQuality, RegistrationRequest,
    RegistrationResult, RigidInit, Similarity,
)

BODY_HU = -500.0
SEED = 20261024
METRIC_MASK_MARGIN_MM = 10.0
BSPLINE_INJECTIVE_FRACTION = 0.4


class RegistrationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def _grid(geom: GeometryResult) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    origin = tuple(float(v) for v in (geom.grid_spec.origin_mm or (0.0, 0.0, 0.0)))
    spacing = tuple(float(v) for v in geom.grid_spec.spacing_mm)
    return origin, spacing


def to_image(arr_zyx: np.ndarray, origin: Sequence[float], spacing: Sequence[float], dtype=np.float32) -> sitk.Image:
    img = sitk.GetImageFromArray(np.asarray(arr_zyx, dtype=dtype))
    img.SetOrigin(tuple(float(v) for v in origin))
    img.SetSpacing(tuple(float(v) for v in spacing))
    return img


def _reference(shape_zyx: Sequence[int], origin: Sequence[float], spacing: Sequence[float]) -> sitk.Image:
    ref = sitk.Image([int(shape_zyx[2]), int(shape_zyx[1]), int(shape_zyx[0])], sitk.sitkUInt8)
    ref.SetOrigin(tuple(float(v) for v in origin))
    ref.SetSpacing(tuple(float(v) for v in spacing))
    return ref


def _working(img: sitk.Image, spacing_mm: float, default: float) -> sitk.Image:
    """The image over its own extent at an isotropic spacing (smoothed first when it is coarser)."""
    old_sp = np.array(img.GetSpacing())
    size = np.array(img.GetSize())
    new_sp = np.array([spacing_mm] * 3)
    new_size = [max(1, int(round(n))) for n in size * old_sp / new_sp]
    sigma = [max(0.0, (s_new ** 2 - s_old ** 2)) ** 0.5 / 2.0 for s_new, s_old in zip(new_sp, old_sp)]
    src = sitk.SmoothingRecursiveGaussian(img, sigma) if max(sigma) > 0.25 else img
    origin = np.array(img.GetOrigin()) - old_sp / 2 + new_sp / 2
    return sitk.Resample(src, new_size, sitk.Transform(), sitk.sitkLinear, origin.tolist(), new_sp.tolist(),
                         img.GetDirection(), default, sitk.sitkFloat32)


def _shrink(img: sitk.Image, factor: int) -> sitk.Image:
    if factor <= 1:
        return img
    sp = np.array(img.GetSpacing()) * factor
    size = [max(1, int(math.ceil(n / factor))) for n in img.GetSize()]
    smooth = sitk.SmoothingRecursiveGaussian(img, [float(s) / 2.0 for s in np.array(img.GetSpacing()) * factor / 2.0])
    origin = np.array(img.GetOrigin()) - np.array(img.GetSpacing()) / 2 + sp / 2
    return sitk.Resample(smooth, size, sitk.Transform(), sitk.sitkLinear, origin.tolist(), sp.tolist(), img.GetDirection(),
                         float(sitk.GetArrayViewFromImage(img).min()), img.GetPixelID())


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def _initial(fixed: sitk.Image, moving: sitk.Image, how: RigidInit, same_for: bool) -> sitk.Euler3DTransform:
    if how is RigidInit.auto:
        how = RigidInit.identity if same_for else RigidInit.centres
    tx = sitk.Euler3DTransform()
    if how is RigidInit.identity:
        return tx
    mode = sitk.CenteredTransformInitializerFilter.GEOMETRY if how is RigidInit.centres else sitk.CenteredTransformInitializerFilter.MOMENTS
    f, m = fixed + 1000.0, moving + 1000.0                      # positive weights for the moments
    return sitk.Euler3DTransform(sitk.CenteredTransformInitializer(f, m, tx, mode))


def _fixed_mask(fixed: sitk.Image, margin_mm: float = METRIC_MASK_MARGIN_MM) -> sitk.Image:
    """Where the metric looks: the fixed image's body (HU > -500) and a margin around it. A cone-beam CT resampled onto
    a planning grid is mostly padding outside its field of view, where the planning CT has tissue; compared there, the
    deformable step drags tissue into the padding. The margin keeps the skin boundary, without which the rigid step
    slides (a body-only mask moved a pancreas cone-beam pair by about 2 cm). Padding cannot be told from air by value:
    the collection clips air at -1000 as well."""
    body = sitk.Cast(sitk.BinaryThreshold(fixed, BODY_HU, 1e9, 1, 0), sitk.sitkUInt8)
    if margin_mm <= 0:
        return body
    radius = [max(1, int(round(margin_mm / sp))) for sp in fixed.GetSpacing()]
    return sitk.Cast(sitk.BinaryDilate(body, radius), sitk.sitkUInt8)


def _pyramid(levels: int) -> Tuple[List[int], List[float]]:
    shrink = [2 ** k for k in range(levels - 1, -1, -1)]
    return shrink, [float(max(0, k)) for k in range(levels - 1, -1, -1)]


def _rigid(fixed: sitk.Image, moving: sitk.Image, init: sitk.Euler3DTransform, levels: int, mask: Optional[sitk.Image] = None) -> sitk.Euler3DTransform:
    reg = sitk.ImageRegistrationMethod()
    reg.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
    if mask is not None:
        reg.SetMetricFixedMask(mask)
    reg.SetMetricSamplingStrategy(reg.RANDOM)
    reg.SetMetricSamplingPercentage(0.25, SEED)
    reg.SetInterpolator(sitk.sitkLinear)
    reg.SetOptimizerAsRegularStepGradientDescent(learningRate=2.0, minStep=1e-4, numberOfIterations=200, relaxationFactor=0.6)
    reg.SetOptimizerScalesFromPhysicalShift()
    shrink, sigma = _pyramid(levels)
    reg.SetShrinkFactorsPerLevel(shrink)
    reg.SetSmoothingSigmasPerLevel(sigma)
    reg.SetInitialTransform(sitk.Euler3DTransform(init), inPlace=False)
    out = reg.Execute(fixed, moving)
    if isinstance(out, sitk.CompositeTransform):
        out = out.GetBackTransform() if out.GetNumberOfTransforms() == 1 else out.GetNthTransform(0)
    return sitk.Euler3DTransform(out)


def _demons(fixed: sitk.Image, moving_r: sitk.Image, levels: int, iterations: int, sigma_mm: float) -> sitk.Image:
    """A displacement field on the fixed working grid with ``moving_r(x + d(x)) ≈ fixed(x)``."""
    field = None
    for factor in [2 ** k for k in range(levels - 1, -1, -1)]:
        f, m = _shrink(fixed, factor), _shrink(moving_r, factor)
        flt = sitk.DiffeomorphicDemonsRegistrationFilter()
        flt.SetNumberOfIterations(int(iterations))
        flt.SetSmoothDisplacementField(True)
        flt.SetStandardDeviations(float(sigma_mm) / float(f.GetSpacing()[0]))
        flt.SetUseImageSpacing(True)
        if field is None:
            field = flt.Execute(f, m)
        else:
            init = sitk.Resample(field, f, sitk.Transform(), sitk.sitkLinear, 0.0, field.GetPixelID())
            field = flt.Execute(f, m, init)
    return field


def _bspline(fixed: sitk.Image, moving: sitk.Image, rigid: sitk.Transform, levels: int, grid_mm: float, iterations: int,
             mask: Optional[sitk.Image] = None, sampling: float = 0.10) -> sitk.BSplineTransform:
    extent = np.array(fixed.GetSize()) * np.array(fixed.GetSpacing())
    mesh = [max(1, int(round(e / grid_mm))) for e in extent]
    bs = sitk.BSplineTransformInitializer(fixed, mesh, order=3)
    # Coefficients within 0.4 of the control-point spacing keep a cubic B-spline one-to-one (Choi and Lee 2000:
    # displacements below 1/2.48 of the spacing): the bound is the regularisation that keeps the field from folding.
    bound = BSPLINE_INJECTIVE_FRACTION * float(np.min(extent / np.array(mesh)))
    reg = sitk.ImageRegistrationMethod()
    if mask is not None:
        reg.SetMetricFixedMask(mask)
    # Normalised correlation: invariant to a linear HU scale and offset (a cone-beam CT's calibration). Not Mattes
    # MI, whose derivative buffers (bins^2 x parameters per work unit) exceed 8 GB for a thorax's ~11k B-spline
    # parameters on 20 threads; not joint-histogram MI, which did not move the B-spline (ADR 0016).
    reg.SetMetricAsCorrelation()
    reg.SetMetricSamplingStrategy(reg.RANDOM)
    reg.SetMetricSamplingPercentage(float(sampling), SEED)
    reg.SetInterpolator(sitk.sitkLinear)
    reg.SetOptimizerAsLBFGSB(gradientConvergenceTolerance=1e-5, numberOfIterations=int(iterations), maximumNumberOfCorrections=5,
                             maximumNumberOfFunctionEvaluations=4 * int(iterations), costFunctionConvergenceFactor=1e7,
                             lowerBound=-bound, upperBound=bound)
    shrink, sigma = _pyramid(levels)
    reg.SetShrinkFactorsPerLevel(shrink)
    reg.SetSmoothingSigmasPerLevel(sigma)
    reg.SetMovingInitialTransform(rigid)
    reg.SetInitialTransform(bs, inPlace=True)
    reg.Execute(fixed, moving)
    return bs


def field_transform(field: sitk.Image) -> sitk.DisplacementFieldTransform:
    return sitk.DisplacementFieldTransform(sitk.Cast(field, sitk.sitkVectorFloat64))


def _matrix(tx: sitk.Euler3DTransform) -> List[List[float]]:
    """4 x 4 of ``y = A (x - c) + c + t``."""
    a = np.array(tx.GetMatrix()).reshape(3, 3)
    c = np.array(tx.GetCenter())
    t = np.array(tx.GetTranslation())
    m = np.eye(4)
    m[:3, :3] = a
    m[:3, 3] = t + c - a @ c
    return m.tolist()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class RegistrationStore:
    """``{artifact_dir}/registrations/{id}/meta.json`` and ``field.nii.gz``, with a cache index."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _index(self) -> Path:
        return self.base_dir / "_index.json"

    def _load_index(self) -> Dict[str, str]:
        try:
            return json.loads(self._index.read_text(encoding="utf-8")) if self._index.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def field_path(self, registration_id: str) -> Path:
        return self.base_dir / registration_id / "field.nii.gz"

    def lookup_by_cache_key(self, key: str) -> Optional[RegistrationResult]:
        rid = self._load_index().get(key)
        return self.get_by_id(rid) if rid else None

    def get_by_id(self, registration_id: str) -> Optional[RegistrationResult]:
        meta = self.base_dir / registration_id / "meta.json"
        if not meta.is_file():
            return None
        try:
            return RegistrationResult.model_validate_json(meta.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_ids(self) -> List[str]:
        if not self.base_dir.is_dir():
            return []
        return sorted(d.name for d in self.base_dir.iterdir() if d.is_dir() and (d / "meta.json").is_file())

    def delete_by_id(self, registration_id: str) -> None:
        import shutil
        result = self.get_by_id(registration_id)
        shutil.rmtree(self.base_dir / registration_id, ignore_errors=True)
        if result is not None:
            index = self._load_index()
            if index.pop(result.cache_key, None) is not None:
                tmp_i = self._index.with_suffix(".json.tmp")
                tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
                os.replace(tmp_i, self._index)

    def load_field(self, registration_id: str) -> sitk.Image:
        return sitk.ReadImage(str(self.field_path(registration_id)))

    def save(self, result: RegistrationResult, field: sitk.Image) -> None:
        root = self.base_dir / result.registration_id
        root.mkdir(parents=True, exist_ok=True)
        sitk.WriteImage(sitk.Cast(field, sitk.sitkVectorFloat32), str(root / "field.nii.gz"), True)
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.registration_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_i, self._index)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RegistrationService:
    def __init__(self, base_dir: Optional[Path] = None, geometry_service=None) -> None:
        from .geometry import GeometryService
        settings = get_settings()
        self.store = RegistrationStore(Path(base_dir) if base_dir else Path(settings.artifact_dir) / "registrations")
        self.geometry_service = geometry_service or GeometryService()

    # ----- inputs -------------------------------------------------------

    def _geometry(self, geometry_id: str) -> GeometryResult:
        geom = self.geometry_service.store.get_by_id(geometry_id)
        if geom is None:
            raise RegistrationError(f"geometry {geometry_id!r} not found")
        return geom

    @staticmethod
    def _ct(geom: GeometryResult) -> sitk.Image:
        from .geometry_bundle import load_ct_hu
        ct = load_ct_hu(geom)
        if ct is None:
            raise RegistrationError(f"geometry {geom.geometry_id!r} has no CT on disk; rebuild it")
        origin, spacing = _grid(geom)
        return to_image(ct.astype(np.float32), origin, spacing)

    @staticmethod
    def _masks(geom: GeometryResult):
        from .geometry_bundle import load_geometry_arrays
        return load_geometry_arrays(geom)

    # ----- registration ---------------------------------------------------

    def register(self, request: RegistrationRequest) -> RegistrationResult:
        fixed_g, moving_g = self._geometry(request.fixed_geometry_id), self._geometry(request.moving_geometry_id)
        key = request.cache_key(fixed_g.cache_key, moving_g.cache_key)
        cached = self.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        t0 = time.time()
        lo, hi = request.hu_window
        fixed_ct, moving_ct = self._ct(fixed_g), self._ct(moving_g)
        fixed_working = _working(fixed_ct, request.working_spacing_mm, -1000.0)
        fw = sitk.Clamp(fixed_working, sitk.sitkFloat32, lo, hi)
        mw = sitk.Clamp(_working(moving_ct, request.working_spacing_mm, -1000.0), sitk.sitkFloat32, lo, hi)
        same_for = bool(fixed_g.frame_of_reference_uid) and fixed_g.frame_of_reference_uid == moving_g.frame_of_reference_uid
        init = _initial(fw, mw, request.rigid_init, same_for)
        mask = _fixed_mask(fixed_working)
        rigid = _rigid(fw, mw, init, request.levels, mask) if request.rigid else init
        total = sitk.CompositeTransform(rigid)
        if request.deformable is DeformableMethod.demons:
            moving_r = sitk.Resample(mw, fw, rigid, sitk.sitkLinear, lo, sitk.sitkFloat32)
            d = _demons(fw, moving_r, request.levels, request.demons_iterations, request.demons_sigma_mm)
            total.AddTransform(field_transform(d))
        elif request.deformable is DeformableMethod.bspline:
            total.AddTransform(_bspline(fw, mw, rigid, request.levels, request.bspline_grid_mm, request.bspline_iterations, mask,
                                        request.bspline_sampling))

        # the composed transform as one field on the fixed geometry's grid
        f_origin, f_spacing = _grid(fixed_g)
        ref = _reference(sitk.GetArrayViewFromImage(fixed_ct).shape, f_origin, f_spacing)
        to_field = sitk.TransformToDisplacementFieldFilter()
        to_field.SetReferenceImage(ref)
        to_field.SetOutputPixelType(sitk.sitkVectorFloat64)
        field = to_field.Execute(total)
        quality = self._quality(request, fixed_g, moving_g, fixed_ct, moving_ct, init, rigid, field)
        rid = str(uuid.uuid4())
        mat = np.array(_matrix(rigid))
        params = {"rx_deg": math.degrees(rigid.GetAngleX()), "ry_deg": math.degrees(rigid.GetAngleY()), "rz_deg": math.degrees(rigid.GetAngleZ()),
                  "tx_mm": float(mat[0, 3]), "ty_mm": float(mat[1, 3]), "tz_mm": float(mat[2, 3])}
        result = RegistrationResult(
            registration_id=rid, fixed_geometry_id=fixed_g.geometry_id, moving_geometry_id=moving_g.geometry_id,
            fixed_frame_of_reference_uid=fixed_g.frame_of_reference_uid, moving_frame_of_reference_uid=moving_g.frame_of_reference_uid,
            rigid_matrix=mat.tolist(), rigid_parameters=params, deformable=request.deformable,
            field_uri=str(self.store.field_path(rid)), quality=quality, request=request, seconds=round(time.time() - t0, 1),
            cache_key=key, created_at=datetime.now(timezone.utc),
        )
        self.store.save(result, field)
        logger.info("Registration {} ({} -> {}, {}): NCC {:.3f} -> {:.3f}, |HU| {:.0f} -> {:.0f}, {:.0f} s",
                    rid, moving_g.geometry_id, fixed_g.geometry_id, request.deformable.value, quality.before.ncc, quality.after.ncc,
                    quality.before.mean_abs_hu, quality.after.mean_abs_hu, result.seconds)
        return result

    # ----- quality --------------------------------------------------------

    @staticmethod
    def _similarity(fixed: np.ndarray, warped: np.ndarray, valid: np.ndarray) -> Similarity:
        f, w = fixed[valid].astype(np.float64), warped[valid].astype(np.float64)
        if f.size < 10:
            return Similarity(mean_abs_hu=float("nan"), ncc=float("nan"))
        fz, wz = f - f.mean(), w - w.mean()
        ncc = float((fz * wz).sum() / max(np.sqrt((fz ** 2).sum() * (wz ** 2).sum()), 1e-12))
        return Similarity(mean_abs_hu=float(np.abs(f - w).mean()), ncc=ncc)

    def _quality(self, request, fixed_g, moving_g, fixed_ct, moving_ct, init, rigid, field) -> RegistrationQuality:
        lo, hi = request.hu_window
        fixed = np.clip(sitk.GetArrayFromImage(fixed_ct), lo, hi)
        body = fixed > BODY_HU
        ones = moving_ct * 0.0 + 1.0

        def warp(tx):
            w = np.clip(sitk.GetArrayFromImage(sitk.Resample(moving_ct, fixed_ct, tx, sitk.sitkLinear, -1000.0, sitk.sitkFloat32)), lo, hi)
            inside = sitk.GetArrayFromImage(sitk.Resample(ones, fixed_ct, tx, sitk.sitkLinear, 0.0, sitk.sitkFloat32)) > 0.99
            return w, inside

        ftx = field_transform(field)
        w0, v0 = warp(init)
        w1, v1 = warp(rigid)
        w2, v2 = warp(ftx)
        q = RegistrationQuality(before=self._similarity(fixed, w0, body & v0),
                                rigid=self._similarity(fixed, w1, body & v1) if request.rigid else None,
                                after=self._similarity(fixed, w2, body & v2))
        u = sitk.GetArrayFromImage(field)
        mag = np.sqrt((u ** 2).sum(axis=-1))
        q.max_displacement_mm = float(mag[body].max()) if body.any() else 0.0
        if request.deformable is not DeformableMethod.none:
            jac = sitk.GetArrayFromImage(sitk.DisplacementFieldJacobianDeterminant(sitk.Cast(field, sitk.sitkVectorFloat64)))
            jb = jac[body & v2] if (body & v2).any() else jac.ravel()
            q.jacobian = JacobianStats(min=float(jb.min()), max=float(jb.max()), mean=float(jb.mean()),
                                       fraction_nonpositive=float((jb <= 0).mean()))
        if request.landmarks:
            fa, ma = self._masks(fixed_g), self._masks(moving_g)
            for lm in request.landmarks:
                pf, pm = _centroid(fa, lm.fixed_structure), _centroid(ma, lm.moving_structure)
                if pf is None or pm is None:
                    continue
                q.landmarks.append(LandmarkError(
                    fixed_structure=lm.fixed_structure, moving_structure=lm.moving_structure,
                    before_mm=float(np.linalg.norm(np.array(init.TransformPoint(tuple(pf))) - pm)),
                    rigid_mm=float(np.linalg.norm(np.array(rigid.TransformPoint(tuple(pf))) - pm)) if request.rigid else None,
                    after_mm=float(np.linalg.norm(np.array(ftx.TransformPoint(tuple(pf))) - pm))))
        return q

    # ----- mappings -------------------------------------------------------

    def get(self, registration_id: str) -> RegistrationResult:
        reg = self.store.get_by_id(registration_id)
        if reg is None:
            raise RegistrationError(f"registration {registration_id!r} not found")
        return reg

    def map_volume(self, registration_id: str, values_zyx: np.ndarray, moving_origin: Sequence[float], moving_spacing: Sequence[float],
                   interpolation: str = "linear", default: float = 0.0) -> np.ndarray:
        """A volume on the moving geometry's grid (a dose, a mask as float) on the fixed geometry's grid: sampled at T(x)."""
        field = self.store.load_field(registration_id)
        img = to_image(np.asarray(values_zyx, np.float32), moving_origin, moving_spacing)
        interp = {"linear": sitk.sitkLinear, "nearest": sitk.sitkNearestNeighbor}[interpolation]
        ref = _reference(sitk.GetArrayViewFromImage(field).shape[:3], field.GetOrigin(), field.GetSpacing())
        out = sitk.Resample(img, ref, field_transform(field), interp, float(default), sitk.sitkFloat32)
        return sitk.GetArrayFromImage(out)

    def export_dicom(self, registration_id: str, directory: Optional[Path] = None) -> List[dict]:
        """The registration as DICOM, in the fixed geometry's frame of reference: a Spatial Registration with the rigid
        part (when the two frames differ) and a Deformable Spatial Registration with the whole field (PS3.3 C.20)."""
        from ..dicom.writers import CaseContext
        from ..dicom.writers.reg import write_deformable_registration, write_spatial_registration

        reg = self.get(registration_id)
        fixed = self._geometry(reg.fixed_geometry_id)
        ctx = CaseContext.from_geometry(fixed)
        out = Path(directory) if directory else self.store.base_dir / registration_id / "dicom"
        written = []
        desc = f"radiarch registration {registration_id[:8]}, {reg.deformable.value}"
        if reg.moving_frame_of_reference_uid and reg.moving_frame_of_reference_uid != ctx.frame_of_reference_uid:
            m = np.linalg.inv(np.asarray(reg.rigid_matrix, float))           # DICOM: source (moving) points into the registered frame
            written.append(write_spatial_registration(ctx, reg.moving_frame_of_reference_uid, m, out / "REG_rigid.dcm", description=desc))
        field = self.store.load_field(registration_id)
        u = sitk.GetArrayFromImage(field)                                    # (z, y, x, 3)
        written.append(write_deformable_registration(ctx, reg.moving_frame_of_reference_uid or ctx.frame_of_reference_uid, u,
                                                     field.GetOrigin(), field.GetSpacing(), out / "REG_deformable.dcm", description=desc))
        return [w.__dict__ for w in written]

    def map_dose(self, registration_id: str, dose_id: str, dose_service=None):
        """A dose on the moving geometry, sampled at T(x) onto the fixed geometry's grid, as a new dose.

        The dose is pulled back point by point: each fixed voxel takes the dose of the moving point it maps
        to. Where tissue is compressed or stretched this does not conserve energy; for accumulation that
        error is the field's Jacobian away from 1, which the registration's quality reports. Outside the
        moving dose grid the mapped dose is zero.
        """
        import hashlib
        from .dose import DoseService, _summary_stats
        from .dose_persistence import DOSE_FILENAME, read_dose_volume

        dose_service = dose_service or DoseService()
        reg = self.get(registration_id)
        src = dose_service.dose_store.get_by_id(dose_id)
        if src is None:
            raise RegistrationError(f"dose {dose_id!r} not found")
        if src.geometry_id != reg.moving_geometry_id:
            raise RegistrationError(f"dose {dose_id!r} is on geometry {src.geometry_id}, not on the registration's moving geometry "
                                    f"{reg.moving_geometry_id}")
        key = hashlib.sha256(f"map-dose|{reg.cache_key}|{src.cache_key}".encode()).hexdigest()
        cached = dose_service.dose_store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        fixed_g, moving_g = self._geometry(reg.fixed_geometry_id), self._geometry(reg.moving_geometry_id)
        m_origin, m_spacing = _grid(moving_g)
        _, f_spacing = _grid(fixed_g)
        mapped = np.clip(self.map_volume(registration_id, read_dose_volume(Path(src.dose_grid_uri)), m_origin, m_spacing), 0.0, None)
        new_id = str(uuid.uuid4())
        result = src.model_copy(update={
            "dose_id": new_id, "geometry_id": fixed_g.geometry_id, "dose_grid_uri": str(dose_service.dose_store.base_dir / new_id / DOSE_FILENAME),
            "statistics": _summary_stats(mapped), "scenario_doses": None, "cache_key": key, "created_at": datetime.now(timezone.utc),
            "mapped_from": {"dose_id": dose_id, "registration_id": registration_id}})
        dose_service.dose_store.save(dose_id=new_id, cache_key=key, nominal_dose=mapped, spacing_mm=tuple(f_spacing), scenario_doses=None,
                                     result=result)
        logger.info("Mapped dose {} onto geometry {} through registration {} → dose {}", dose_id, fixed_g.geometry_id, registration_id, new_id)
        return result

    def propagate(self, registration_id: str, request: PropagateRequest) -> GeometryResult:
        """A derived geometry of the fixed one that adds the moving geometry's structures, warped onto its grid."""
        import hashlib
        from .masks import BITMASK, MAX_BITMASK_STRUCTURES, set_structure, structure_mask, to_bitmask
        from .persistence import GeometryPaths

        reg = self.get(registration_id)
        fixed_g, moving_g = self._geometry(reg.fixed_geometry_id), self._geometry(reg.moving_geometry_id)
        key = hashlib.sha256(f"{fixed_g.cache_key}|propagate|{reg.cache_key}|{request.model_dump_json()}".encode()).hexdigest()
        cached = self.geometry_service.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        names = list(moving_g.structure_index) if request.structures is None else list(request.structures)
        missing = [n for n in names if n not in moving_g.structure_index]
        if missing:
            raise RegistrationError(f"structures {missing} not in the moving geometry ({sorted(moving_g.structure_index)})")
        index: Dict[str, int] = {str(k): int(v) for k, v in fixed_g.structure_index.items()}
        clash = [n + request.suffix for n in names if (n + request.suffix) in index]
        if clash:
            raise RegistrationError(f"the fixed geometry already has {clash}; give a suffix to keep both")
        if len(index) + len(names) > MAX_BITMASK_STRUCTURES:
            raise RegistrationError(f"a geometry holds at most {MAX_BITMASK_STRUCTURES} structures")
        read = lambda p: sitk.GetArrayFromImage(sitk.ReadImage(str(p)))       # noqa: E731
        masks = to_bitmask(read(fixed_g.structure_masks_uri), index.values(), getattr(fixed_g, "mask_encoding", "labels") or "labels")
        density = read(fixed_g.density_grid_uri).astype(np.float32)
        ct = read(fixed_g.ct_grid_uri).astype(np.int16) if fixed_g.ct_grid_uri else None
        marr = self._masks(moving_g)
        m_origin, m_spacing = _grid(moving_g)
        for n in names:
            warped = self.map_volume(registration_id, marr.mask_zyx(marr.structure_index[n]).astype(np.float32), m_origin, m_spacing)
            label = max(index.values(), default=0) + 1
            index[n + request.suffix] = label
            masks = set_structure(masks, label, warped >= request.threshold, BITMASK)
        gid = str(uuid.uuid4())
        paths = GeometryPaths.for_id(self.geometry_service.store.base_dir, gid)
        result = fixed_g.model_copy(update={
            "geometry_id": gid, "density_grid_uri": str(paths.density), "structure_masks_uri": str(paths.masks),
            "ct_grid_uri": str(paths.ct) if ct is not None else None, "structure_index": index, "mask_encoding": BITMASK,
            "cache_key": key, "parent_geometry_id": fixed_g.geometry_id,
            "derived_operations": list(fixed_g.derived_operations) + [{"op": "propagate", "registration_id": registration_id,
                                                                       "moving_geometry_id": moving_g.geometry_id, "structures": names,
                                                                       "suffix": request.suffix, "threshold": request.threshold}],
        })
        # (z, y, x) here; the store takes (x, y, z)
        self.geometry_service.store.save(geometry_id=gid, cache_key=key, density=density.transpose(2, 1, 0), masks=masks.transpose(2, 1, 0),
                                         ct=ct.transpose(2, 1, 0) if ct is not None else None, result=result)
        logger.info("Propagated {} structure(s) from {} onto {} → geometry {}", len(names), moving_g.geometry_id, fixed_g.geometry_id, gid)
        return result


def _centroid(arrays, name: str) -> Optional[np.ndarray]:
    """A structure's centroid in patient coordinates (mm, x y z)."""
    if name not in arrays.structure_index:
        return None
    m = arrays.mask_zyx(arrays.structure_index[name])
    if not m.any():
        return None
    zyx = np.argwhere(m).mean(axis=0)
    return np.array([arrays.origin_mm[i] + zyx[2 - i] * arrays.spacing_mm[i] for i in range(3)])


__all__ = ["RegistrationError", "RegistrationService", "RegistrationStore", "field_transform", "to_image"]
