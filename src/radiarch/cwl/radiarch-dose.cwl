#!/usr/bin/env cwl-runner
# radiarch dose recalculation of an RT Plan on a CT with its structures.
cwlVersion: v1.2
class: CommandLineTool
label: radiarch dose
doc: |
  Recomputes the dose of a DICOM RT Plan or RT Ion Plan on a CT series with its RT Structure Set: the plan is
  imported as a beam model with its own metersets and its dose computed by a radiarch engine (the pencil beam or
  collapsed cone for photons, MCsquare for protons). Writes the RT Dose, the plan as radiarch re-writes it, and the
  records as JSON. RESEARCH USE ONLY. NOT FOR CLINICAL USE.
baseCommand: [radiarch, dose]
arguments: [--export, rt, --json, dose.json]
hints:
  SoftwareRequirement:
    packages:
      radiarch: {}
inputs:
  ct:
    type: Directory
    doc: The CT series (and its RT Structure Set, unless one is given).
    inputBinding: {prefix: --ct}
  structures:
    type: ["null", File, Directory]
    doc: The RT Structure Set, or a folder with exactly one; the written RT Dose references it.
    inputBinding: {prefix: --structures}
  plan:
    type: [File, Directory]
    doc: The RT Plan or RT Ion Plan, or a folder with exactly one.
    inputBinding: {prefix: --plan}
  engine:
    type: string?
    doc: "auto (default), pb, ccc or mcsquare."
    inputBinding: {prefix: --engine}
  spacing_mm:
    type: float?
    doc: Dose grid spacing in mm (default 3; 0 = the CT's own grid).
    inputBinding: {prefix: --spacing}
  machine:
    type: string?
    doc: The machine model the plan is delivered on.
    inputBinding: {prefix: --machine}
  dose_only:
    type: boolean?
    doc: Write only the RT Dose, referencing the given plan (no re-written plan or structure set).
    inputBinding: {prefix: --dose-only}
  label:
    type: string?
    doc: RT Plan label (default RESEARCH).
    inputBinding: {prefix: --label}
  server:
    type: string?
    doc: A radiarch API base URL; without it the computation runs inside the tool's process.
    inputBinding: {prefix: --server}
outputs:
  rt_objects:
    type: Directory
    doc: The RT Dose and the RT Plan as re-written (and a structure set when none was given).
    outputBinding: {glob: rt}
  dose:
    type: File
    doc: The geometry, beam model, dose and export records as JSON.
    outputBinding: {glob: dose.json}
