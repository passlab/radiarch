"""Roadmap R13.2d: the standalone viewer in a browser, end to end.

The test assembles a full deployment:
- a CT and an export of radiarch's are pushed to Orthanc;
- radiarch's API is served with an API key required;
- the `radiarch-viewer` image is started, with its proxy pointing at both and adding the key.
Headless Chromium then opens the study in the plan review mode and checks:
- the dose is drawn over the CT, in isodose colours of the prescription;
- the dose panel shows the DVHs from the RT Dose;
- the radiarch panel finds the plan, and Evaluate grades the goals.

It needs:
- RADIARCH_TEST_VIEWER_IMAGE (the image tag);
- RADIARCH_TEST_DICOMWEB_URL (Orthanc's DICOMweb);
- docker;
- Playwright with Chromium.
CI's Viewer job provides all of them. Screenshots go to RADIARCH_TEST_ARTIFACTS when set.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from test_r6_rt_export_service import env  # noqa: F401
from test_r13_viewer import _ct_slices, _export, _loaded_ct
from test_r13_viewer_client import KEY, _free_port, api  # noqa: F401

IMAGE = os.environ.get("RADIARCH_TEST_VIEWER_IMAGE", "")
DICOMWEB = os.environ.get("RADIARCH_TEST_DICOMWEB_URL", "").rstrip("/")

try:
    import playwright.sync_api  # noqa: F401
    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False

pytestmark = pytest.mark.skipif(
    not (IMAGE and DICOMWEB and HAVE_PLAYWRIGHT and shutil.which("docker")),
    reason="needs RADIARCH_TEST_VIEWER_IMAGE, RADIARCH_TEST_DICOMWEB_URL, docker and Playwright (CI's Viewer job)",
)


def _orthanc_root() -> str:
    return DICOMWEB[: -len("/dicom-web")] if DICOMWEB.endswith("/dicom-web") else DICOMWEB


def _forget_study(study_uid: str) -> None:
    """Remove the study from Orthanc, so only this test's objects are in it."""
    import json

    req = urllib.request.Request(f"{_orthanc_root()}/tools/lookup", data=study_uid.encode(), method="POST")
    for hit in json.loads(urllib.request.urlopen(req, timeout=30).read() or b"[]"):
        if hit.get("Type") == "Study":
            urllib.request.urlopen(urllib.request.Request(f"{_orthanc_root()}/studies/{hit['ID']}", method="DELETE"), timeout=30)


@pytest.fixture()
def viewer(api):  # noqa: F811
    port = _free_port()
    radiarch = api[: -len("/api/v1")]
    name = f"radiarch-viewer-test-{port}"
    subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "--network", "host",
                    "-e", f"VIEWER_PORT={port}", "-e", f"ORTHANC_URL={_orthanc_root()}", "-e", f"RADIARCH_URL={radiarch}",
                    "-e", f"RADIARCH_API_KEY={KEY}", IMAGE], check=True, capture_output=True)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 60
        while True:
            try:
                urllib.request.urlopen(f"{base}/app-config.js", timeout=5)
                break
            except OSError:
                assert time.time() < deadline, "the viewer did not start"
                time.sleep(0.5)
        yield base
    finally:
        logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        if os.environ.get("RADIARCH_TEST_ARTIFACTS"):
            Path(os.environ["RADIARCH_TEST_ARTIFACTS"]).mkdir(parents=True, exist_ok=True)
            (Path(os.environ["RADIARCH_TEST_ARTIFACTS"]) / "viewer-nginx.log").write_text(logs)


# Software WebGL for headless Chromium (no GPU on the runner). It draws the CT; it does not draw a second volume, so the
# dose is checked inside OHIF (its values on the CT's grid, its isodose colours and opacities) rather than in pixels;
# the colour wash on screen is checked by hand (R13.3).
CHROMIUM_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]

VIEWPORT_STATE = """() => {
  const vp = window.services.cornerstoneViewportService.getRenderingEngine().getViewports()[0];
  return vp.getActors().map(a => {
    const d = vp.getImageData(a.referencedId);
    const props = vp.getProperties(a.referencedId);
    const tf = a.actor.getProperty().getRGBTransferFunction(0);
    const of = a.actor.getProperty().getScalarOpacity(0);
    const at = v => { const c = [0, 0, 0]; tf.getColor(v, c); return { value: v, rgb: c.map(x => +x.toFixed(2)), opacity: +of.getValue(v).toFixed(3) }; };
    return { id: a.referencedId, dims: d.dimensions, range: d.voxelManager.getRange(), colormap: props.colormap?.name ?? null,
             voi: props.voiRange, samples: [20, 40, 60, 75, 85, 92, 97, 103, 110].map(at) };
  });
}"""


def _grey_pixels(png: bytes) -> int:
    """Pixels of a screenshot brighter than the background: the CT drawn."""
    import io

    import numpy as np
    from PIL import Image

    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    return int((rgb.mean(axis=2) > 100).sum())


