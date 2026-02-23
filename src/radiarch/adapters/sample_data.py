SAMPLE_STUDIES = {
    "1.2.840.113619.2.55.3.604688321.783.1459769131.467": {
        "StudyInstanceUID": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        "PatientName": "RADIARCH^PHANTOM",
        "PatientID": "RADIARCH001",
        "ModalitiesInStudy": ["CT"],
        "NumberOfStudyRelatedSeries": 1,
        "NumberOfStudyRelatedInstances": 120,
        "series": [
            {
                "SeriesInstanceUID": "1.2.840.113619.2.55.3.604688321.783.1459769131.468",
                "Modality": "CT",
                "BodyPartExamined": "ABDOMEN",
                "SliceThickness": 1.25,
                "ImageType": ["ORIGINAL", "PRIMARY", "AXIAL"],
            }
        ],
    }
}

SAMPLE_SEGMENTATIONS = {
    "1.2.246.352.63.1.4648126406368983830.13435.202201120812": {
        "labelset": [
            {"id": 1, "name": "PTV", "color": "#ff5f5f"},
            {"id": 2, "name": "CTV", "color": "#5f87ff"},
        ],
        "StudyInstanceUID": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
    }
}
