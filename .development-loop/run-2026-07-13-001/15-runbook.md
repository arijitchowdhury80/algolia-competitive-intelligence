# Phase 1 Runtime Runbook

## Pre-deployment

1. Confirm `cios-runner.service` is inactive and `cios-runner.path` is active.
2. Verify the release archive checksum against the reviewed commit.
3. Preserve `/opt/cios/app/run-queue`, `.state`, `out`, `tmp`, and the known
   stale queue artifact.
4. Back up the currently deployed wrapper and package verifier.

## Deployment

1. Stop only `cios-runner.path` and the inactive runner service.
2. Install the immutable archive under `/opt/cios/releases/`.
3. Overlay tracked source into `/root/.hermes/apps/cios` without deleting
   runtime state.
4. Install the Hermes-facing wrapper as `cios:hermes` mode 0750.
5. Run `deploy/cios-host-permissions.sh`.
6. Reload systemd and start `cios-runner.path`.

## Post-deploy Validation

1. Run package preflight as `cios` in a delegated transient cgroup.
2. Verify container-side queue-client startup as `hermes`.
3. Trigger through Hermes cron, not a root shell substitute.
4. Track request ID through `.running`, `active-run`, `.result`, and `.done`.
5. Confirm runtime user, cgroup membership, error counts, terminal result,
   public status, root-owned count, and post-run hash stability.

## Rollback Trigger

Rollback if the queue cannot enqueue, Linux preflight fails, a real run returns
nonzero, permission or secret-leak indicators appear, a cgroup or job remains
after terminal status, or runtime/public ownership drifts to root.

## Rollback Procedure

1. Stop `cios-runner.path` and `cios-runner.service`.
2. Preserve current queue, private logs, outputs, and public diagnostics.
3. Verify the selected rollback archive checksum.
4. Overlay the archive without deleting runtime state.
5. Reinstall the reviewed wrapper and units; rerun host permissions.
6. Reload systemd and start the path unit.
7. Run delegated Linux preflight and one real Hermes smoke run before declaring
   service restored.

The Phase 1 rollback baseline is `1fa7ac5`; use it for later-phase rollback.