def test_a_plan_in_the_standalone_viewer(env, viewer, tmp_path):  # noqa: F811
    import numpy as np
    import pydicom
    from playwright.sync_api import expect, sync_playwright

    from radiarch.adapters.dicomweb import DICOMwebNotifier
    from radiarch.dicom import read_rtdose

    vol = _loaded_ct().ct
    _forget_study(vol.studyInstanceUID)
    ct_dir = tmp_path / "ct"
    ct_dir.mkdir()
    n = vol.imageArray.shape[1]
    yy, xx = np.mgrid[:n, :n]
    disc = np.where(((yy - (n - 1) / 2) ** 2 + (xx - (n - 1) / 2) ** 2) < (n / 2.7) ** 2, 0, -1000)   # water in air
    hu = np.broadcast_to(disc, vol.imageArray.shape)
    assert DICOMwebNotifier(url=DICOMWEB).store_instances([str(p) for p in _ct_slices(ct_dir, hu=hu)], raise_errors=True)
    svc, res = _export()
    assert svc.push(res.export_id, url=DICOMWEB, kinds=["RTSTRUCT", "RTPLAN", "RTDOSE"]).error is None
    # the dose in % of the 2 Gy prescription, on the CT's grid (here the same grid)
    pct = read_rtdose(svc.file_path(res.export_id, "RD.dcm")).dose_zyx / 2.0 * 100.0
    assert pydicom.dcmread(svc.file_path(res.export_id, "RP.dcm")).DoseReferenceSequence[0].TargetPrescriptionDose == 2.0

    artifacts = Path(os.environ.get("RADIARCH_TEST_ARTIFACTS", tmp_path))
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=CHROMIUM_ARGS)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        try:
            page.goto(f"{viewer}/plan-review?StudyInstanceUIDs={vol.studyInstanceUID}", wait_until="domcontentloaded")
            hide = page.get_by_role("button", name="Confirm and hide")
            hide.wait_for(timeout=60000)
            hide.click()                                                  # OHIF's investigational-use notice

            # the hanging protocol opens the dose over its CT, labelled with the prescription it is drawn against
            expect(page.get_by_text("Isodoses in % of the prescription (2.00 Gy)")).to_be_visible(timeout=90000)
            # the dose panel: the RT Dose's own DVHs, named by the structure set
            expect(page.get_by_text("DVHs from the RT Dose file")).to_be_visible(timeout=60000)
            expect(page.locator("td", has_text="PTV").first).to_be_visible()
            page.wait_for_timeout(5000)
            assert _grey_pixels(page.locator("[data-viewportid=\"rtDose\"]").screenshot()) > 1000, "the CT is not drawn"
            page.screenshot(path=str(artifacts / "viewer-dose.png"))

            # inside OHIF: the CT, then the dose on the CT's grid in % of the prescription with the isodose colours
            ct_actor, dose_actor = page.evaluate(VIEWPORT_STATE)
            assert ct_actor["range"] == [-1000, 0] and dose_actor["id"].startswith("rtdose.")
            assert dose_actor["dims"] == ct_actor["dims"]
            assert dose_actor["range"] == pytest.approx([float(pct.min()), float(pct.max())], abs=0.05)
            assert dose_actor["colormap"] == "radiarch-isodose"
            assert dose_actor["voi"]["lower"] == 0 and dose_actor["voi"]["upper"] == pytest.approx(120, abs=1.5)
            by_value = {s["value"]: s for s in dose_actor["samples"]}
            assert by_value[20]["opacity"] == 0 and all(by_value[v]["opacity"] > 0 for v in (40, 60, 75, 85, 92, 97, 103, 110))
            bands = [tuple(by_value[v]["rgb"]) for v in (40, 60, 75, 85, 92, 97, 103, 110)]
            assert len(set(bands)) == len(bands), bands                   # one colour per isodose band

            # the radiarch panel: the plan behind the dose, then its goals graded by radiarch
            page.locator('[data-cy="radiarch-plan-btn"]').click()
            expect(page.get_by_text("2.0 Gy in 2 fractions")).to_be_visible(timeout=60000)
            page.get_by_label("Goal template").select_option("rtog-0617")
            page.get_by_role("button", name="Evaluate").click()
            expect(page.get_by_text("Goals:")).to_be_visible(timeout=120000)
            expect(page.get_by_text("DVHs from radiarch's evaluation")).to_be_visible()
            page.screenshot(path=str(artifacts / "viewer-goals.png"))
        except Exception:
            page.screenshot(path=str(artifacts / "viewer-failure.png"))
            (artifacts / "viewer-failure.html").write_text(page.content())
            (artifacts / "viewer-console.txt").write_text("\n".join(errors))
            raise
        finally:
            browser.close()
    assert not [e for e in errors if "Error loading displaySet" in e or "RT Dose:" in e], errors
