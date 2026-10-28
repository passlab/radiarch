"""A plan exported again with the same settings is the same export (the same UIDs, which an archive stores once);
``new_export`` writes a copy instead, marked "copy N" and referencing the earlier plan as its predecessor."""

from __future__ import annotations

import shutil
from pathlib import Path

import pydicom
import pytest

from radiarch.models.rt_export import PrescriptionSpec, RTExportRequest

from test_r6_rt_export_service import _photon_pipeline, env  # noqa: F401  (stub CT, the test machine and engines)


def _request(seq, **kw):
    return RTExportRequest(**{"sequence_id": seq.sequence_id, "label": "R6TEST", "prescription": PrescriptionSpec(dose_gy=2.0, fractions=2),
                              "drr_size_mm": (80.0, 80.0), "drr_pixel_mm": (2.0, 2.0), **kw})


def _uids(result):
    return sorted(o.sop_instance_uid for o in result.objects)


def test_the_same_plan_and_settings_are_the_same_export(env, monkeypatch):
    from radiarch.services.rt_export import RTExportService

    _, _, _, seq = _photon_pipeline()
    svc = RTExportService()
    pushed = []
    monkeypatch.setattr(svc, "_push", lambda paths: pushed.append(list(paths)) or (True, None))

    first = svc.export(_request(seq))
    again = svc.export(_request(seq, push=True))
    assert again.reused and not first.reused and first.copy_number == again.copy_number == 1
    assert again.export_id == first.export_id and _uids(again) == _uids(first)
    assert [p.name for p in svc.base_dir.iterdir()] == [first.export_id]               # nothing written
    assert pushed == [[o.path for o in first.objects]] and svc.get(first.export_id).pushed      # the same objects, pushed again
    assert not svc.get(first.export_id).reused                                          # the flag is the response's, not stored

    # another setting that shapes the objects is another export
    other = svc.export(_request(seq, label="OTHER"))
    assert other.export_id != first.export_id and not other.reused and other.copy_number == 1
    assert set(_uids(other)).isdisjoint(_uids(first))


def test_a_new_export_is_a_marked_copy_of_the_latest(env):
    from radiarch.services.rt_export import RTExportService

    _, _, _, seq = _photon_pipeline()
    svc = RTExportService()
    first = svc.export(_request(seq))
    copy = svc.export(_request(seq, new_export=True))
    assert copy.copy_number == 2 and copy.copy_of == first.export_id and not copy.reused
    assert copy.cache_key == first.cache_key and set(_uids(copy)).isdisjoint(_uids(first))

    rp = pydicom.dcmread(svc.file_path(copy.export_id, "RP.dcm"))
    assert rp.RTPlanLabel == "R6TEST copy 2" and str(rp.RTPlanDescription).endswith("copy 2")
    ref = rp.ReferencedRTPlanSequence[0]
    assert ref.ReferencedSOPInstanceUID == first.plan_sop_instance_uid and ref.RTPlanRelationship == "PREDECESSOR"
    for o in copy.objects:              # every series says it is the copy; the first export's do not
        assert pydicom.dcmread(o.path, stop_before_pixels=True).SeriesDescription.endswith("(copy 2)"), o.file_name
    assert not pydicom.dcmread(first.objects[0].path, stop_before_pixels=True).SeriesDescription.endswith(")")

    # by default the latest export of the plan comes back; another copy follows it
    assert svc.export(_request(seq)).export_id == copy.export_id
    third = svc.export(_request(seq, new_export=True))
    assert third.copy_number == 3 and third.copy_of == copy.export_id
    rp3 = pydicom.dcmread(svc.file_path(third.export_id, "RP.dcm"))
    assert rp3.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == copy.plan_sop_instance_uid
    assert [r.copy_number for r in svc.exports_of(first.cache_key)] == [1, 2, 3]


def test_an_export_without_its_files_is_written_again(env):
    from radiarch.services.rt_export import RTExportService

    _, _, _, seq = _photon_pipeline()
    svc = RTExportService()
    first = svc.export(_request(seq))
    Path(first.objects[0].path).unlink()
    again = svc.export(_request(seq))
    assert again.export_id != first.export_id and not again.reused and again.copy_number == 1
    shutil.rmtree(svc.directory(first.export_id))
    assert [r.export_id for r in svc.exports_of(first.cache_key)] == [again.export_id]


def test_the_key_leaves_out_what_does_not_shape_the_objects():
    base = RTExportRequest(sequence_id="s1")
    assert base.compute_cache_key() == RTExportRequest(sequence_id="s1", push=True, new_export=True).compute_cache_key()
    for change in ({"label": "OTHER"}, {"structures": ["PTV"]}, {"sequence_id": "s2"}, {"objects": ["rtstruct", "rtplan"]},
                   {"prescription": PrescriptionSpec(dose_gy=60.0, fractions=30)}):
        assert RTExportRequest(**{"sequence_id": "s1", **change}).compute_cache_key() != base.compute_cache_key(), change


@pytest.mark.parametrize("label, expected", [("RESEARCH", "RESEARCH copy 2"), ("RESEARCH-LUNG-DEMO", "RESEARCH copy 2")])
def test_a_copy_label_fits_the_plan_label(label, expected):
    from radiarch.services.rt_export import _copy_label

    assert _copy_label(label, 2) == expected and len(expected) <= 16
