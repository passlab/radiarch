"""Stored results scoped by the studies a user may see (ADR 0021).

A host that serves several users through one radiarch instance names the user (the trusted proxy, R11.10) and answers,
for one user and one study, whether the user may see it: ``GET {access_url}?user=<user>&study=<uid>`` with the proxy's
secret, ``200`` meaning yes. Every patient result traces, through the lineage graph, to the geometries it was computed
on, and each geometry to the study its CT came from; an imported plan also to the study it was written in, and a gamma
comparison to its reference dose. A user reads a result only when the host lets them see every one of its studies. A
result that traces to no study, to a file, or to a version that is gone is read by nobody.

Results are content-addressed and never change, so a result's studies are kept once found; the host's answers are kept
for ``access_cache_s``. The cache and the job join stay shared: a user who may see a study may see what its inputs
determine. The check reads the ids a request names (in its path and its JSON body). An id that is not a plain token, a
refused id and an unknown one answer alike. A request that names a file on the server is refused.
"""

from __future__ import annotations

import re
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from loguru import logger

from ..config import get_settings

# A path parameter → the kind of result it names. Every other path parameter is listed in PATH_UNCHECKED with the reason.
PATH_KINDS = {
    "geometry_id": "geometry", "beam_model_id": "beam_model", "influence_id": "influence", "dose_id": "dose",
    "opt_id": "optimization", "sequence_id": "sequence", "vmat_id": "vmat", "mco_id": "mco", "deliverable_id": "deliverable",
    "evaluation_id": "evaluation", "run_id": "run", "export_id": "rt_export", "registration_id": "registration",
    "assessment_id": "assessment", "bao_id": "bao", "upload_id": "upload", "plan_id": "plan", "artifact_id": "artifact",
}
PATH_UNCHECKED = {
    "kind": "names the kind of version_id, which is checked as that kind",
    "version_id": "checked as the kind its path names",
    "file_name": "a file the export's manifest names",
    "state_id": "a state of the Pareto set the path names (a plain token)",
    "job_id": "job status stays open: a state and the result's id, whose read is checked",
    "machine_id": "machines belong to no patient", "name": "an engine's name",
    "protocol_id": "a shipped protocol", "template_id": "a goal template", "workflow_id": "a workflow template",
    "session_id": "a temporary upload read by nothing else",
}

# A JSON body's key → the kind of result it names (a list of ids is checked id by id, at any depth).
BODY_KINDS = {
    "geometry_id": "geometry", "geometry_ids": "geometry", "phase_geometry_ids": "geometry", "fixed_geometry_id": "geometry",
    "moving_geometry_id": "geometry", "reference_geometry_id": "geometry", "planning_geometry_id": "geometry",
    "day_geometry_id": "geometry", "beam_model_id": "beam_model", "dose_id": "dose", "planned_dose_id": "dose",
    "reference_dose_id": "dose", "optimization_id": "optimization", "sequence_id": "sequence",
    "registration_id": "registration", "evaluation_id_a": "evaluation", "evaluation_id_b": "evaluation", "upload_id": "upload",
}
BODY_STUDIES = ("dicom_study_uid", "study_instance_uid")         # a study a request reads from the PACS
# files on the server name no study: these keys, and every key ending in _uri or _path, are refused
BODY_PATHS = ("nrrd_ct_path", "nrrd_seg_path", "data_root_override", "path", "registration_path", "mcsquare_dir")
# names of shipped things that are joined onto a folder (an engine's assets, the machine library, protocols, templates):
# plain names only, so none of them reaches another file
BODY_NAMES = ("bdl", "scanner", "machine_model_id", "machine", "model_id", "template_id", "protocol_id", "workflow_id")
BODY_TOKENS = ("state_id", "from_state")                         # joined onto a Pareto set's folder: plain tokens only
BODY_UNCHECKED = {
    "id": "a version reference's id ({kind, id}), checked as that kind",
    "plan_id": "a label naming the owning plan; nothing is read by it",
    "state_id": "a state of the Pareto set the path names (a plain token)",
    "from_state": "a state of the Pareto set the path names (a plain token)",
    "ct_series_uid": "a series of the study the request names", "rtstruct_uid": "a series of the study the request names, or one an export writes",
    "segmentation_uid": "a series of the study the request names",
    "rtplan_uid": "a UID an export writes", "predecessor_plan_uid": "a UID an export writes", "summed_plan_uids": "UIDs an export writes",
    "machine_model_id": "machines belong to no patient", "model_id": "an NTCP or TCP parameter set", "beam_id": "a beam's name",
    "arc_id": "an arc's name", "template_id": "a goal template", "protocol_id": "a shipped protocol", "workflow_id": "a workflow template",
    "file_name": "a file of the upload the request names", "file": "an uploaded file (multipart), not a stored result",
    "url": "where a push sends an export the user may see",
}
# A query parameter names no result a route reads: listings filter by these, and every item they list is checked.
QUERY_UNCHECKED = {
    "dose_id": "a listing's filter", "beam_model_id": "a listing's filter", "study_instance_uid": "a listing's filter",
    "series_instance_uid": "a listing's filter", "sop_instance_uid": "a listing's filter", "limit": "a count",
    "max_depth": "a count", "dataset_id": "a dataset manifest's name", "version": "a dataset manifest's version",
    "identifiability": "a label", "description": "a label",
}
LINEAGE_KINDS = ("geometry", "beam_model", "influence", "dose", "optimization", "sequence", "bao", "evaluation", "rt_export",
                 "plan", "registration", "mco")

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")        # every stored id: UUIDs, hex keys, state names
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")      # a shipped file's or folder's name, without "/"
UID = re.compile(r"[0-9]+(\.[0-9]+)*")                          # a DICOM UID: digits and dots, at most 64
_UNKNOWN = ""                       # a study that cannot be found (a version gone, a file, a cycle): allowed to nobody
_MAX_KEPT = 50_000
_MAX_DEPTH = 64                     # a body nested deeper names nothing a request model holds


