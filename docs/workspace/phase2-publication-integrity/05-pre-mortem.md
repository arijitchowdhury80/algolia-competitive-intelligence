# Pre-mortem

## Launch-blocking tigers

| Risk | Evidence | Mitigation | Owner | Decision date |
|---|---|---|---|---|
| Sequential promotion exposes mixed state | Current wrapper copies paths individually | One immutable generation plus one pointer swap | CI-OS developer | Before staging |
| Status appears before release completion | Current wrapper writes status before later artifacts | One shared status target, replaced last | CI-OS developer | Before staging |
| Safety can be self-attested | Current status hardcodes safety booleans | Independent recursive scanner | Security reviewer | Before staging |
| Cutover breaks live static serving | Live service reads the legacy directory directly | Sibling root, probe, backup, rollback drill | Chowmes operator | Staging gate |

## Fast follow

Retention policy for old immutable generations can wait until measured disk
growth exists. Phase 2 must retain rollback generations and does not delete
history automatically.

## Paper tiger

A Caddy rewrite is unnecessary: the existing reverse proxy already isolates a
single loopback static service whose document root can be changed safely.

## Elephant

The static service currently runs as root despite serving files owned by
`cios:hermes`. The Phase 2 cutover must remove that privilege, not perpetuate
it.
