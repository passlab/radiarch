"""Live demo of Service 1 — Geometry Service.

Runs the Geometry Service end-to-end and prints the GeometryResult,
optionally rendering an axial slice with structure masks overlaid.

Usage:
    # 1. Bundled SimpleFantom sample (dev fallback)
    python demo/show_geometry.py
    python demo/show_geometry.py --show

    # 2. A real DICOM study you provide as a ZIP — exercises the same
    #    code path the production HTTP upload endpoint uses.
    python demo/show_geometry.py --upload /path/to/study.zip
    python demo/show_geometry.py --upload /path/to/study.zip --show

Requirements:
    Whatever's in src/.venv (numpy, scipy, pydantic, SimpleITK,
    matplotlib if you pass --show). No docker, no Orthanc, no
    Postgres, no Celery worker.

Where to get a real DICOM study:
    See demo/README_DICOM.md — points at TCIA's free LCTSC collection
    (CT + RTSTRUCT, anonymized).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Path + env setup BEFORE importing radiarch
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# Mock Orthanc → service falls back to disk loading.
os.environ["RADIARCH_ORTHANC_USE_MOCK"] = "true"
# No Postgres/Redis needed for direct service usage.
os.environ["RADIARCH_DATABASE_URL"] = ""
os.environ["RADIARCH_BROKER_URL"] = "memory://"
os.environ["RADIARCH_RESULT_BACKEND"] = "cache+memory://"
os.environ["RADIARCH_DICOMWEB_URL"] = ""
# Override docker-mode artifact dir (which lives at /data/artifacts inside the
# container) with a local path so the demo writes to the repo, not the root fs.
os.environ["RADIARCH_ARTIFACT_DIR"] = str(_REPO_ROOT / "data" / "artifacts")
# Point at the test fixture that ships with the repo.
_TEST_DATA = (
    _REPO_ROOT
    / "tests"
    / "opentps"
    / "core"
    / "opentps-testData"
    / "SimpleFantomWithStruct"
)
os.environ["RADIARCH_OPENTPS_DATA_ROOT"] = str(_TEST_DATA)


from radiarch.config import get_settings  # noqa: E402
from radiarch.models.geometry import (  # noqa: E402
    GeometryBuildRequest,
    HUDensityModel,
    PatientRef,
)
from radiarch.services.geometry import GeometryService  # noqa: E402


# ---------------------------------------------------------------------------
# Upload helper — mirrors what POST /uploads/dicom does, in-process so the
# demo doesn't need a running server.
# ---------------------------------------------------------------------------

def _ingest_upload_zip(zip_path: Path) -> str:
    """Extract a DICOM ZIP into the configured upload_dir, return an upload_id."""
    import shutil
    import uuid
    import zipfile

    settings = get_settings()
    base = settings.upload_dir or str(Path(settings.artifact_dir) / "uploads")
    upload_root = Path(base).expanduser().resolve()
    upload_root.mkdir(parents=True, exist_ok=True)

    upload_id = str(uuid.uuid4())
    dest = upload_root / upload_id
    dest.mkdir()

    # Refuse zip-slip traversal — same check as the upload endpoint.
    with zipfile.ZipFile(zip_path) as zf:
        dest_resolved = dest.resolve()
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                shutil.rmtree(dest, ignore_errors=True)
                raise ValueError(f"Refusing unsafe ZIP entry: {member.filename!r}")
        zf.extractall(dest)

    # Quick sanity check.
    dcm_count = sum(1 for p in dest.rglob("*.dcm") if p.is_file())
    print(f"  extracted {dcm_count} .dcm files into {dest}")
    return upload_id


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------

BAR = "─" * 64


def _h(label: str) -> None:
    print(f"\n{BAR}\n  {label}\n{BAR}")


def _row(key: str, value) -> None:
    print(f"  {key:<26} {value}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _parse_upload_arg() -> Optional[Path]:
    if "--upload" not in sys.argv:
        return None
    idx = sys.argv.index("--upload")
    if idx + 1 >= len(sys.argv):
        print("ERROR: --upload requires a path to a ZIP file", file=sys.stderr)
        sys.exit(2)
    return Path(sys.argv[idx + 1]).expanduser().resolve()


def main() -> None:
    upload_zip = _parse_upload_arg()

    _h("Radiarch Geometry Service — Live Demo")

    if upload_zip is not None:
        if not upload_zip.is_file():
            print(f"ERROR: upload ZIP not found at {upload_zip}", file=sys.stderr)
            sys.exit(1)
        _row("source:", "ZIP upload")
        _row("zip path:", upload_zip)
        upload_id = _ingest_upload_zip(upload_zip)
        _row("upload_id:", upload_id)
        patient_ref = PatientRef(upload_id=upload_id)
    else:
        if not _TEST_DATA.exists():
            print(f"ERROR: test data not found at {_TEST_DATA}", file=sys.stderr)
            print("Either provide --upload <study.zip> or place the SimpleFantom")
            print("sample at the expected location.")
            sys.exit(1)
        _row("source:", "bundled SimpleFantom (dev fallback)")
        _row("test data:", _TEST_DATA.relative_to(_REPO_ROOT))
        patient_ref = PatientRef(
            dicom_study_uid="demo-study-001",
            ct_series_uid=None,
            rtstruct_uid=None,
        )

    # Build the request — same shape an HTTP client would send.
    request = GeometryBuildRequest(
        patient_ref=patient_ref,
        grid_spec=None,                                 # match CT grid
        hu_to_density_model=HUDensityModel.stoichiometric,
    )

    _h("Request")
    _row("dicom_study_uid:", request.patient_ref.dicom_study_uid)
    _row("hu_to_density_model:", request.hu_to_density_model.value)
    _row("cache_key:", request.compute_cache_key()[:16] + "…")

    service = GeometryService()

    # First call — could be a cache miss (full build) or a cache hit
    # if you've run this script before.
    _h("Build #1")
    t0 = time.monotonic()
    result1 = service.build(request)
    t1_ms = (time.monotonic() - t0) * 1000.0
    _row("geometry_id:", result1.geometry_id)
    _row("elapsed:", f"{t1_ms:8.1f} ms")

    # Second call — guaranteed cache hit.
    _h("Build #2 (same request)")
    t0 = time.monotonic()
    result2 = service.build(request)
    t2_ms = (time.monotonic() - t0) * 1000.0
    _row("geometry_id:", result2.geometry_id)
    _row("elapsed:", f"{t2_ms:8.1f} ms")
    _row("speedup:", f"{t1_ms / max(t2_ms, 0.01):6.1f}×")
    if result1.geometry_id == result2.geometry_id:
        print("  ✓ same geometry_id — cache hit confirmed")

    _h("GeometryResult")
    _row("modality:", result1.ct_metadata.modality)
    _row("patient_name:", result1.ct_metadata.patient_name)
    _row("num_slices:", result1.ct_metadata.num_slices)
    _row("frame_of_reference_uid:", result1.frame_of_reference_uid or "(none)")
    _row("grid spacing (mm):", result1.grid_spec.spacing_mm)
    _row("grid origin (mm):", result1.grid_spec.origin_mm)
    _row("grid size (vox):", result1.grid_spec.size)
    _row("structure_index:", dict(result1.structure_index))
    _row("density NIfTI:", result1.density_grid_uri)
    _row("masks NIfTI:", result1.structure_masks_uri)

    if "--show" in sys.argv:
        _show_axial_slices(result1)
    else:
        print(f"\n  (pass --show to also render axial slices)")
    print()


# ---------------------------------------------------------------------------
# Optional visualization
# ---------------------------------------------------------------------------

def _show_axial_slices(result) -> None:
    """Render the middle axial slice — density, masks, overlay."""
    try:
        import numpy as np
        import SimpleITK as sitk
        import matplotlib.pyplot as plt
    except ImportError as exc:
        print(f"\n  (--show needs matplotlib + SimpleITK: {exc})")
        return

    density = sitk.GetArrayFromImage(sitk.ReadImage(result.density_grid_uri))
    masks = sitk.GetArrayFromImage(sitk.ReadImage(result.structure_masks_uri))
    z = density.shape[0] // 2  # middle axial slice

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    axes[0].imshow(density[z], cmap="gray")
    axes[0].set_title(f"Density (slice {z})")
    axes[1].imshow(masks[z], cmap="tab10", vmin=0, vmax=10)
    axes[1].set_title("Structure masks")
    axes[2].imshow(density[z], cmap="gray")
    masked = np.ma.masked_where(masks[z] == 0, masks[z])
    axes[2].imshow(masked, cmap="tab10", alpha=0.5, vmin=0, vmax=10)
    axes[2].set_title("Overlay")
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])

    plt.suptitle(
        f"Geometry {result.geometry_id[:8]}…  "
        f"({', '.join(result.structure_index.keys())})",
        fontsize=11,
    )
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