class NotVisible(Exception):
    """The request names a result or a study the user may not see, or one that does not exist (answered alike)."""


class ServerPathRefused(Exception):
    """A request names a file on the server: it names no study, so nobody's access can be checked."""


class AccessUnavailable(Exception):
    """The host's access endpoint could not answer."""


def enabled() -> bool:
    return bool(getattr(get_settings(), "access_url", ""))


def is_server_path(key: str) -> bool:
    return key in BODY_PATHS or key.endswith(("_uri", "_path"))


class AccessService:
    """Which studies a stored result traces to, and whether the host lets a user see them."""

    _studies: Dict[Tuple[str, str], FrozenSet[str]] = {}
    _answers: Dict[Tuple[str, str], Tuple[bool, float]] = {}
    _down_until = 0.0
    _lock = threading.Lock()

    # ----- the studies of a result ------------------------------------

    def studies(self, kind: str, version_id: str) -> Optional[FrozenSet[str]]:
        """The studies ``kind``/``version_id`` traces to; None when no such result is stored. A version it derives from
        that is gone, a file it was read from, or a cycle adds an unknown study, which nobody may see."""
        try:
            return self._studies_of(kind, str(version_id), frozenset())
        except RecursionError:
            logger.warning("access: the lineage of {} {} is too deep to walk; read by nobody", kind, version_id)
            return frozenset({_UNKNOWN})

    def _studies_of(self, kind: str, version_id: str, walking: FrozenSet[Tuple[str, str]]) -> Optional[FrozenSet[str]]:
        key = (kind, version_id)
        with self._lock:
            kept = self._studies.get(key)
        if kept is not None:
            return kept
        if key in walking:
            return frozenset({_UNKNOWN})
        if not TOKEN.fullmatch(version_id):
            return None
        try:
            looked = self._lookup(kind, version_id)
        except Exception as exc:  # a store that cannot read the id has no such result
            logger.debug("access: {} {} unreadable: {}", kind, version_id, exc)
            return None
        if looked is None:
            return None
        own, parents = looked
        out: Set[str] = {s for s in own if s is not None}
        for pk, pid in parents:
            if pid:
                got = self._studies_of(pk, str(pid), walking | {key})
                out |= got if got is not None else {_UNKNOWN}
        found = frozenset(out)
        with self._lock:
            if len(self._studies) >= _MAX_KEPT:
                self._studies.clear()
            self._studies[key] = found
        return found

    @staticmethod
    def _lookup(kind: str, version_id: str) -> Optional[Tuple[Iterable[Optional[str]], List[Tuple[str, Optional[str]]]]]:
        """The stored result's own studies and the versions it derives from; None if it is not stored. An own study of
        ``_UNKNOWN`` marks a source that names no study."""
        if kind in LINEAGE_KINDS:
            from ..models.lineage import VersionRef
            from .lineage import LineageService

            found = LineageService().parents(VersionRef(kind=kind, id=version_id))
            if found is None:
                return None
            obj, parents = found
            refs = [(p.kind, p.id) for p in parents]
            own: List[Optional[str]] = []
            if kind == "geometry":
                own.append(getattr(getattr(obj, "ct_metadata", None), "study_instance_uid", None) or None)
            elif kind in ("plan", "rt_export"):
                own.append(getattr(obj, "study_instance_uid", None) or None)
            elif kind == "beam_model" and getattr(obj, "imported_plan", None) is not None:
                own.append(obj.imported_plan.study_instance_uid or _UNKNOWN)         # the study the RT Plan was written in
            elif kind == "evaluation":
                if not getattr(obj, "dose_id", None):
                    own.append(_UNKNOWN)                                            # its dose was read from a file
                gamma = getattr(obj, "gamma", None)
                if gamma is not None:
                    ref = getattr(gamma, "reference_dose_id", None)
                    if ref:
                        refs.append(("dose", ref))
                    else:
                        own.append(_UNKNOWN)                                        # a reference from a file, or not recorded
            if kind in ("beam_model", "dose") and str(getattr(obj, "cache_key", "") or "").startswith("vmat:"):
                refs.append(("vmat", str(obj.cache_key).split(":")[1]))             # an arc plan and its dose: the arcs' sources
            return own, refs
        if kind == "vmat":
            from .optimization import OptimizationService
            from .vmat import VMATService

            r = VMATService(optimization_service=OptimizationService()).store.get_by_id(version_id)
            # its sources only: the arc plan and dose it made trace back to it
            return None if r is None else ([], [("optimization", r.optimization_id), ("geometry", r.geometry_id),
                                                ("beam_model", r.source_beam_model_id)])
        if kind == "deliverable":
            from .mco import MCOService
            from .mco_deliverable import DeliverableService

            r = DeliverableService(mco_service=MCOService()).store.get_by_id(version_id)
            return None if r is None else ([], [("mco", r.mco_id), ("geometry", r.geometry_id), ("optimization", r.optimization_id),
                                                ("beam_model", r.beam_model_id), ("dose", r.dose_id), ("sequence", r.sequence_id),
                                                ("vmat", r.vmat_id)])
        if kind == "run":
            from .autoplan import AutoplanService

            r = AutoplanService().store.get_by_id(version_id)
            return None if r is None else ([], [("geometry", r.geometry_id), ("geometry", r.planning_geometry_id)])
        if kind == "assessment":
            from .replan import ReplanService

            r = ReplanService().store.get_by_id(version_id)
            return None if r is None else ([], [("registration", r.registration_id), ("geometry", r.day_geometry_id),
                                                ("beam_model", r.day_beam_model_id), ("dose", r.day_dose_id),
                                                ("dose", r.mapped_planned_dose_id)])
        if kind == "upload":
            return _upload_studies(version_id)
        if kind == "artifact":
            from ..core.store import store

            r = store.get_artifact(version_id)
            return None if r is None else ([], [("plan", r.plan_id)])
        return None

    # ----- the host's answer ------------------------------------------

    def _host_up(self) -> None:
        """A host that just failed is taken as down for ``access_cache_s``: every check answers 503 meanwhile, so an
        unknown id and a known one answer alike during an outage."""
        if time.monotonic() < self._down_until:
            raise AccessUnavailable("the host's access endpoint failed recently")

    def _host_failed(self) -> None:
        type(self)._down_until = time.monotonic() + float(get_settings().access_cache_s)

    def allowed(self, user: str, study: str) -> bool:
        if not study or len(study) > 64 or not UID.fullmatch(study):       # not a UID: no host is asked about it
            return False
        settings = get_settings()
        key, now = (user, study), time.monotonic()
        with self._lock:
            kept = self._answers.get(key)
        if kept is not None and kept[1] > now:
            return kept[0]
        self._host_up()
        secret = settings.trusted_proxy_secret.get_secret_value() if settings.trusted_proxy_secret else ""
        try:
            r = _http().get(settings.access_url, params={"user": user, "study": study},
                            headers={settings.trusted_proxy_secret_header: secret}, timeout=10.0)
        except Exception as exc:
            self._host_failed()
            raise AccessUnavailable(f"the host's access endpoint did not answer ({type(exc).__name__})") from exc
        if r.status_code == 200:
            answer = True
        elif r.status_code in (403, 404):
            answer = False
        elif r.status_code in (401, 407, 408, 429) or r.status_code >= 500:     # the host, or the way to it, is failing
            self._host_failed()
            raise AccessUnavailable(f"the host's access endpoint answered {r.status_code}")
        else:                                                                    # another 4xx: this request is refused
            logger.info("access: the host answered {} for user {!r} and study {!r}; refused", r.status_code, user, study)
            return False
        with self._lock:
            if len(self._answers) >= _MAX_KEPT:
                self._answers.clear()
            self._answers[key] = (answer, now + float(settings.access_cache_s))
        return answer

    def visible(self, user: Optional[str], kind: str, version_id: str) -> bool:
        """Whether ``user`` may read the stored result (False also when it is not stored)."""
        if not user:
            return False
        self._host_up()
        found = self.studies(kind, version_id)
        return bool(found) and all(self.allowed(user, s) for s in found)

    # ----- a request ---------------------------------------------------

    def check(self, user: str, path_params: Dict[str, str], body: Any) -> None:
        """Every result and study ``path_params`` and ``body`` name is one ``user`` may see, else :class:`NotVisible`."""
        self._host_up()
        for name, value in path_params.items():
            kind = path_params.get("kind") if name == "version_id" else PATH_KINDS.get(name)
            if kind is not None and value and not self.visible(user, kind, value):
                raise NotVisible(f"{kind} {value}")
            if name == "state_id" and not TOKEN.fullmatch(value or ""):
                raise NotVisible(f"state {value}")
        for kind, value in body_refs(body):
            if kind == "study":
                if not self.allowed(user, value):
                    raise NotVisible(f"study {value}")
            elif kind == "token":
                if not TOKEN.fullmatch(value):
                    raise NotVisible(f"state {value}")
            elif not self.visible(user, kind, value):
                raise NotVisible(f"{kind} {value}")

    @classmethod
    def forget(cls) -> None:
        """Drop the kept studies and answers, and the host's outage (tests; a host whose permissions changed at once)."""
        with cls._lock:
            cls._studies.clear()
            cls._answers.clear()
            cls._down_until = 0.0


