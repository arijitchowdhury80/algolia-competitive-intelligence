# SOP Constraints

The Google Drive SOP paths named by `module-builder` are absent. Verified
current copies were read from:

- `/Users/arijitchowdhury/Dropbox/AI-Development/Obsidian/Arijit-Second-Brain/Standards/CodingSOPs.md`
- `/Users/arijitchowdhury/Dropbox/AI-Development/Obsidian/Arijit-Second-Brain/Standards/TestingSOPs.md`

## Coding

- Validate file and inter-module boundaries with Pydantic v2 models.
- Fully type public functions and run strict static checks available in this
  repository.
- Fail fast; catch specific filesystem/parse errors with structured context and
  never swallow failures.
- Keep responsibilities separated: staging, manifesting, scanning, validating,
  and promoting are distinct operations.
- Never log secret values or matched unsafe content.
- Use least privilege, safe relative paths, and no hardcoded credentials.
- Follow existing repository style where the global SOP's strict 20-line rule
  would conflict with established testable orchestration patterns; record any
  intentional exception in code review.

## Testing

- Map and run current wrapper, publisher, exporter, and launch-gate tests before
  behavior changes.
- Write each regression test first and observe the expected failure.
- Cover unit logic, filesystem integration, structured contract parsing, and
  live HTTP behavior at staging.
- Prefer real temporary directories and fakes over mock call-count assertions.
- Tests must be independent, deterministic, and readable as
  Arrange-Act-Assert stories.
- Track branch coverage where repository tooling supports it; the existing
  suite predates the newer SOP layout, so do not reorganize unrelated tests in
  this slice.
