from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field



class PlanWorkflow(str, Enum):
    proton_impt_basic = "proton-impt-basic"
    proton_impt_optimized = "proton-impt-optimized"  # NEW
    proton_robust = "proton-robust"                  # NEW
    photon_ccc = "photon-ccc"                        # NEW


class ObjectiveType(str, Enum):
    d_min = "DMin"        # Minimum dose to structure
    d_max = "DMax"        # Maximum dose to structure
    d_uniform = "DUniform" # Uniform dose
    dvh_min = "DVHMin"    # DVH-based minimum
    dvh_max = "DVHMax"    # DVH-based maximum


class DoseObjective(BaseModel):
    structure_name: str          # ROI name (e.g. "PTV", "SpinalCord")
    objective_type: ObjectiveType
    dose_gy: float               # Dose value
    weight: float = 1.0          # Optimization weight
    volume_fraction: Optional[float] = None  # For DVH objectives (0-1)


class RobustnessConfig(BaseModel):
    """Phase 8C: Robustness parameters for proton optimization."""
    setup_systematic_error_mm: List[float] = [1.6, 1.6, 1.6]
    setup_random_error_mm: List[float] = [0.0, 0.0, 0.0]
    range_systematic_error_pct: float = 5.0
    selection_strategy: str = "REDUCED_SET"  # REDUCED_SET | ALL | RANDOM
    num_scenarios: int = 5


class PlanRequest(BaseModel):
    study_instance_uid: str = Field(..., description="DICOM Study Instance UID")
    segmentation_uid: Optional[str] = Field(None, description="RTSTRUCT/SEG UID with target contours")
    workflow_id: PlanWorkflow = Field(default=PlanWorkflow.proton_impt_basic)
    prescription_gy: float = Field(..., gt=0)
    fraction_count: int = Field(default=1, gt=0)
    beam_count: int = Field(default=1, ge=1, le=9, description="Number of beams (1-9)")
    notes: Optional[str] = None

    # Phase 8A: Optimization parameters
    objectives: Optional[List[DoseObjective]] = None
    optimization_method: str = "Scipy_L-BFGS-B"
    max_iterations: int = 50
    spot_spacing_mm: float = 5.0
    layer_spacing_mm: float = 5.0
    scoring_spacing_mm: List[float] = [2.0, 2.0, 2.0]
    nb_primaries_beamlets: float = 1e4    # For beamlet calc
    nb_primaries_final: float = 1e6       # For final dose

    # Phase 8B: Photon parameters
    mlc_leaf_width_mm: float = 10.0
    jaw_opening_mm: List[float] = [-50.0, 50.0]
    mu_per_beam: float = 5000.0

    # Phase 8C: Robustness
    robustness: Optional[RobustnessConfig] = None


class PlanSummary(BaseModel):
    id: str
    workflow_id: PlanWorkflow
    status: str
    created_at: datetime
    updated_at: datetime
    prescription_gy: float
    artifact_ids: List[str] = []


class PlanDetail(PlanSummary):
    study_instance_uid: str
    segmentation_uid: Optional[str]
    fraction_count: int
    beam_count: int = 1
    notes: Optional[str] = None
    job_id: Optional[str] = None
    qa_summary: Optional[dict] = None
    
    # Return optimization config in detail too
    objectives: Optional[List[DoseObjective]] = None
    robustness: Optional[RobustnessConfig] = None
