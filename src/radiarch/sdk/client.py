"""The SDK's client: one HTTP session to a radiarch server, or the app in process.

Every service answers a long request the same way: ``200`` with the result when it is cached or quick, else
``202`` with a ``job_id``; ``/{service}/jobs/{job_id}`` then reports the state and, once ``succeeded``, the id of
the result, which ``GET /{service}/{id}`` returns. :meth:`Radiarch.submit` hides that: it returns the result.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

#: service prefix → (the job's result-id field, the result path)
JOBS = {
    "geometry": ("geometry_id", "/geometry/{id}"),
    "beam-model": ("beam_model_id", "/beam-model/{id}"),
    "dose": ("dose_id", "/dose/{id}"),
    "optimize": ("optimization_id", "/optimize/{id}"),
    "evaluate": ("evaluation_id", "/evaluate/{id}"),
    "bao": ("bao_id", "/bao/{id}"),
    "protocols": ("run_id", "/protocols/runs/{id}"),
    "mco": ("mco_id", "/mco/{id}"),
    "mco/deliverables": ("deliverable_id", "/mco/deliverables/{id}"),
}


class RadiarchError(RuntimeError):
    """A refused or failed request: the HTTP status and the service's own detail."""

    def __init__(self, status_code: int, detail: Any, method: str = "", path: str = ""):
        self.status_code, self.detail = status_code, detail
        super().__init__(f"{method} {path} -> {status_code}: {detail}")


