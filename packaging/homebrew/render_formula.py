#!/usr/bin/env python3
"""Render the Homebrew formula for a gitpulse-analytics release.

Resolves the package's runtime dependencies in a throwaway virtualenv, then looks up
each one's sdist on PyPI to write the resource blocks Homebrew needs.

    render_formula.py 0.2.0 > Formula/gitpulse.rb
    render_formula.py 0.2.0 --sdist dist/gitpulse_analytics-0.2.0.tar.gz  # local testing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
import venv
from pathlib import Path

PACKAGE = "gitpulse-analytics"
TEMPLATE = Path(__file__).with_name("gitpulse.rb")


def pypi_sdist(name: str, version: str) -> tuple[str, str]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as resp:
        files = json.load(resp)["urls"]
    for item in files:
        if item["packagetype"] == "sdist":
            return item["url"], item["digests"]["sha256"]
    raise SystemExit(f"{name} {version} has no sdist on PyPI; Homebrew builds resources from source")


def resolve_dependencies(spec: str) -> list[tuple[str, str]]:
    """Install SPEC into a temporary virtualenv and return its pinned dependencies."""
    with tempfile.TemporaryDirectory() as tmp:
        venv.create(tmp, with_pip=True)
        python = str(Path(tmp) / "bin" / "python")
        subprocess.run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", spec], check=True)
        listing = subprocess.run(
            [python, "-m", "pip", "list", "--format=json", "--exclude", "pip"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    skip = {PACKAGE, "setuptools", "wheel"}
    return sorted(
        (item["name"].lower(), item["version"])
        for item in json.loads(listing)
        if item["name"].lower() not in skip
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--sdist", help="Use a local sdist instead of the PyPI release.")
    args = parser.parse_args()

    if args.sdist:
        sdist = Path(args.sdist).resolve()
        url, sha256 = sdist.as_uri(), hashlib.sha256(sdist.read_bytes()).hexdigest()
        spec = str(sdist)
    else:
        url, sha256 = pypi_sdist(PACKAGE, args.version)
        spec = f"{PACKAGE}=={args.version}"

    blocks = []
    for name, version in resolve_dependencies(spec):
        dep_url, dep_sha = pypi_sdist(name, version)
        blocks.append(f'  resource "{name}" do\n    url "{dep_url}"\n    sha256 "{dep_sha}"\n  end')

    formula = (
        TEMPLATE.read_text()
        .replace("@URL@", url)
        .replace("@SHA256@", sha256)
        .replace("  @RESOURCES@", "\n\n".join(blocks))
    )
    sys.stdout.write(formula)


if __name__ == "__main__":
    main()
