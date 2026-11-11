# ADR 0021 — Stored results scoped by the studies a user may see

Date: 2026-11-10. Status: decided by the project lead and built, 2026-11-11 (open points A, B and C below, each as
recommended). Follows ADR 0020 ("Not covered: per-user image reads, and per-user scoping of stored results").

## Context

One radiarch instance can serve several users through a host platform. The host's proxy proves itself with a shared
secret and names the user in a header (`requester`, R11.10). Radiarch records that user on the results made for it
(`requested_by` on optimizations, Pareto sets, navigation states, deliverable plans, second sets, exports and
protocol runs), and writes it as Operators' Name. It does not use the user to decide what the caller may read.

Today every caller with the API key can read every stored result by its id, and the listing routes return every
user's results:
- `GET /rt/exports?study_instance_uid=…`, `GET /mco/deliverables?dose_id=…`, `GET /mco/{id}/states`;
- the lineage graph, which walks from any version to everything derived from it.

Ids are random UUIDs, so a caller has to learn an id first, but the listing routes and the lineage graph hand them
out. A host that limits which studies a user may open cannot rely on radiarch to keep to the same limit.

Two properties of radiarch shape the answer:
- **Results are content-addressed.** The cache key is the inputs, never the user. Two users who ask for the same
  plan on the same CT get one result, and since b3d80db a second request joins the first one's job. A result
  holds nothing its inputs do not determine.
- **Every patient result traces to a study.** A result traces back, through the lineage graph, to one or more
  geometries. Each geometry was built from a study (`patient_ref.dicom_study_uid`), or derives from one that was. A
  registration or a 4D accumulation joins several geometries, and so several studies.

## Options

1. **Scope by the creator.** Each result keeps the set of users who asked for it, and a read needs the caller in
   that set. This fights the cache: a second user's request for the same inputs either adds them to the set, which
   gives them the result anyway, or computes it again. It also hides from a colleague a plan on a patient both may
   see. Clinical systems grant access by patient, not by author.
2. **Scope by study (proposed).** A read is allowed when the user may see every study the result traces to. The
   host decides that, since it already holds the user's permissions. Radiarch enforces the decision on every read
   and every listing. The cache and the job join stay shared, because a user who may see a study may see what its
   inputs determine.
3. **One instance per group.** Deployment, no code. Each instance's store holds one group's results. It fits a few
   fixed groups, not permissions that change per study.

## Decisions

1. **The host answers, radiarch asks.** A setting `RADIARCH_ACCESS_URL` names a host endpoint. Radiarch calls
   `GET {url}?user=<user>&study=<uid>` with the proxy's secret, and a `200` means yes. Answers are cached for a short
   time (`RADIARCH_ACCESS_CACHE_S`, default 60 s), so a viewer's burst of reads costs one call per study.
   - Open point A, decided: the endpoint. The alternative was a header the proxy adds, listing the user's studies. It
     needs no endpoint, but a user with hundreds of studies overflows a header, and the list goes stale while a
     viewer stays open.
   - The host answers `403` or `404` for no. A host that cannot answer never opens a result:
     - a network error, a `5xx`, `401`, `407`, `408` or `429` is an outage, and the request answers `503`;
     - any other `4xx` refuses only that request.
   - A host that failed is taken as down for the cache time, and every checked request answers `503` meanwhile.
   - A study UID that is not one (digits and dots, at most 64 characters) is refused without asking the host. So no
     request can make the host fail for everyone.
   - The host is asked about the user exactly as the proxy's header names them. The name radiarch records is cleaned
     for DICOM, and two names must not share one user's access.
2. **What is checked.**
   - Every read by id of a patient result: geometry, beam model, dose, influence, optimization, sequence, arcs,
     Pareto set, state, deliverable plan, evaluation, protocol run, export, its files, registration, 4D accumulation.
   - The listing routes, which drop what the user may not see.
   - The lineage graph. A version's graph holds only what it derives from, whose studies are among its own. The list of
     what derives from a version drops what the user may not see.
   - A refused read answers `404`, as an unknown id does, so a caller learns nothing about what exists. An id that is
     not a plain token (letters, digits, `-` and `_`) names nothing, so a path in an id reaches no file.
   - Machines, protocols, goal templates and engine information belong to no patient and stay open. So do workflow
     templates, the capability statement and job status. Every route that writes needs a user, the temporary upload
     sessions too.
   - A result's studies include every source it joins: the geometries the lineage graph walks to, the sources of the
     arcs an arc plan and its dose were made by, the study an imported RT Plan was written in, and a gamma
     comparison's reference dose.
   - A stored result that a route returns without the request naming it is checked too. This is a geometry build's
     cache hit, whose study comes from the CT it read.
   - A result that traces to no study, to a file (a CT, a dose or a gamma reference read from one), or to a version
     that is gone is read by nobody.
