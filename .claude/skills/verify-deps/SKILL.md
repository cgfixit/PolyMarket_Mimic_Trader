---
name: verify-deps
description: Read-only verification of requirements.txt, constraints.txt, and pyproject.toml dependency consistency, including Windows CPython resolution checks. Use when dependency manifests change, a fresh clone is prepared, a Windows install is suspected to drift, or a PR needs dependency evidence.
---

# Verify dependency manifests

This skill is read-only. It checks the repository's direct runtime and test
requirements, project metadata, exact constraints, and—when requested—the
Windows wheel resolution for the supported Python versions. It never edits
manifests, installs into the repository, commits, or publishes changes.

## Run the verifier

Run from the repository root:

```powershell
python .claude/skills/verify-deps/scripts/check_deps.py
```

Run the network-backed Windows resolution check when dependencies or package
metadata changed:

```powershell
python .claude/skills/verify-deps/scripts/check_deps.py --resolve-windows
```

The full check resolves Windows CPython 3.10, 3.11, 3.12, and 3.13 with
`pip install --dry-run --only-binary=:all:`. Override the matrix when needed:

```powershell
python .claude/skills/verify-deps/scripts/check_deps.py --resolve-windows --python-version 3.12 --python-version 3.13
```

If `packaging` is unavailable, install it in the active verification
environment (`python -m pip install packaging`) and rerun. Resolution checks
also require a pip version that supports `--dry-run` and access to the package
index; a failed network/tool check is a failed verification, not a pass.

## Checks and output

The verifier must report `RESULT|PASS` only when all of these hold:

- `requirements.txt` includes `-c constraints.txt`.
- The runtime section in `requirements.txt` exactly matches
  `[project].dependencies` in `pyproject.toml`.
- The test section exactly matches
  `[project.optional-dependencies].test`.
- Every direct requirement has one exact `==` constraint, and each pin
  satisfies the corresponding requirement range.
- Constraint pins are valid, non-pre-release versions and may include
  transitive packages pulled by the direct requirements.
- With `--resolve-windows`, every resolved package is present in
  `constraints.txt` at the pinned version for every requested Python version.

Output is intentionally machine-readable:

```text
CHECK|name|PASS|detail
RESULT|PASS
```

Use `--json` for automation. Exit code `0` means every requested check passed;
`1` means a manifest or resolution check failed; `2` means the verifier itself
could not start because a required tool or input is missing.

## Dependency-update workflow

1. Update the direct range in the runtime or test section of
   `requirements.txt`.
2. Mirror that range in `pyproject.toml`.
3. Resolve the Windows matrix with a temporary report and update
   `constraints.txt` only after reviewing the complete graph. Keep stable
   releases selected when an upstream lower bound permits a pre-release.
4. Run the static check and `--resolve-windows` check.
5. Run the repository's normal CI gates; this skill does not replace tests,
   Ruff, mypy, or `pip-audit`.

Do not add a package only to the constraints file to make it install. A
constraints file controls versions; it does not request installation. Keep
direct dependencies in both project metadata and the requirements sections,
and keep transitive pins traceable to the resolver report.