class Radiarch:
    """A radiarch server, through its REST API.

    >>> rx = Radiarch("http://localhost:8000/api/v1", api_key="...")      # a server
    >>> rx = Radiarch.local()                                                # the app in this process
    >>> geo = rx.build_geometry("1.2.3", data_root="/data/case1", spacing_mm=3)
    """

    def __init__(self, base_url: str = "http://localhost:8000/api/v1", api_key: Optional[str] = None, *, timeout: float = 600.0,
                 poll_interval: float = 1.0, job_timeout: float = 6 * 3600.0, http: Optional[httpx.Client] = None,
                 api_key_header: str = "X-API-Key", on_progress: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        headers = {api_key_header: api_key} if api_key else {}
        self.http = http or httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)
        if http is not None and api_key:
            self.http.headers[api_key_header] = api_key
        self.prefix = "" if http is None else base_url.rstrip("/")
        self.poll_interval, self.job_timeout = float(poll_interval), float(job_timeout)
        # called with (service, job status) whenever a job's state, stage or progress changes while waiting on it
        self.on_progress = on_progress

    @classmethod
    def local(cls, **kwargs) -> "Radiarch":
        """The radiarch app in this process (no server): for notebooks, scripts on the planning machine, tests."""
        from fastapi.testclient import TestClient
        from ..app import create_app

        return cls("/api/v1", http=TestClient(create_app()), **kwargs)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "Radiarch":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ----- requests ----------------------------------------------------------

    def request(self, method: str, path: str, *, json: Any = None, params: Optional[Dict[str, Any]] = None,
                expect: tuple = (200, 201, 202, 204)) -> httpx.Response:
        if isinstance(json, BaseModel):
            json = json.model_dump(mode="json", exclude_none=True)
        resp = self.http.request(method, self.prefix + path, json=json, params=params)
        if resp.status_code not in expect:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise RadiarchError(resp.status_code, detail, method, path)
        return resp

    def get(self, path: str, model: Optional[Type[T]] = None, **params) -> Any:
        data = self.request("GET", path, params=params or None).json()
        return model.model_validate(data) if model else data

    def post(self, path: str, body: Any = None, model: Optional[Type[T]] = None) -> Any:
        data = self.request("POST", path, json=body).json()
        return model.model_validate(data) if model else data

    def submit(self, service: str, path: str, body: Any, model: Type[T]) -> T:
        """POST a request that may run as a job; wait for the job; return the result."""
        resp = self.request("POST", path, json=body)
        data = resp.json()
        if resp.status_code != 202:
            # the service answers 200 with a result it already holds (same inputs): no job to wait on
            if self.on_progress is not None:
                self.on_progress(service, {"state": "done", "message": "computed before: the stored result"})
            return model.model_validate(data) if model else data
        id_field, result_path = JOBS[service]
        job_id = data["job_id"]
        deadline = time.monotonic() + self.job_timeout
        seen = None
        while True:
            job = self.get(f"/{service}/jobs/{job_id}")
            state = str(job.get("state", ""))
            now = (state, job.get("stage"), job.get("progress"), job.get("message"))
            if self.on_progress is not None and now != seen:
                seen = now
                self.on_progress(service, job)
            if state == "succeeded":
                return self.get(result_path.format(id=job[id_field]), model)
            if state in ("failed", "cancelled"):
                raise RadiarchError(500, job.get("message") or job.get("error") or state, "JOB", f"/{service}/jobs/{job_id}")
            if time.monotonic() > deadline:
                raise RadiarchError(504, f"job still {state} after {self.job_timeout:.0f} s", "JOB", f"/{service}/jobs/{job_id}")
            time.sleep(self.poll_interval)

    # ----- what the server offers ------------------------------------------------

    def info(self) -> Dict[str, Any]:
        return self.get("/info")

    def machines(self) -> Dict[str, Any]:
        return self.get("/beam-model/machines")

    def engines(self) -> Any:
        return self.get("/dose/engines")

    def goal_templates(self) -> Any:
        return self.get("/evaluate/goal-templates")

    def capability(self) -> Dict[str, Any]:
        return self.get("/lineage/capability")

    # ----- entry points: the domain objects (``objects.py``) -------------------------

    def build_geometry(self, study_uid: str, *, data_root: Optional[str] = None, spacing_mm: Optional[float] = None,
                       hu_model: Optional[str] = None, structure_name_map: Optional[Dict[str, list]] = None, **patient_ref):
        """A patient's planning CT and structures as a geometry (built, or the cached one)."""
        from ..models.geometry import GeometryBuildRequest, GeometryResult, GridSpec, PatientRef
        from .objects import Geometry

        req = GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=study_uid, **patient_ref),
                                   grid_spec=GridSpec(spacing_mm=(spacing_mm,) * 3) if spacing_mm else None,
                                   data_root_override=data_root, structure_name_map=structure_name_map,
                                   **({"hu_to_density_model": hu_model} if hu_model else {}))
        return Geometry(self, self.submit("geometry", "/geometry/build", req, GeometryResult))

    def geometry(self, geometry_id: str):
        from ..models.geometry import GeometryResult
        from .objects import Geometry
        return Geometry(self, self.get(f"/geometry/{geometry_id}", GeometryResult))

    def beam_model(self, beam_model_id: str):
        from ..models.beam_model import BeamModelResult
        from .objects import BeamModel
        return BeamModel(self, self.get(f"/beam-model/{beam_model_id}", BeamModelResult))

    def optimization(self, optimization_id: str):
        from ..models.optimization import OptimizationResult
        from .objects import Optimization
        return Optimization(self, self.get(f"/optimize/{optimization_id}", OptimizationResult))

    def dose(self, dose_id: str):
        from ..models.dose import DoseResult
        from .objects import Dose
        return Dose(self, self.get(f"/dose/{dose_id}", DoseResult))

    def evaluation(self, evaluation_id: str):
        from ..models.evaluation import EvaluationResult
        from .objects import Evaluation
        return Evaluation(self, self.get(f"/evaluate/{evaluation_id}", EvaluationResult))

    def arcs(self, vmat_id: str):
        from ..models.vmat import ArcResult
        from .objects import Arcs
        return Arcs(self, self.get(f"/optimize/arcs/{vmat_id}", ArcResult))

    def sequence(self, sequence_id: str):
        from ..models.apertures import SequenceResult
        from .objects import Sequence
        return Sequence(self, self.get(f"/optimize/sequences/{sequence_id}", SequenceResult))

    def export(self, export_id: str):
        from ..models.rt_export import RTExportResult
        from .objects import Export
        return Export(self, self.get(f"/rt/exports/{export_id}", RTExportResult))

    def find_exports(self, *, study_instance_uid: Optional[str] = None, series_instance_uid: Optional[str] = None,
                     sop_instance_uid: Optional[str] = None, limit: int = 50) -> List[Any]:
        """Exports by DICOM UID, newest first (what a viewer showing that study, series or instance came from)."""
        from ..models.rt_export import RTExportResult
        from .objects import Export
        params = {k: v for k, v in {"study_instance_uid": study_instance_uid, "series_instance_uid": series_instance_uid,
                                    "sop_instance_uid": sop_instance_uid, "limit": limit}.items() if v is not None}
        return [Export(self, RTExportResult.model_validate(r)) for r in self.get("/rt/exports", **params)]

    def protocols(self) -> Any:
        """The shipped planning protocols."""
        return self.get("/protocols")

    def protocol(self, protocol_id: str):
        from ..models.protocol import PlanningProtocol
        return self.get(f"/protocols/{protocol_id}", PlanningProtocol)

    def run_protocol(self, protocol, geometry):
        """Plan ``geometry`` (a ``Geometry`` or its id) with ``protocol`` (a shipped id, a ``PlanningProtocol`` or a dict)."""
        from ..models.protocol import PlanningProtocol, ProtocolRunRequest, ProtocolRunResult
        from .objects import Geometry, ProtocolRun

        gid = geometry.id if isinstance(geometry, Geometry) else geometry
        if isinstance(protocol, str):
            req = ProtocolRunRequest(geometry_id=gid, protocol_id=protocol)
        else:
            req = ProtocolRunRequest(geometry_id=gid, protocol=protocol if isinstance(protocol, PlanningProtocol) else PlanningProtocol(**protocol))
        return ProtocolRun(self, self.submit("protocols", "/protocols/run", req, ProtocolRunResult))

    def protocol_run(self, run_id: str):
        from ..models.protocol import ProtocolRunResult
        from .objects import ProtocolRun
        return ProtocolRun(self, self.get(f"/protocols/runs/{run_id}", ProtocolRunResult))

    def registration(self, registration_id: str):
        from ..models.registration import RegistrationResult
        from .objects import Registration
        return Registration(self, self.get(f"/registrations/{registration_id}", RegistrationResult))


__all__ = ["Radiarch", "RadiarchError", "JOBS"]
