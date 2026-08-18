"""Live demo of Service 2 — Beam Model Service.

Runs the Beam Model Service end-to-end against the OpenTPS sample data
that ships with the repo. Builds a geometry first (Service 1), then
builds a *proton* beam model and a *photon* beam model against it,
printing per-build timings and fluence-element summaries. Each build
is run twice so the cache hit shows up clearly.

Usage:
    python demo/show_beam_model.py                # both modalities
    python demo/show_beam_model.py --proton-only
    python demo/show_beam_model.py --photon-only

Requirements:
    Whatever's in src/.venv (numpy, pydantic, fastapi, SimpleITK,
    SQLAlchemy, OpenTPS + MCsquare for the proton path). No docker,
    no Postgres, no Redis, no Celery worker.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Path + env setup BEFORE importing radiarch
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# Same env shim as the geometry demo: in-memory store, no broker, no Orthanc.
os.environ["RADIARCH_ORTHANC_USE_MOCK"] = "true"
os.environ["RADIARCH_DATABASE_URL"] = ""
os.environ["RADIARCH_BROKER_URL"] = "memory://"
os.environ["RADIARCH_RESULT_BACKEND"] = "cache+memory://"
os.environ["RADIARCH_DICOMWEB_URL"] = ""
os.environ["RADIARCH_ARTIFACT_DIR"] = str(_REPO_ROOT / "data" / "artifacts")

# Point the OpenTPS data loader at the SimpleFantom sample.
_TEST_DATA = (
    _REPO_ROOT
    / "tests"
    / "opentps"
    / "core"
    / "opentps-testData"
    / "SimpleFantomWithStruct"
)
os.environ["RADIARCH_OPENTPS_DATA_ROOT"] = str(_TEST_DATA)


from radiarch.models.beam_model import (  # noqa: E402
    BeamModelBuildRequest,
    BeamModelStage,
    BeamSetSpec,
    BeamSpec,
    DeliveryParams,
    Modality,
)
from radiarch.models.geometry import (  # noqa: E402
    GeometryBuildRequest,
    HUDensityModel,
    PatientRef,
)
from radiarch.services.beam_model import BeamModelService  # noqa: E402
from radiarch.services.geometry import GeometryService  # noqa: E402


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------

BAR = "─" * 64


def _h(label: str) -> None:
    print(f"\n{BAR}\n  {label}\n{BAR}")


def _row(key: str, value) -> None:
    print(f"  {key:<26} {value}")


def _on_progress(stage: BeamModelStage, fraction: float, message: str) -> None:
    pct = int(fraction * 100)
    print(f"    [{pct:3d}%] {stage.value:<24} {message}")


# ---------------------------------------------------------------------------
# Request builders — these are the same payloads an HTTP client would send
# ---------------------------------------------------------------------------

def _proton_request(geometry_id: str) -> BeamModelBuildRequest:
    """Two opposed proton fields with 5 mm spot + layer spacing."""
    return BeamModelBuildRequest(
        geometry_id=geometry_id,
        modality=Modality.proton_pbs,
        machine_model_id=None,
        beam_set=BeamSetSpec(
            isocenter_mm=[0.0, 0.0, 0.0],
            beams=[
                BeamSpec(beam_id="B1", gantry_deg=0.0, couch_deg=0.0,
                         collimator_deg=0.0),
                BeamSpec(beam_id="B2", gantry_deg=180.0, couch_deg=0.0,
                         collimator_deg=0.0),
            ],
        ),
        delivery_params=DeliveryParams(
            spot_spacing_mm=5.0,
            layer_spacing_mm=5.0,
        ),
    )


def _photon_request(geometry_id: str) -> BeamModelBuildRequest:
    """Three coplanar photon fields with 5 mm beamlets, 10x10 cm jaw."""
    return BeamModelBuildRequest(
        geometry_id=geometry_id,
        modality=Modality.photon_imrt,
        machine_model_id=None,
        beam_set=BeamSetSpec(
            isocenter_mm=[0.0, 0.0, 0.0],
            beams=[
                BeamSpec(beam_id="B1", gantry_deg=0.0),
                BeamSpec(beam_id="B2", gantry_deg=120.0),
                BeamSpec(beam_id="B3", gantry_deg=240.0),
            ],
        ),
        delivery_params=DeliveryParams(
            beamlet_size_mm=[5.0, 5.0],
            jaw_opening_mm=[100.0, 100.0],
        ),
    )


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

def _build_geometry() -> str:
    """Build (or hit cached) geometry — returns its geometry_id."""
    _h("Step 1 — Geometry Service (Service 1)")
    request = GeometryBuildRequest(
        patient_ref=PatientRef(
            dicom_study_uid="demo-study-001",
            ct_series_uid=None,
            rtstruct_uid=None,
        ),
        grid_spec=None,
        hu_to_density_model=HUDensityModel.stoichiometric,
    )
    _row("cache_key:", request.compute_cache_key()[:16] + "…")
    t0 = time.monotonic()
    result = GeometryService().build(request)
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    _row("geometry_id:", result.geometry_id)
    _row("elapsed:", f"{elapsed_ms:8.1f} ms")
    _row("density NIfTI:", Path(result.density_grid_uri).name)
    _row("structures:", list(result.structure_index.keys()))
    return result.geometry_id


def _build_beam_model(
    label: str,
    request: BeamModelBuildRequest,
    service: BeamModelService,
    show_progress: bool = True,
) -> tuple[Optional[object], float]:
    """Run service.build with timing. Returns (result, elapsed_ms)."""
    _h(label)
    _row("modality:", request.modality.value)
    _row("beams:", [b.beam_id for b in request.beam_set.beams])
    _row("cache_key:", request.compute_cache_key()[:16] + "…")
    t0 = time.monotonic()
    try:
        cb = _on_progress if show_progress else None
        result = service.build(request, progress_callback=cb)
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        _row("status:", "FAILED")
        _row("error:", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None, elapsed_ms
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    _row("beam_model_id:", result.beam_model_id)
    _row("elapsed:", f"{elapsed_ms:8.1f} ms")
    return result, elapsed_ms


def _print_result(result) -> None:
    fe = result.fluence_elements
    _h(f"BeamModelResult — {result.modality.value}")
    _row("beam_model_id:", result.beam_model_id)
    _row("cache_key:", result.cache_key[:16] + "…")
    _row("machine_model_id:", result.machine_model_id or "(default)")
    _row("plan artifact:", Path(result.beam_model_ref_uri).name)
    _row("fluence elements:", f"{fe.total_count} total")
    for pb in fe.per_beam:
        bits = [f"{pb.element_count} elements"]
        if pb.energy_layers:
            bits.append(f"{len(pb.energy_layers)} energy layers")
            bits.append(f"E ∈ [{min(pb.energy_layers):.1f}, "
                        f"{max(pb.energy_layers):.1f}] MeV")
        if pb.spots_per_layer:
            bits.append(f"{sum(pb.spots_per_layer)} spots")
        if pb.grid_dims:
            bits.append(f"grid {pb.grid_dims[0]}×{pb.grid_dims[1]}")
        if pb.active_beamlets is not None:
            bits.append(f"{pb.active_beamlets} active beamlets")
        print(f"    • {pb.beam_id}: " + ", ".join(bits))


def _run_modality(
    name: str,
    request: BeamModelBuildRequest,
    service: BeamModelService,
) -> None:
    """Build twice — first call exercises the full pipeline, second hits cache."""
    r1, t1 = _build_beam_model(f"{name} build #1 (cache miss)", request,
                               service, show_progress=True)
    if r1 is None:
        return
    r2, t2 = _build_beam_model(f"{name} build #2 (same request)", request,
                               service, show_progress=False)
    if r2 is not None and r1.beam_model_id == r2.beam_model_id:
        speedup = t1 / max(t2, 0.01)
        _row("speedup:", f"{speedup:6.1f}×")
        print("  ✓ same beam_model_id — cache hit confirmed")
        _print_result(r1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not _TEST_DATA.exists():
        print(f"ERROR: test data not found at {_TEST_DATA}", file=sys.stderr)
        sys.exit(1)

    do_proton = "--photon-only" not in sys.argv
    do_photon = "--proton-only" not in sys.argv

    _h("Radiarch Beam Model Service — Live Demo")
    _row("test data:", _TEST_DATA.relative_to(_REPO_ROOT))
    _row("artifact dir:", os.environ["RADIARCH_ARTIFACT_DIR"])
    _row("modalities:", ", ".join(
        ([Modality.proton_pbs.value] if do_proton else [])
        + ([Modality.photon_imrt.value] if do_photon else [])
    ))

    geometry_id = _build_geometry()

    service = BeamModelService()

    if do_proton:
        _run_modality("Proton (PROTON_PBS)", _proton_request(geometry_id), service)
    if do_photon:
        _run_modality("Photon (PHOTON_IMRT)", _photon_request(geometry_id), service)

    _h("Done")
    print(f"  Cached beam models live in: "
          f"{Path(os.environ['RADIARCH_ARTIFACT_DIR']) / 'beam_models'}")
    print()


if __name__ == "__main__":
    main()
