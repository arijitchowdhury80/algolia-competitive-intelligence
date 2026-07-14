# Risk Assessment

## Pre-mortem

| Failure | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Pointer moves before validation completes | Medium | High | Immutable stage, complete manifest verification, pointer swap only after PASS |
| Root and `/v2` expose different generations | Proven current risk | High | Both route trees resolve through the same `current` and `latest-status` pointers |
| Blocked run erases last useful decision surface | Medium | High | Separate diagnostic generation; never move `current` on blocked status |
| Status says published before all artifacts resolve | Proven current risk | High | Atomically write one shared status target after pointer promotion |
| Run ID is accepted from an unsafe caller | Medium | High | Wrapper generates and validates it; production does not accept an external override |
| Safety scanner leaks the secret it detects | Medium | High | Report rule ID and relative file only; never matched text or environment values |
| Symlink traversal escapes the staged root | Medium | High | Reject symlinks and resolve every path beneath the generation root |
| Old direct publisher bypasses the new contract | High | High | One publication module used by wrapper and admin refresh; package verifier bans legacy copy sequence |
| Static service cutover breaks the public site | Medium | High | Seed and probe sibling served root, preserve old unit/root, bounded restart and rollback drill |
| Static server remains unnecessarily privileged | Current | High | `User=cios`, `Group=hermes`, read-only serving path after cutover |

## STRIDE

- Spoofing: structured evidence must name the same validated run ID; arbitrary
  PASS text cannot satisfy a check.
- Tampering: SHA-256 and size bind every regular file; immutable generation
  directories and pointer-only promotion prevent mixed writes.
- Repudiation: publication verdict records run ID, manifest digest, check
  results, timestamps, outcome, and prior/current pointer targets.
- Information disclosure: recursive scanning rejects local paths, file URLs,
  credential-shaped JSON, and configured secrets without echoing them.
- Denial of service: bounded file count/size, no symlink following, and atomic
  rollback prevent a partial stage from taking down the retained generation.
- Elevation of privilege: no root writer is introduced; static serving moves
  from root to the existing unprivileged `cios` account.

No named regulatory regime adds requirements to this internal pilot slice.
Security recommendation: proceed locally; production cutover is blocked until
security review, rollback rehearsal, and the staging gate pass.
