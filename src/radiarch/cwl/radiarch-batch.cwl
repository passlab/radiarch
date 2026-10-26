#!/usr/bin/env cwl-runner
# radiarch batch planning: one planning protocol over a list of cases (roadmap R10).
cwlVersion: v1.2
class: CommandLineTool
label: radiarch batch
doc: |
  Plans every case of a CSV list (case_id, study_uid, data_root relative to the data directory, optional
  spacing_mm) with one radiarch planning protocol; a case that fails is recorded and the batch goes on.
  Writes a summary table of goals per case, every run as JSON lines, and each case's RT objects.
  RESEARCH USE ONLY. NOT FOR CLINICAL USE.
baseCommand: [radiarch, batch]
arguments: [--out, results, --export]
hints:
  SoftwareRequirement:
    packages:
      radiarch: {}
successCodes: [0, 1]
inputs:
  protocol:
    type: string
    doc: A shipped protocol id or the path of a protocol JSON file.
    inputBinding: {prefix: --protocol}
  cases:
    type: File
    doc: "CSV with a header: case_id, study_uid[, data_root, spacing_mm]."
    inputBinding: {prefix: --cases}
  data:
    type: Directory
    doc: The directory the cases' data_root values are relative to.
    inputBinding: {prefix: --data-root}
  spacing_mm:
    type: float?
    doc: Dose grid spacing in mm for cases without their own.
    inputBinding: {prefix: --spacing}
  server:
    type: string?
    doc: A radiarch API base URL; without it the planning runs inside the tool's process.
    inputBinding: {prefix: --server}
outputs:
  summary:
    type: File
    outputBinding: {glob: results/summary.csv}
  summary_md:
    type: File
    outputBinding: {glob: results/summary.md}
  runs:
    type: File
    outputBinding: {glob: results/runs.jsonl}
  results:
    type: Directory
    doc: The summary files and one directory of RT objects per case.
    outputBinding: {glob: results}
