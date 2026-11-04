"""Run the installation tests in a throwaway environment.

The installation tests install real packages from PyPI and npm. This script
creates a temporary virtual environment and a temporary global npm prefix,
installs the extension in it, runs the tests, then deletes everything, so that
the current environment is left untouched.

Run it with:

    python .github/scripts/run_install_tests.py [--package PATH] [PYTEST_ARGS...]

PATH is the extension to install (a wheel or a source directory), the
repository root by default. The other arguments are passed to pytest.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS = REPO_ROOT / "jupyter_ai_manager" / "tests" / "test_install.py"


def main() -> int:
    """Create the throwaway environment and run the installation tests in it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--package",
        default=str(REPO_ROOT),
        help="extension to install: a wheel or a source directory",
    )
    args, pytest_args = parser.parse_known_args()

    with tempfile.TemporaryDirectory(
        prefix="jupyter-ai-manager-install-tests-", ignore_cleanup_errors=True
    ) as tmp:
        env_dir = Path(tmp) / "venv"
        npm_prefix = Path(tmp) / "npm"
        npm_prefix.mkdir()

        print(f"Creating a throwaway environment in {tmp}", flush=True)
        venv.EnvBuilder(with_pip=True).create(env_dir)
        bin_dir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
        python = bin_dir / ("python.exe" if sys.platform == "win32" else "python")

        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "jupyterlab>=4.0.0,<5",
                f"{args.package}[test]",
            ],
            check=True,
        )

        # npm puts global executables in the prefix on Windows, and in its
        # `bin` directory elsewhere.
        env = {
            **os.environ,
            "JUPYTER_AI_MANAGER_INSTALL_TESTS": str(env_dir),
            "NPM_CONFIG_PREFIX": str(npm_prefix),
            "PATH": os.pathsep.join(
                [str(bin_dir), str(npm_prefix), str(npm_prefix / "bin"), os.environ["PATH"]]
            ),
        }
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONPATH", None)
        return subprocess.run(
            [str(python), "-m", "pytest", "-p", "no:cacheprovider", str(TESTS), *pytest_args],
            cwd=REPO_ROOT,
            env=env,
        ).returncode


if __name__ == "__main__":
    sys.exit(main())
