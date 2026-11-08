# ADR 0020 — An upload token per export, and the viewer's hook for it

Date: 2026-11-08. Status: accepted and built (2026-11-08; decision 6 first, in 8d0bffc). Roadmap R13 ("Viewer
integration"), R13.4; builds on R6's push and on R11.10 (planning behind a gateway).

## Context

An export with `push`, and `POST /api/v1/rt/exports/{id}/push`, send the RT objects to a DICOMweb server with
STOW-RS. Radiarch signs in with its own credential: HTTP basic, or an OAuth2 client-credentials token fetched from
`RADIARCH_DICOMWEB_TOKEN_URL` (`docs/PRODUCTION.md`). A push request may also give a username and password.

Behind a host platform, the archive often sits behind a write gateway. That gateway sees every upload as radiarch's.
It cannot tell which user exported, and it cannot limit an upload to the study that user has open. The user name
radiarch keeps (`requested_by`, R11.10) is radiarch's own record; the archive cannot rely on it.

A host that wants the archive to decide per user and per study can issue a short-lived token for one upload: this
user, this study, these objects, a few minutes. Radiarch has to carry that token to the archive. The viewer has to
get it from the host when the user exports.

The viewer's client already sends the host's authorization header with every API call (OHIF's
`userAuthenticationService`). That header proves the user to the host's proxy in front of radiarch. It is not meant
for the archive, and radiarch does not forward it.

## Decisions

1. **The token travels in a request header**, `X-Upload-Authorization` by default
   (`RADIARCH_UPLOAD_TOKEN_HEADER`), on `POST /rt/export` with `push` and on `POST /rt/exports/{id}/push`. It is not
   a body field: an export keeps its request, and a validation error echoes the body. Built: treatment records
   pushed with `POST /rt/exports/{id}/records` take it too, so that decision 5 does not shut them out. A value an
   HTTP header cannot carry (a line break, NUL) is refused (422) without being quoted.
2. **Radiarch passes the value through unread.** It becomes the `Authorization` header of that one STOW-RS request,
   as given (for example `Bearer eyJ…`). Radiarch does not parse, check or refresh it.
3. **The token is never kept.** It is not written to the export record, the job table, a log line or an error
   message. The push's log line names its kind of authentication ("upload token"), not its value. An archive's
   refusal that quotes the token is kept with `[upload token]` in its place. Export and push run inside the request,
   as they do now, so the token never enters the job queue. If a push ever moves into a job, this needs a new design.
4. **A token comes first.** With a token, radiarch uses neither its own credential nor a request's username and
   password. A request that gives a token and a username is refused (422).
5. **A server can require a token** (`RADIARCH_UPLOAD_TOKEN_REQUIRED`, off by default). When it is on, a push
   without a token is refused (422) before anything is written. An export without `push` is not affected. Built:
   a plan job (the `/plans` route), which can hold no token, then pushes nothing and logs why.
6. **Radiarch's own credential goes only to its configured URL** (`RADIARCH_DICOMWEB_URL`). A push to a request's
   `url` uses the request's token, or its username and password, or nothing. Built on 2026-11-08, ahead of the rest
   (`DICOMwebNotifier`; `tests/test_dicomweb_push_auth.py`).
7. **A refusal is the archive's.** A refused token comes back as any refused push does: `push_error`,
   `http_status` and `response`, and 502 when `RADIARCH_DICOMWEB_PUSH_REQUIRED` is set. A stored export pushed again
   (the same UIDs) needs a new token.
8. **The viewer's hook.** The planning extension's configuration takes an optional function:

   ```ts
   getUploadToken?: (ctx: { studyInstanceUID: string; objects: string[] }) => Promise<string | null>;
   ```

   The MCO panel calls it when the user exports with push, and the client sends what it returns in the header.
   `objects` lists the object kinds the export writes (`rtplan`, `rtdose`, …): the hook is asked before the export,
   so their UIDs do not exist yet. The header's name is the extension's `uploadTokenHeader` (default
   `X-Upload-Authorization`), which must match the server's.
   - No hook: the export works as today.
   - `null`: the objects are written but not sent, and the panel says "not sent: the host gave no upload token".
   - An error: the panel shows it and exports nothing.

   `radiarch-client`'s export and push calls take an optional `uploadToken`; `exportAndPush` holds the panel's
   rule above.
9. **Nothing in radiarch knows who issues the token or what it holds.** The host issues it and the archive's gateway
   checks it. Radiarch and its viewer only carry it.

## Consequences

- An archive behind a write gateway can authorize each upload by user and study. A deployment can then drop
  radiarch's own write credential, or keep it for pushes outside the viewer.
- Radiarch does not check the token. A wrong or expired token is a refused push, reported as one.
- The token passes through the proxy and radiarch's memory. Every hop must use TLS, as for any credential.
- The API gains two optional settings and one optional header. No object radiarch writes changes, so the release
  stays as it is (`PRODUCTION.md`: the release follows output). The viewer gains one optional configuration function.
  Nothing changes for a deployment that sets neither.
- Not covered: per-user image reads, and per-user scoping of stored results. Results are shared between users
  today, so these need their own note.

## Tests

radiarch (`tests/test_upload_token.py`, with the fake STOW-RS server of `tests/test_dicomweb_push_auth.py`):
- the archive receives the token as `Authorization`, and the export record, the stored request and the captured log
  hold no trace of it;
- with `RADIARCH_UPLOAD_TOKEN_REQUIRED`, a push without a token is refused and nothing is written; an export without
  `push` still works;
- a push to a request's `url` without a token carries no credential of the server's;
- a token and a username together are refused;
- a refusal that quotes the token is kept without it; a plan job pushes nothing where a token is required.

radiarch-ohif (`libs/radiarch-client/test/upload.test.js`):
- the client sends the header only when it is given a token;
- the panel calls the hook with the study and the objects; `null` gives "not sent" with the reason; an error exports
  nothing;
- the browser test, which sets no hook, passes unchanged.

## Documents

`docs/PRODUCTION.md` (the push section: the header, the two settings, the rule of decision 6), `docs/viewing.md`
(the hook), ADR 0018 (a pointer to this one), `docs/impl-plan.md` and `docs/impl-log.md`.

## Decided by the project lead (2026-11-08)

1. **The value passes through unchanged** (decision 2), rather than radiarch taking only a bearer token and adding
   `Bearer ` itself. That fits more gateways.
2. **Requiring a token is off by default** (decision 5), so nothing changes for a deployment that does not use
   tokens.
3. **The header is `X-Upload-Authorization`**, configurable (decision 1).
