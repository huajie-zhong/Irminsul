---
id: release
title: Release Process
status: stable
summary: How a tagged release is built and published.
describes: []
---

# Release Process

Irminsul releases are driven by pushing a `v*.*.*` tag, which fires `.github/workflows/release.yml`; its header comment and jobs describe the pipeline. The version number is derived from the tag by `hatch-vcs`; do not hand-edit version strings.

The `build` job `needs:` the `verify` job, which runs `pytest -q` and `irminsul check` on the tagged commit, so a tag whose tests or self-check fail publishes nothing. `verify` runs on one platform and one Python version, so the CI matrix still has to be green before tagging, as the checklist below requires.

The PyPI step publishes with `skip-existing: true`, which makes it idempotent: re-running the workflow after a partial failure is safe.

## One-time setup

Before the first release:

- **PyPI**: add a trusted publisher at `https://pypi.org/manage/account/publishing/` pointing to this repo and `release.yml`.
- **ghcr.io**: no setup required; `GITHUB_TOKEN` already has the right scopes. <!-- irminsul:ignore code-references/unknown-env-var reason="a CI secret the release workflow reads, not this code" -->

## Pre-release checklist

- [ ] Tests green on all CI matrix entries
- [ ] `irminsul check` passes on the release branch
- [ ] CHANGELOG updated with the new version entry
- [ ] The version pin in the [README](../../README.md) updated to the new version. The workflows `init` scaffolds are not on this list: `action_ref()` derives their pin from the installed version.

## Scope & Limitations

This doc covers the automated release pipeline only. It does not describe how to roll back a bad release. Docker image signing and SBOM generation are not currently implemented.
