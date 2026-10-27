#!/usr/bin/env bash
# Put the bundled phantom (tests/data/SimpleFantomWithStruct) into the Docker Compose stack's Orthanc as one study and
# print its Study Instance UID on the last line. Used by smoke_test.sh and demo-viewer.sh.
#
# The phantom comes from OpenTPS's test data, which a PACS client cannot use as it stands: its CT has no Frame of
# Reference UID, and its structure set sits in a study of its own, says Modality RTDOSE and names no CT series. So, on
# the way in (the files on disk are not changed), the CT and the structure set get one Frame of Reference UID, and
# the structure set the CT's study, Modality RTSTRUCT and a reference to the CT series and its images. It runs inside
# the API container (pydicom, and the compose network's Orthanc with the API's Orthanc user). Loading it again is
# harmless: the UIDs are derived from the CT's, and Orthanc keeps one copy.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose exec -T api python - <<'PY'
import base64, glob, io, os, urllib.request

import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

root = os.environ.get("RADIARCH_DATA_ROOT") or "/data/radiarch/testData/SimpleFantomWithStruct"
url = os.environ.get("RADIARCH_ORTHANC_BASE_URL", "http://orthanc:8042").rstrip("/")
user, password = os.environ.get("RADIARCH_ORTHANC_USERNAME", ""), os.environ.get("RADIARCH_ORTHANC_PASSWORD", "")
headers = {"Content-Type": "application/dicom"}
if user:
    headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def post(data: bytes) -> None:
    urllib.request.urlopen(urllib.request.Request(f"{url}/instances", data=data, headers=headers, method="POST"), timeout=60).read()


def send(ds) -> None:
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    post(buf.getvalue())


cts = [pydicom.dcmread(f) for f in sorted(glob.glob(f"{root}/CT_*.dcm"))]
study, series = cts[0].StudyInstanceUID, cts[0].SeriesInstanceUID
frame = cts[0].get("FrameOfReferenceUID") or generate_uid(entropy_srcs=[series, "frame-of-reference"])
for ds in cts:
    ds.FrameOfReferenceUID = frame
    send(ds)
for f in glob.glob(f"{root}/RS*.dcm"):
    ds = pydicom.dcmread(f)
    ds.StudyInstanceUID, ds.Modality = study, "RTSTRUCT"
    images = []
    for ct in cts:
        ref = Dataset()
        ref.ReferencedSOPClassUID, ref.ReferencedSOPInstanceUID = ct.SOPClassUID, ct.SOPInstanceUID
        images.append(ref)
    rt_series = Dataset()
    rt_series.SeriesInstanceUID, rt_series.ContourImageSequence = series, Sequence(images)
    rt_study = Dataset()
    rt_study.ReferencedSOPClassUID, rt_study.ReferencedSOPInstanceUID = "1.2.840.10008.3.1.2.3.1", study
    rt_study.RTReferencedSeriesSequence = Sequence([rt_series])
    for_item = Dataset()
    for_item.FrameOfReferenceUID, for_item.RTReferencedStudySequence = frame, Sequence([rt_study])
    ds.ReferencedFrameOfReferenceSequence = Sequence([for_item])
    for roi in ds.get("StructureSetROISequence", []):
        roi.ReferencedFrameOfReferenceUID = frame
    send(ds)
print(f"{len(cts)} CT images and the structure set in Orthanc")
print(study)
PY
