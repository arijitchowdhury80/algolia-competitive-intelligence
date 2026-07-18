# Architecture Review

## Findings

1. `.argus-publish.<pid>` is a copy buffer, not an atomic release boundary;
   promotion still mutates the live tree one path at a time.
2. Two independently copied route trees cannot provide one-generation
   consistency under interruption.
3. Writing public status before demand helpers and briefs violates the stated
   status-last contract.
4. A run ID buried in dashboard state cannot bind wrapper execution, sidecars,
   validation, and publication.
5. Self-attested booleans and PASS substrings prove only that input text was
   shaped favorably, not that artifacts were safe or checks ran.
6. Serving the mutable tree with a root-owned generic HTTP server adds
   privilege without solving atomicity.

## Alternatives considered

- Per-file `os.replace`: each file is atomic but the set can still mix runs.
- Directory rename over a nonempty live directory: not portably atomic.
- Caddy route change: unnecessary because the loopback static service already
  provides a single document-root boundary.
- Stable router plus one `current` symlink: provides set-level consistency,
  preserves URLs, and allows status to be independently updated last.

## Decision

Build one CI-OS publication module around immutable generation directories,
content manifests, independent validation, a stable served router, and atomic
pointer/status replacement. Keep blocked diagnostics separate from the current
decision generation. Cut the static service to the sibling served root only
after local verification and rollback rehearsal.

The normal architecture reviewer subagent was unavailable because the agent
thread limit was already reached. This inline review uses the live Caddy,
listener, ownership, filesystem, wrapper, publisher, exporter, and test
evidence recorded in Discovery.

Verdict: acceptable to build under the approved Phase 2 boundary.
