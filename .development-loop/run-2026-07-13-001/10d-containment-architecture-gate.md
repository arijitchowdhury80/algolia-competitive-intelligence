# Phase 1 Containment Architecture Gate

Status: APPROVED by Arijit on 2026-07-14 after the three-strike rectification
circuit breaker.

## Decision

Replace PID/process-group discovery with hierarchical cgroup v2 containment:

1. systemd owns the full CI-OS run cgroup and executes the service as
   `User=cios`, `Group=cios`;
2. systemd delegates only the unit's private cgroup subtree to `cios`;
3. each child command enters a dedicated nested cgroup before its target
   executable can run or fork;
4. command timeout writes to that nested cgroup's `cgroup.kill` and waits for
   `cgroup.events` to report `populated 0`;
5. whole-run timeout is enforced by systemd with `KillMode=control-group`, with
   completion/result finalization occurring only after group cleanup.

No Hermes core change is involved. `chowmesadmin` remains deployment-only and
never executes CI-OS application work. Root/systemd owns unit lifecycle, as it
does for every system service; the application processes remain `cios`.

## Evidence

Live read-only VPS inspection on 2026-07-14 established:

- Ubuntu kernel `6.8.0-134-generic`;
- systemd 255 with unified cgroup v2;
- `cgroup.kill` is present on active service cgroups;
- `cios-runner.service` already uses `User=cios`, `Group=cios`, and
  `KillMode=control-group`;
- `Delegate=no` is the current missing capability;
- installed systemd documentation states that `Delegate=` makes an
  unprivileged `User=` service's private cgroup subtree accessible to that
  user while systemd retains ownership above it;
- `DelegateSubgroup=` is available in systemd 255 to place the supervisor in a
  leaf cgroup before it creates command subgroups.

The rejected `b8ee261` design used a one-time process-table snapshot. A target
could fork and detach after that snapshot, producing three reproduced failures
under the independent review command. Repeated scans cannot make discovery and
kill atomic; containment must exist before target execution.

## Required Design Changes

### Run boundary

- Change the runner from `Type=oneshot` to a service type for which systemd can
  enforce a runtime ceiling.
- Keep `KillMode=control-group` and bounded `TimeoutStopSec`/SIGKILL escalation.
- Add `Delegate=yes` and `DelegateSubgroup=supervisor`.
- Process exactly one queue request per service activation.
- Replace shell PID-tree watchdogs with systemd unit timeout/stop semantics.
- Add an app-user finalizer that writes `.result`/`.done` only after systemd
  has completed cgroup cleanup; timeout finalization must be explicit and
  non-successful.

### Command boundary

- Resolve the delegated cgroup root from `/proc/self/cgroup`.
- Create a unique child cgroup for each supervised command.
- Launch through a minimal handshake process that moves itself into the child
  cgroup before `execve`; the target cannot fork before containment.
- On timeout or shutdown, use `cgroup.kill`, wait for `populated 0`, and remove
  the empty child cgroup.
- Keep process groups only as a local-development compatibility fallback.
- Deployed package preflight must fail closed when delegated cgroups or
  `cgroup.kill` are unavailable.

## TDD And Verification Contract

1. Existing detached-child tests remain and must pass repeatedly under the
   wider independent-review selection.
2. Add a fork-at-timeout stress regression, not only a fixed-sleep test.
3. Add tests proving the target cannot execute before cgroup placement.
4. Add wrapper/service tests proving whole-run timeout kills detached children
   before a terminal queue result is published.
5. Add package-preflight tests that reject missing delegation, missing
   `cgroup.kill`, and a launcher that executes before placement.
6. Run the full local suite and independent security/code review.
7. On the VPS, run a bounded disposable containment probe as `cios`, then two
   consecutive real Hermes-triggered runs with zero orphan processes, late
   writes, permission failures, or stale-public fallback.

## Rejected Alternatives

- Repeated `ps` or `/proc` tree scans: still race with fork/detach.
- Process groups alone: `setsid()` escapes them.
- Per-run cgroup without nested command groups: detached item work can continue
  until the full run exits.
- Weakening the no-orphan gate: contradicts the approved Phase 1 contract.

## Human Gate

Approval authorizes one architecture reset using the hierarchical cgroup design
above. It does not authorize Hermes-core changes, root application execution,
public-port changes, firewall changes, or deployment before local review gates
pass.

Decision: APPROVED. Implementation may resume with a fresh rectification audit.
