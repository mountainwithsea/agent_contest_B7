# Standalone reference checker migration

**Goal:** Copy the current reference hallucination checker into this cloned repository, remove application-level dependencies on the other project, verify and push to the user-specified remote.

**Authorization:** User explicitly requested clone into E:/Project, isolate the reference project and push. The original integrated repository and all task data must remain untouched.

## Scope

Preserve `reference-checker/` application, extraction, identity and tests; required `b7_shared` helpers; reference-only Electron desktop and Windows build scripts. Keep the folder layout to avoid modifying validated bibliographic algorithms. Retain the optional local AnyStyle formatter; fresh source installations may use the public formatter without Ruby/Node binaries.

Exclude private .env, task data, historical papers and datasets, cloned research repositories, model/runtime binaries, node_modules, installers, ZIPs and temporary test profiles. Do not copy the other application's source, tests or launch paths.

## Steps

- [x] Clone and inspect remote instructions; copy allowlisted source and provenance hashes.
- [x] Add standalone isolation regressions; observe failures against mixed configuration, then remove coupling from config, launcher, desktop UI, service manager and build payload.
- [x] Document installation, API configuration, workflow, desktop build and third-party origins; include an empty-key env template and ignore rules.
- [x] Run reference and shared tests, desktop tests and a fresh-profile HTTP smoke test. Check staged source for secrets, forbidden artifacts and unintended changes.
- [ ] Commit explicit paths, push the existing main branch without force, verify the remote commit and clean local status.

## Decisions

The clone is the isolated workspace. No changes or commits in the integrated repository. No new installer is required for this source migration. A desktop app built from this repository has its own application ID and user-data directory, preserving separation from the integrated desktop app.

## Verification notes

Fresh Python environment created from the pinned requirements. Reference suite 252 cases (two optional native formatter tests skipped without binary runtimes); both native formatter tests also passed separately using explicitly configured external binary dependencies. No old application imports are required. Desktop 9 tests and payload policy test passed.

Real HTTP two-reference run: both confirmed; total 13.242 seconds, remote public conversion, zero extraction/parsing/identity/search model calls. The test used a placeholder model key that was never called and temporary data only.

Independent review found that child_environment replaced configured external formatter paths. Reproduced with a regression, fixed, and verified. Launcher console-shutdown smoke exposed an indefinite Windows native wait that deferred signal handling; bounded waits fixed it. Actual startup, Ctrl+Break shutdown and backend termination then passed.

No independent desktop installer was built in this migration; the previous combined installer is not a release of this repository.
