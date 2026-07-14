# Assumptions

| Assumption | Confidence | Impact if wrong | Treatment |
|---|---|---|---|
| One symlink pointer swap is atomic on the live Linux filesystem | High | Mixed or unavailable release | Test locally and in rollback rehearsal |
| The static server can serve a stable router as `cios` | High | Cutover failure | Probe sibling root before service change |
| All public artifacts fit bounded recursive scanning | High | Slow or incomplete validation | Enforce file count and byte limits |
| Existing consumers tolerate additive run-ID fields | High | Client regression | Preserve paths and schemas; run full suite |
| Blocked runs need status/diagnostics but must retain the decision surface | High | Misleading public state | Separate pointers and explicit status semantics |
| Historical product counts can currently mask incomplete extraction | High | False readiness | Require current-run completeness arithmetic |

Highest-risk experiment: construct a complete sibling release store, serve it
on a temporary loopback port as `cios`, atomically swap `current` under load,
and confirm every response resolves one generation. Threshold: zero mixed or
failed responses across the bounded probe.
