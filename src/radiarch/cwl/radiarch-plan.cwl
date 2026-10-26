#!/usr/bin/env cwl-runner
# radiarch auto-planning of one patient with a planning protocol (roadmap R10).
cwlVersion: v1.2
class: CommandLineTool
label: radiarch plan
doc: |
  Plans one patient with a radiarch planning protocol (a shipped protocol id or a protocol JSON file): the
  protocol's structures, goal-driven optimization, a deliverable plan normalised to the target's coverage goal,
  its goals; writes the RT objects and the run as JSON. RESEARCH USE ONLY. NOT FOR CLINICAL USE.
baseCommand: [radiarch, plan]
arguments: [--export, rt, --json, run.json]
hints:
  SoftwareRequirement:
    packages:
      radiarch: {}
inputs:
  protocol:
    type: string
    doc: A shipped protocol id (``radiarch protocols``) or the path of a protocol JSON file.
    inputBinding: {prefix: --protocol}
  study_uid:
    type: string
    doc: The DICOM study instance UID.
    inputBinding: {prefix: --study}
  dicom:
    type: Directory
    doc: The CT series and its RT Structure Set.
    inputBinding: {prefix: --data}
  spacing_mm:
    type: float?
    doc: Dose grid spacing in mm.
    inputBinding: {prefix: --spacing}
  label:
    type: string?
    doc: RT Plan and structure set label (default RESEARCH).
    inputBinding: {prefix: --label}
  server:
    type: string?
    doc: A radiarch API base URL; without it the planning runs inside the tool's process.
    inputBinding: {prefix: --server}
outputs:
  rt_objects:
    type: Directory
    doc: RT Structure Set, RT Plan and RT Dose.
    outputBinding: {glob: rt}
  run:
    type: File
    doc: The protocol run (plan, dose, goals, normalisation) as JSON.
    outputBinding: {glob: run.json}
