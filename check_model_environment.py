"""Hard version gate: fail if this environment can't be trusted to load the
committed model artifact.

The running service deliberately only *warns* when installed library versions
differ from the ones recorded in model_metadata.json. That is the right call
there -- crashing a live API over a patch bump trades a risk that the pickle
*might* misbehave for a certainty that the service *is* down. But that
leniency is only defensible if something stricter runs before deployment.
This is that stricter thing, and it runs in CI.

The difference in posture is the whole point: here, absence of evidence is a
failure. Unreadable metadata, a missing library_versions block, or a recorded
library that isn't installed all exit non-zero, because in CI there is no
running service whose uptime is worth protecting -- there is only a question
of whether this environment matches the artifact, and "can't tell" is not a
yes.

Exit codes: 0 = environment matches the artifact, 1 = it does not.
"""
from __future__ import annotations

import importlib.metadata
import json
import sys

import config

EXIT_OK = 0
EXIT_MISMATCH = 1


def _installed_version(library: str, runtime_tracked: dict[str, str]) -> str | None:
    """Version of `library` as this environment would actually use it.

    Prefers the number the running service itself reports, so the gate and
    production are reading the same value from the same code -- a separate
    hand-maintained list here would drift, and a gate that checks something
    other than what production checks is worse than no gate at all.

    Falls back to installed-distribution metadata for anything the service
    doesn't track, so a library recorded in the artifact still gets verified
    instead of silently skipped.
    """
    if library in runtime_tracked:
        return runtime_tracked[library]
    try:
        return importlib.metadata.version(library)
    except importlib.metadata.PackageNotFoundError:
        return None


def check_environment(metadata_path: str = config.METADATA_PATH) -> list[str]:
    """Return human-readable problems. An empty list means the environment
    matches the artifact and the build may proceed.
    """
    try:
        with open(metadata_path) as f:
            metadata = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot read {metadata_path}: {e}"]

    trained_versions = metadata.get("library_versions")
    if not trained_versions:
        return [
            f"{metadata_path} has no 'library_versions' block, so there is "
            f"nothing to check the environment against. Regenerate it by "
            f"running the notebook's save cell."
        ]
    if not isinstance(trained_versions, dict):
        return [
            f"'library_versions' in {metadata_path} is a "
            f"{type(trained_versions).__name__}, expected an object mapping "
            f"library name to version."
        ]

    runtime_tracked = config._current_library_versions()

    problems = []
    for library, trained_version in sorted(trained_versions.items()):
        installed_version = _installed_version(library, runtime_tracked)
        if installed_version is None:
            problems.append(
                f"{library}: artifact was trained with {trained_version}, "
                f"but it is not installed here"
            )
        elif installed_version != trained_version:
            problems.append(
                f"{library}: artifact was trained with {trained_version}, "
                f"this environment has {installed_version}"
            )
    return problems


def main() -> int:
    problems = check_environment()
    if problems:
        print("FAIL: this environment does not match the committed model artifact.")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\njoblib/pickle does not guarantee cross-version compatibility for "
            "scikit-learn or XGBoost objects, so loading the artifact here may "
            "fail outright or -- worse -- return silently different predictions."
            "\nResolve by either re-running the notebook to retrain and rewrite "
            "model_metadata.json, or pinning this environment back to the "
            "versions above."
        )
        return EXIT_MISMATCH

    print("OK: installed library versions match model_metadata.json.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
