# Security Review

Verdict: PASS WITH RESIDUAL DEPENDENCY-LOCK RISK

The named security-review subagent could not be dispatched because the agent
thread limit was exhausted. This inline review follows the Development-Loop
security checklist and records the substitution.

## Findings

### Critical

None.

### High

None.

### Medium, rectified

1. **Concurrent publication race:** wrapper and admin promotion could interleave
   otherwise atomic file operations. A no-follow store lock now covers layout,
   generation install, pointer promotion, status commit, and rollback.
2. **Filesystem redirection:** pre-existing router or internal bucket symlinks
   could redirect reads or writes. Every fixed router target and real directory
   is now validated before staging.
3. **Incomplete launch authority:** a fresh publication PASS could be supplied
   without proving which served manifest it covered. Launch now hashes the exact
   served bytes and compares them with the publication verdict digest.
4. **Path and credential coverage:** the scanner omitted common macOS temp,
   container app, and Windows user paths, and only recognized scalar credential
   values. Those cases now fail closed without logging matched content.

### Residual

- The project has version ranges but no lock file. A pinned direct-dependency
  `pip-audit` found no known vulnerability for Pydantic 2.12.5, HTTPX 0.28.1,
  PyYAML 6.0.3, FastAPI 0.128.0, Uvicorn 0.40.0, and Psycopg 3.3.4. The first
  transitive-resolution attempt failed inside pip-audit's temporary venv; the
  successful bounded retry used `--no-deps --disable-pip`. No dependency was
  added or changed in this slice. Add a reviewed lock file in a later packaging
  phase before general distribution.
- Global `pip check` reports unrelated `python-jobspy` constraints in the host
  Python environment. CI-OS package preflight and tests use the project package
  contract; this slice did not alter that global environment.

## STRIDE validation

| Threat | Control and evidence | Result |
|---|---|---|
| Spoofing | Conservative run-ID grammar; fresh structured verdicts share one run ID | Pass |
| Tampering | Canonical SHA/size manifest, independent tree enumeration, exact served-manifest digest binding | Pass |
| Repudiation | Immutable run directories plus run-bound package/publication/click/launch verdicts | Pass |
| Information disclosure | Recursive path, credential-shape, and configured-secret scan; zero changed-file secret candidates | Pass |
| Denial of service | File/count limits, serialized publisher, status-last rollback, bounded cgroup service | Pass |
| Elevation of privilege | Static service is `User=cios`, `Group=cios`, loopback-only, sandboxed; no Hermes core/root runtime added | Pass |

## OWASP and boundary checks

- Broken access control: no public write/admin route added; static service is
  read-only and loopback-only.
- Cryptographic failures: SHA-256 is used for integrity, not secret storage.
- Injection: identifiers and paths use Pydantic constraints and canonical
  relative paths; shell run ID is generated internally.
- Insecure design: blocked diagnostics cannot promote the decision pointer.
- Security misconfiguration: systemd unit enforces no-new-privileges, private
  devices, protected system/home, memory/CPU/task limits, and loopback bind.
- Vulnerable components: direct pinned advisory scan passed; residual lock-file
  limitation recorded above.
- Authentication failures: no authentication surface changed.
- Data integrity failures: package, publication, click, and launch checks are
  structured, fresh, run-bound, and digest-bound.
- Logging failures: expected validation logs expose run ID and rule category,
  not matched secret values or internal generation paths.
- SSRF: no new outbound fetch path introduced.

The goal charter explicitly pre-authorizes routine non-destructive security
review and says to pause only for irreducible access or destructive decisions.
No such decision is present, so the human gate is satisfied by that standing
authorization. Advance to Code Review.
