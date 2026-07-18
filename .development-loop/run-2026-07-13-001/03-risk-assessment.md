# Risk Assessment

## Pre-mortem

| Failure | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Batch timeout remains shorter than child budget | High | High | Validate and derive a dedicated bounded batch budget |
| Timeout kills only the Python parent | Proven | High | Start a new process session and terminate its process group |
| Partial exports are mistaken for complete evidence | Medium | High | Structured per-item summary and blocked readiness |
| Missing GA4 is hidden to make cron green | Medium | High | Separate runtime health from product readiness; preserve blocked artifacts |
| More parallel workers overload the VPS | Medium | Medium | Retain bounded worker count and avoid increasing it in this slice |

## STRIDE

- Spoofing: no identity boundary changes.
- Tampering: partial output can currently survive a killed parent; structured
  terminal status and later publication gates mitigate this.
- Repudiation: stage ledger and result summary must retain exact timeout cause.
- Information disclosure: subprocess errors remain bounded and must not print
  environment values.
- Denial of service: contradictory nested timeouts and orphan descendants are
  the active issue; process-group supervision is required.
- Elevation of privilege: no root execution path is introduced; services remain
  `cios` and `cios-shim`.

No named regulatory regime adds a requirement to this internal recovery slice.
Recommendation: proceed, with live deployment blocked until tests and review
pass.
