"""R11.7: the MCO panel of the standalone viewer, in a browser.

A Pareto set's deliverable plan (tests/test_r11_viewer_client.py's ``mco_export``) is pushed to Orthanc with its CT,
radiarch's API is served with a key, and the viewer image is started in front of both (test_r13_viewer_browser.py's
fixtures). Headless Chromium opens the study in the plan review mode, opens the MCO panel and checks:
- the panel finds the Pareto set behind the dose and shows a slider per trade-off;
- a value typed for a trade-off navigates: a new state, the trade-off at most that value;
- "Make deliverable" makes the state a plan and shows its deviation table;
- "Export and open" writes it.
Needs what the R13 browser test needs (CI's Viewer job).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from test_r6_rt_export_service import env  # noqa: F401
from test_r11_viewer_client import mco_export
from test_r13_viewer import _ct_slices, _loaded_ct
from test_r13_viewer_browser import CHROMIUM_ARGS, DICOMWEB, _forget_study, pytestmark, viewer  # noqa: F401
from test_r13_viewer_client import api  # noqa: F401


def test_the_mco_panel_navigates_and_makes_a_plan_deliverable(env, viewer, tmp_path):  # noqa: F811
    import numpy as np
    from playwright.sync_api import expect, sync_playwright

    from radiarch.adapters.dicomweb import DICOMwebNotifier

    vol = _loaded_ct().ct
    _forget_study(vol.studyInstanceUID)
    ct_dir = tmp_path / "ct"
    ct_dir.mkdir()
    n = vol.imageArray.shape[1]
    yy, xx = np.mgrid[:n, :n]
    disc = np.where(((yy - (n - 1) / 2) ** 2 + (xx - (n - 1) / 2) ** 2) < (n / 2.7) ** 2, 0, -1000)
    assert DICOMwebNotifier(url=DICOMWEB).store_instances([str(p) for p in _ct_slices(ct_dir, hu=np.broadcast_to(disc, vol.imageArray.shape))],
                                                         raise_errors=True)
    svc, exp, res, plan = mco_export()
    assert svc.push(exp.export_id, url=DICOMWEB, kinds=["RTSTRUCT", "RTPLAN", "RTDOSE"]).error is None
    mid = 0.5 * (res.ideal_gy[1] + res.nadir_gy[1])

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
            hide.click()
            expect(page.get_by_text("Isodoses in % of the prescription (2.00 Gy)")).to_be_visible(timeout=90000)

            page.locator('[data-cy="radiarch-mco-btn"]').click()
            expect(page.get_by_text(f"{len(res.plans)} plans, error bound")).to_be_visible(timeout=60000)
            expect(page.get_by_label("UniformRMS(PTV) slider")).to_be_visible()
            field = page.get_by_label("MeanDose(OAR) (Gy)")
            field.fill(f"{mid:.2f}")
            field.press("Enter")
            expect(page.locator('[data-cy="radiarch-mco-state"]')).to_have_text(re.compile(r"MeanDose\(OAR\) to "), timeout=60000)
            assert float(field.input_value()) <= round(mid, 2) + 0.01
            expect(page.get_by_text("DVHs of the navigated blend")).to_be_visible()
            page.screenshot(path=str(artifacts / "viewer-mco-navigated.png"))

            page.get_by_role("button", name="Make deliverable").click()
            expect(page.locator('[data-cy="radiarch-mco-deviation"]')).to_be_visible(timeout=180000)
            page.get_by_role("button", name="Export and open").click()
            expect(page.get_by_text(re.compile(r"Open the deliverable plan|Sent to the image server|Exported \("))).to_be_visible(timeout=120000)
            page.screenshot(path=str(artifacts / "viewer-mco-deliverable.png"))
        except Exception:
            page.screenshot(path=str(artifacts / "viewer-mco-failure.png"))
            (artifacts / "viewer-mco-failure.html").write_text(page.content())
            (artifacts / "viewer-mco-console.txt").write_text("\n".join(errors))
            raise
        finally:
            browser.close()
