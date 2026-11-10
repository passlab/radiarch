# ADR 0021 — Stored results scoped by the studies a user may see

Date: 2026-11-10. Status: proposed; the project lead decides the open points. Follows ADR 0020 ("Not covered:
per-user image reads, and per-user scoping of stored results").

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

## Proposed decisions (open until the project lead decides)

1. **The host answers, radiarch asks.** A setting `RADIARCH_ACCESS_URL` names a host endpoint. Radiarch calls
   `GET {url}?user=<user>&study=<uid>` with the proxy's secret, and a `200` means yes. Answers are cached for a short
   time (`RADIARCH_ACCESS_CACHE_S`, default 60 s), so a viewer's burst of reads costs one call per study.
   - Open point A: an alternative is a header the proxy adds, listing the user's studies. It needs no endpoint, but
     a user with hundreds of studies overflows a header, and the list goes stale while a viewer stays open.
2. **What is checked.**
   - Every read by id of a patient result: geometry, beam model, dose, influence, optimization, sequence, arcs,
     Pareto set, state, deliverable plan, evaluation, protocol run, export, its files, registration, 4D accumulation.
   - The listing routes, which drop what the user may not see.
   - The lineage graph, which stops at a version the user may not see.
   - A refused read answers `404`, as an unknown id does, so a caller learns nothing about what exists.
   - Machines, protocols, goal templates and engine information belong to no patient and stay open.
3. **Writes.** A request that builds on a stored result needs the same access as reading it. A geometry built from
   a study needs access to that study.
4. **Without a user, nothing changes.** A request without the user header, or a deployment without
   `RADIARCH_ACCESS_URL`, behaves as today. A deployment behind a host sets both: the trusted proxy (R11.10) and the
   access URL.
   - Open point B: with `RADIARCH_ACCESS_URL` set, should a request without a user be refused, or be read as the
     host itself (a service account)? Refusal is safer. A service account is what a host's batch jobs need.
5. **`requested_by` stays a record.** It does not grant access. A result read by another user who may see its
   study still shows who made it.
   - Open point C: should it be shown to other users, or only to its maker?
6. **Jobs.** Job status by id stays open: it holds a state and the result's id, and the result's read is checked.

## Consequences

- Each checked read resolves the result's studies. The lineage store already walks to the geometries, and a small
  cache keeps it cheap (results do not change, so their studies do not either).
- The host has to serve one endpoint. With a viewer, every image it shows was already checked by the host's own
  image routes. This only adds radiarch's results to what the host controls.
- Not covered: the images themselves. Radiarch reads CTs from the configured PACS with its own credential, and the
  host decides which studies a user can ask radiarch to plan on.
- Size: about 3 days with tests (the check, the routes, the listings, the lineage walk, the settings, a fake access
  endpoint in the tests).

## Tests (to build)

- A fake access endpoint that allows one user one study:
  - that user reads the results of that study;
  - another user gets `404` on reads by id, empty listings, and a lineage graph without them;
  - a write that builds on a refused result is refused;
  - the cache and the job join still serve the allowed user from another user's result.
- Without the setting, every existing test passes unchanged.
