---
id: release
title: Release Process
audience: reference
tier: 3
status: stable
describes: []
---

# Release Process

Irminsul releases are driven by git tags. The version number is derived from the tag by `hatch-vcs`; do not hand-edit version strings.

## Trigger

Push a tag matching `v*.*.*` to the main branch:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

This fires `.github/workflows/release.yml`.

## Pipeline

1. **Build** — a single `build` job checks out the repo with full history (`fetch-depth: 0`), builds the wheel and sdist via `python -m build`, and uploads the dist artifact. All subsequent jobs consume this one artifact.

2. **PyPI** — publishes via OIDC trusted publishing (`pypa/gh-action-pypi-publish`). `skip-existing: true` makes the step idempotent; re-running the workflow after a partial failure is safe.

3. **Docker** — builds and pushes `ghcr.io/<owner>/irminsul:<version>` and `ghcr.io/<owner>/irminsul:latest` to GitHub Container Registry using the pre-built wheel.

4. **Homebrew tap** — dispatches an `irminsul-release` repository event to `<owner>/homebrew-irminsul` via `peter-evans/repository-dispatch`. Requires a fine-grained PAT with `contents:write` on the tap repo, stored as `HOMEBREW_TAP_TOKEN`. The tap repo handles the formula bump.

## One-time setup

Before the first release:

- **PyPI**: add a trusted publisher at `https://pypi.org/manage/account/publishing/` pointing to this repo and `release.yml`.
- **Homebrew**: create `<owner>/homebrew-irminsul`, generate a fine-grained PAT with `contents:write` on it, and add it as repository secret `HOMEBREW_TAP_TOKEN`.
- **ghcr.io**: no setup required; `GITHUB_TOKEN` already has the right scopes.

## Pre-release checklist

- [ ] Tests green on all CI matrix entries
- [ ] `irminsul check --profile hard` passes on the release branch
- [ ] CHANGELOG updated with the new version entry

## Scope & Limitations

This doc covers the automated release pipeline only. It does not describe the Homebrew formula structure or how to roll back a bad release. Docker image signing and SBOM generation are not currently implemented.
