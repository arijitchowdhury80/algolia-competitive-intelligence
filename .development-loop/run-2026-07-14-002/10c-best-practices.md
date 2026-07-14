# Best Practices Synthesis

## Patterns that worked

- Treat a static release as one immutable generation plus one pointer, not a
  collection of individually atomic files.
- Keep blocked diagnostics and the last successful decision on separate
  pointers.
- Derive safety from final bytes and overwrite caller claims before hashing.
- Make package, publication, click, and launch evidence structured, fresh,
  run-bound, and digest-bound.
- Serialize all writers even when each underlying filesystem operation is
  atomic.
- Use stable non-secret hashes when public accounting needs entity identity
  without exposing source URLs.

## Anti-patterns removed

- PASS-substring authority.
- Caller-attested safety.
- Duplicate mutable root and `/v2` trees.
- Silent acceptance of pre-existing router state.
- Per-file promotion without a process-wide commit boundary.

## Test gaps discovered

- Concurrency lock acquisition.
- Wrong stable-router targets.
- Symlinked internal generation buckets.
- macOS/container/Windows local path forms.
- Nested credential containers.
- Exact served-manifest digest mismatch.
- Multiple disposed sources for one competitor.
- Private package/model provenance.

No cross-project SOP update is needed before this phase gate. The project spec,
E2E command, package verifier, and tests now carry the reusable rules.
