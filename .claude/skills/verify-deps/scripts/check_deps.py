"""Verify dependency manifests and optional Windows resolutions without editing the repo."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only used on Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        print("Python 3.11+ or the 'tomli' package is required", file=sys.stderr)
        raise SystemExit(2) from None

try:
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion, Version
except ModuleNotFoundError:
    print("The 'packaging' package is required; run: python -m pip install packaging", file=sys.stderr)
    raise SystemExit(2) from None


DEFAULT_PYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13")
SECTION_MARKERS = {
    "# BEGIN RUNTIME DEPENDENCIES": "runtime",
    "# END RUNTIME DEPENDENCIES": None,
    "# BEGIN TEST DEPENDENCIES": "test",
    "# END TEST DEPENDENCIES": None,
}


@dataclass(frozen=True)
class RequirementEntry:
    requirement: Requirement
    line_number: int
    section: str | None


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def requirement_key(requirement: Requirement) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...], str]:
    specifiers = tuple(sorted((item.operator, str(item.version)) for item in requirement.specifier))
    marker = str(requirement.marker) if requirement.marker else ""
    return canonicalize_name(requirement.name), tuple(sorted(requirement.extras)), specifiers, marker


def strip_inline_comment(line: str) -> str:
    return line.split(" #", 1)[0].rstrip()


def parse_requirements(path: Path) -> tuple[list[RequirementEntry], dict[str, list[Requirement]], list[str], list[str]]:
    entries: list[RequirementEntry] = []
    sections: dict[str, list[Requirement]] = {"runtime": [], "test": []}
    constraint_refs: list[str] = []
    errors: list[str] = []
    section: str | None = None

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped in SECTION_MARKERS:
            section = SECTION_MARKERS[stripped]
            continue
        if not stripped or stripped.startswith("#"):
            continue

        if stripped in {"-c constraints.txt", "--constraint constraints.txt"}:
            constraint_refs.append("constraints.txt")
            continue
        if stripped.startswith("-c ") or stripped.startswith("--constraint "):
            constraint_refs.append(stripped.split(None, 1)[1])
            continue
        if stripped.startswith("-r ") or stripped.startswith("--requirement "):
            errors.append(f"line {line_number}: nested requirement files are not supported")
            continue
        if stripped.startswith("-"):
            errors.append(f"line {line_number}: unsupported requirements option {stripped!r}")
            continue

        candidate = strip_inline_comment(stripped)
        try:
            requirement = Requirement(candidate)
        except InvalidRequirement as exc:
            errors.append(f"line {line_number}: invalid requirement {candidate!r}: {exc}")
            continue
        entry = RequirementEntry(requirement, line_number, section)
        entries.append(entry)
        if section in sections:
            sections[section].append(requirement)

    return entries, sections, constraint_refs, errors


def parse_constraints(path: Path) -> tuple[dict[str, tuple[Requirement, int]], list[str]]:
    constraints: dict[str, tuple[Requirement, int]] = {}
    errors: list[str] = []

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-"):
            errors.append(f"line {line_number}: constraints cannot contain options or nested files")
            continue
        try:
            requirement = Requirement(strip_inline_comment(stripped))
        except InvalidRequirement as exc:
            errors.append(f"line {line_number}: invalid constraint {stripped!r}: {exc}")
            continue

        name = canonicalize_name(requirement.name)
        if requirement.extras:
            errors.append(f"line {line_number}: constraint {name!r} cannot specify extras")
        if name in constraints:
            errors.append(f"line {line_number}: duplicate constraint for {name!r}")
            continue
        specifiers = list(requirement.specifier)
        if len(specifiers) != 1 or specifiers[0].operator != "==":
            errors.append(f"line {line_number}: constraint {name!r} must contain exactly one == pin")
            continue
        constraints[name] = (requirement, line_number)

    return constraints, errors


def load_project_requirements(path: Path) -> tuple[dict[str, list[Requirement]], list[str]]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"could not parse pyproject.toml: {exc}"]

    project = data.get("project")
    if not isinstance(project, dict):
        return {}, ["pyproject.toml is missing [project]"]

    errors: list[str] = []
    result: dict[str, list[Requirement]] = {}
    optional = project.get("optional-dependencies")
    test_values = optional.get("test") if isinstance(optional, dict) else None
    for section, values in (("runtime", project.get("dependencies")), ("test", test_values)):
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            errors.append(f"pyproject.toml is missing project dependency list for {section!r}")
            result[section] = []
            continue
        parsed: list[Requirement] = []
        for value in values:
            try:
                parsed.append(Requirement(value))
            except InvalidRequirement as exc:
                errors.append(f"pyproject.toml has invalid {section} dependency {value!r}: {exc}")
        result[section] = parsed
    return result, errors


def add_check(checks: list[Check], name: str, passed: bool, detail: str) -> None:
    checks.append(Check(name, passed, detail.replace("\n", " ").replace("|", "/")))


def compare_requirement_lists(left: list[Requirement], right: list[Requirement]) -> bool:
    return Counter(requirement_key(item) for item in left) == Counter(requirement_key(item) for item in right)


def constraint_version(requirement: Requirement) -> str:
    return next(iter(requirement.specifier)).version


def verify_static(repo: Path, checks: list[Check]) -> tuple[bool, dict[str, tuple[Requirement, int]]]:
    requirements_path = repo / "requirements.txt"
    constraints_path = repo / "constraints.txt"
    pyproject_path = repo / "pyproject.toml"
    for name, path in (
        ("requirements-file", requirements_path),
        ("constraints-file", constraints_path),
        ("pyproject-file", pyproject_path),
    ):
        if not path.is_file():
            add_check(checks, name, False, f"{path.name} is missing")
            return False, {}

    try:
        entries, requirement_sections, constraint_refs, requirement_errors = parse_requirements(requirements_path)
        constraints, constraint_errors = parse_constraints(constraints_path)
        project_sections, project_errors = load_project_requirements(pyproject_path)
    except OSError as exc:
        add_check(checks, "manifest-read", False, str(exc))
        return False, {}

    add_check(
        checks,
        "requirements-parse",
        not requirement_errors,
        "; ".join(requirement_errors) or f"{len(entries)} requirements parsed",
    )
    add_check(
        checks,
        "constraints-parse",
        not constraint_errors,
        "; ".join(constraint_errors) or f"{len(constraints)} exact pins parsed",
    )
    add_check(checks, "pyproject-parse", not project_errors, "; ".join(project_errors) or "dependency metadata parsed")
    add_check(
        checks,
        "requirements-include-constraints",
        constraint_refs == ["constraints.txt"],
        "requirements.txt includes -c constraints.txt"
        if constraint_refs == ["constraints.txt"]
        else f"expected exactly -c constraints.txt, found {constraint_refs or '<none>'}",
    )

    sections_present = {entry.section for entry in entries}
    sections_ok = {"runtime", "test"}.issubset(sections_present)
    add_check(
        checks,
        "requirements-sections",
        sections_ok,
        "runtime and test sections are marked"
        if sections_ok
        else "requirements need BEGIN/END runtime and test markers",
    )

    runtime_match = compare_requirement_lists(requirement_sections["runtime"], project_sections.get("runtime", []))
    test_match = compare_requirement_lists(requirement_sections["test"], project_sections.get("test", []))
    add_check(
        checks,
        "runtime-metadata-consistency",
        runtime_match,
        "requirements runtime section matches pyproject.toml"
        if runtime_match
        else "runtime requirements differ from pyproject.toml",
    )
    add_check(
        checks,
        "test-metadata-consistency",
        test_match,
        "requirements test section matches pyproject.toml"
        if test_match
        else "test requirements differ from pyproject.toml",
    )

    direct_requirements = [*project_sections.get("runtime", []), *project_sections.get("test", [])]
    direct_names = [canonicalize_name(item.name) for item in direct_requirements]
    duplicate_names = sorted(name for name, count in Counter(direct_names).items() if count > 1)
    add_check(
        checks,
        "direct-requirement-uniqueness",
        not duplicate_names,
        "direct dependency names are unique" if not duplicate_names else f"duplicate names: {duplicate_names}",
    )

    missing = sorted(set(direct_names) - set(constraints))
    add_check(
        checks,
        "direct-constraint-coverage",
        not missing,
        "all direct requirements are constrained" if not missing else f"missing pins: {missing}",
    )

    prerelease_names: list[str] = []
    for name, (requirement, _) in constraints.items():
        try:
            version = Version(constraint_version(requirement))
        except (InvalidVersion, StopIteration):
            continue
        if version.is_prerelease:
            prerelease_names.append(f"{name}=={version}")
    add_check(
        checks,
        "stable-constraint-pins",
        not prerelease_names,
        "all constraint pins are stable" if not prerelease_names else f"pre-release pins: {prerelease_names}",
    )

    incompatible: list[str] = []
    for requirement in direct_requirements:
        constrained = constraints.get(canonicalize_name(requirement.name))
        if constrained is None:
            continue
        pin = constraint_version(constrained[0])
        if not requirement.specifier.contains(pin, prereleases=True):
            incompatible.append(f"{requirement.name} {requirement.specifier} excludes {pin}")
    add_check(
        checks,
        "constraint-range-consistency",
        not incompatible,
        "all pins satisfy direct ranges" if not incompatible else "; ".join(incompatible),
    )

    return all(item.passed for item in checks), constraints


def summarize_process(process: subprocess.CompletedProcess[str]) -> str:
    output = (process.stderr or process.stdout or "").strip().splitlines()
    return " ".join(output[-6:]) if output else f"pip exited with {process.returncode}"


def verify_windows_resolution(
    repo: Path, constraints: dict[str, tuple[Requirement, int]], versions: list[str], timeout: int, checks: list[Check]
) -> None:
    for python_version in versions:
        check_name = f"windows-resolution-{python_version}"
        if not re.fullmatch(r"\d+\.\d+", python_version):
            add_check(checks, check_name, False, "Python version must be MAJOR.MINOR")
            continue
        abi = "cp" + python_version.replace(".", "")
        report_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="verify-deps-", suffix=".json", delete=False) as report_file:
                report_path = Path(report_file.name)
            command = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--upgrade",
                "--ignore-installed",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "--platform",
                "win_amd64",
                "--implementation",
                "cp",
                "--abi",
                abi,
                "--python-version",
                python_version,
                "--report",
                str(report_path),
                "-r",
                "requirements.txt",
            ]
            process = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=timeout, check=False)
            if process.returncode:
                add_check(checks, check_name, False, summarize_process(process))
                continue
            report = json.loads(report_path.read_text(encoding="utf-8"))
            resolved = {
                canonicalize_name(item["metadata"]["name"]): item["metadata"]["version"]
                for item in report.get("install", [])
            }
            missing = sorted(set(resolved) - set(constraints))
            mismatches = sorted(
                f"{name} resolved {version}, constrained {constraint_version(constraints[name][0])}"
                for name, version in resolved.items()
                if name in constraints and Version(version) != Version(constraint_version(constraints[name][0]))
            )
            if missing:
                detail = f"unconstrained resolved packages: {missing}"
            elif mismatches:
                detail = "; ".join(mismatches)
            else:
                detail = f"{len(resolved)} packages match constraints"
            add_check(checks, check_name, not missing and not mismatches, detail)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, InvalidVersion) as exc:
            add_check(checks, check_name, False, str(exc))
        finally:
            if report_path is not None:
                report_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    parser.add_argument("--resolve-windows", action="store_true", help="run pip dry-run resolution for Windows wheels")
    parser.add_argument(
        "--python-version", action="append", dest="python_versions", help="Windows Python MAJOR.MINOR; repeatable"
    )
    parser.add_argument("--timeout", type=int, default=180, help="per-version pip timeout in seconds")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of CHECK lines")
    args = parser.parse_args()

    repo = args.repo.resolve()
    checks: list[Check] = []
    _, constraints = verify_static(repo, checks)
    if args.resolve_windows and constraints:
        verify_windows_resolution(
            repo, constraints, args.python_versions or list(DEFAULT_PYTHON_VERSIONS), args.timeout, checks
        )

    passed = all(item.passed for item in checks)
    if args.json:
        print(
            json.dumps({"result": "PASS" if passed else "FAIL", "checks": [item.__dict__ for item in checks]}, indent=2)
        )
    else:
        for item in checks:
            print(f"CHECK|{item.name}|{'PASS' if item.passed else 'FAIL'}|{item.detail}")
        print(f"RESULT|{'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