@lru_cache(maxsize=1)
def _client():
    import httpx

    return httpx.Client()


def _http():
    return _client()


def body_refs(body: Any) -> List[Tuple[str, str]]:
    """The (kind, id) pairs a JSON body names, at any depth: ``study`` for a study UID, ``token`` for a state name. A
    server path raises :class:`ServerPathRefused`; a body nested deeper than any request model raises
    :class:`NotVisible`."""
    out: List[Tuple[str, str]] = []
    stack: List[Tuple[Any, int]] = [(body, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise NotVisible("a body nested too deep")
        if isinstance(node, dict):
            ref_kind, ref_id = node.get("kind"), node.get("id")
            if isinstance(ref_kind, str) and ref_kind in LINEAGE_KINDS and isinstance(ref_id, str) and ref_id:
                out.append((ref_kind, ref_id))                     # a version reference: {"kind", "id"}
            for key, value in node.items():
                if isinstance(key, str) and is_server_path(key) and value:
                    raise ServerPathRefused(key)
                if key in BODY_NAMES and isinstance(value, str) and value and (not NAME.fullmatch(value) or ".." in value):
                    raise ServerPathRefused(key)
                if key in BODY_KINDS or key in BODY_STUDIES or key in BODY_TOKENS:
                    kind = BODY_KINDS.get(key) or ("study" if key in BODY_STUDIES else "token")
                    for v in value if isinstance(value, list) else [value]:
                        if v is None:
                            continue
                        if not isinstance(v, str) or not v:
                            raise NotVisible(f"{key} {v!r}")
                        out.append((kind, v))
                elif isinstance(value, (dict, list)):
                    stack.append((value, depth + 1))
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node)
    return out


def _upload_studies(upload_id: str) -> Optional[Tuple[List[str], list]]:
    """The studies of an uploaded DICOM bundle, from its files' Study Instance UIDs."""
    settings = get_settings()
    root = Path(settings.upload_dir or str(Path(settings.artifact_dir) / "uploads")).expanduser().resolve() / upload_id
    if not root.is_dir():
        return None
    import pydicom

    studies: Set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, specific_tags=["StudyInstanceUID"])
        except Exception:
            continue
        uid = str(getattr(ds, "StudyInstanceUID", "") or "")
        if uid:
            studies.add(uid)
    return sorted(studies) or [_UNKNOWN], []