3. **Writes.** A request that builds on a stored result needs the same access as reading it. A geometry built from
   a study needs access to that study.
   - An upload's studies are those its DICOM files name.
   - A request that names a file on the server names no study, so it is refused (`422`). This covers
     `nrrd_ct_path`, `data_root_override`, an import's `path`, an engine's `mcsquare_dir`, and every field ending in
     `_uri` or `_path`.
   - Names that are joined onto a folder must be plain names: an engine's `bdl` and `scanner`, machine, model,
     template, protocol and workflow ids.
   - The data root is not read either. It is read by series UID whatever study a request names, so only the PACS or
     an upload is read.
   - The body is read as JSON whatever its content type says, since the route parses it so.
4. **Without the setting, nothing changes.** A deployment without `RADIARCH_ACCESS_URL` behaves as before. A
   deployment behind a host sets both the trusted proxy (R11.10) and the access URL.
   - Open point B, decided: with `RADIARCH_ACCESS_URL` set, a request without a user is refused (`401`). A host's
     batch jobs name a service user in the header, and the host's endpoint decides what that user may see. Radiarch
     needs no setting for it.
5. **`requested_by` stays a record.** It does not grant access. A result read by another user who may see its
   study still shows who made it.
   - Open point C, decided: it is shown to every user who may see the result's study, as clinical systems show a
     plan's author to colleagues. The exported objects carry it as Operators' Name in any case. A cached result keeps
     its first requester, so a second user who asked for the same inputs sees the first user's name.
6. **Jobs.** Job status by id stays open: it holds a state and the result's id, and the result's read is checked.

## Consequences

- Each checked read resolves the result's studies. The lineage store already walks to the geometries, and a small
  cache keeps it cheap (results do not change, so their studies do not either).
- The host has to serve one endpoint. With a viewer, every image it shows was already checked by the host's own
  image routes. This only adds radiarch's results to what the host controls.
- Not covered: the images themselves. Radiarch reads CTs from the configured PACS with its own credential, and the
  host decides which studies a user can ask radiarch to plan on.
- Where it is: `services/access.py` finds a result's studies and asks the host, and `api/access.py` is the check. It
  is one dependency on every protected router, so a new route is checked by default. A route is open only if it is
  listed in `OPEN_ROUTES`.
- It reads the ids a request names in its path and its JSON body, by field name. The lists of names are in
  `services/access.py`, with each unchecked name's reason. A test fails when a route's path parameter, query
  parameter or body field looks like an id, a UID, a path, a file or a URI and is in no list.
- Known limits:
  - A caller who already holds an id can tell whether it exists, at the first failure of the host or by how long a
    host call takes. Ids are random UUIDs, so a caller without one learns nothing.
  - A version's state history can name the version that superseded it, and its `locked` flag and a refused delete
    say that an approved version derives from it. Both can name a version in a study the reader may not see, which
    the reader still cannot open.
  - Deleting a version checks only that version. A result whose studies were found before its source was deleted
    keeps them. A result whose source is gone before its studies are first found is read by nobody.
  - An import's registration was not recorded as the plan's parent. Closed 2026-11-11: a plan imported through a radiarch
    registration keeps it as a parent (`frame_registration_id`), so its studies are the registration's too.
  - A request whose JSON FastAPI cannot parse answers `422` before the check, so without a user it gets `422`, not
    `401`.
- Two independent reviews found ways round the build; each was reproduced, and all are closed and tested. The first
  review found:
  - a body sent without a JSON content type;
  - ids that were paths;
  - file fields ending in `_uri`;
  - imported plans and gamma references that joined a second study;
  - names cleaned to one user;
  - an outage that told ids apart;
  - a deep body that raised a server error;
  - an open session route that wrote outside its folder.

  The second review found:
  - arc plans that traced to their geometry only;
  - a malformed study UID that took the check down for every user;
  - a cached geometry that skipped the check;
  - engine and machine names that were paths.

## Tests

`tests/test_access_scope.py`, with a fake access endpoint:
  - that user reads the results of that study;
  - another user gets `404` on reads by id, empty listings, and a lineage graph without them;
  - a write that builds on a refused result is refused;
  - the cache still serves the allowed user another user's result;
  - a result that joins two studies is read only by a user who may see both: a 4D average, an imported plan, a gamma
    comparison;
  - a body is checked whatever its content type; an id that is a path, a file field and a too-deep body are refused;
  - a request without a user, and one naming a file on the server, are refused, and the open routes stay open;
  - the host is asked once per user and study within the cache time, with the proxy's secret, about the user's exact
    name; a host that answers 500 and one that does not answer both refuse with `503`, unknown ids too;
  - the session routes need a user, and keep a client's file name inside the session's folder;
  - an arc plan made from another study's beam model; a malformed UID and a host's `400` refuse one request only; a
    cached geometry holding another study's CT; names of shipped files that are paths;
  - every route is open or checked, and every id field it takes is known.
- Without the setting, every existing test passes unchanged.
