"""
End-to-end installation tests, installing real packages from PyPI and npm.

They modify the Python environment and the global npm packages, so they only
run in the throwaway environment created by:

    python .github/scripts/run_install_tests.py
"""
import json
import os
import shutil
import sys

import jupyter_core.paths
import pytest

from ..handlers import ACP_INSTALL_TIMEOUT



def _in_throwaway_env() -> bool:
    """Whether the tests run in the environment created by run_install_tests.py."""
    env_dir = os.environ.get("JUPYTER_AI_MANAGER_INSTALL_TESTS")
    if not env_dir or not os.environ.get("NPM_CONFIG_PREFIX"):
        return False
    try:
        return os.path.samefile(sys.prefix, env_dir)
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _in_throwaway_env(),
    reason="run with `python .github/scripts/run_install_tests.py`",
)


@pytest.fixture
def jp_server_config(jp_server_config):
    """Also load JupyterLab, which provides the extension manager API."""
    return {
        **jp_server_config,
        "ServerApp": {
            **jp_server_config["ServerApp"],
            "jpserver_extensions": {
                **jp_server_config["ServerApp"]["jpserver_extensions"],
                "jupyterlab": True,
            },
        },
    }


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not available")
async def test_install_claude_acp_client(jp_fetch):
    response = await jp_fetch(
        "jupyter-ai-manager",
        "acp-clients",
        "install",
        method="POST",
        body=json.dumps({"name": "Claude"}),
        request_timeout=ACP_INSTALL_TIMEOUT,
    )

    assert json.loads(response.body) == {"available": True}
    assert shutil.which("claude-agent-acp") is not None

    response = await jp_fetch("jupyter-ai-manager", "acp-clients")
    clients = json.loads(response.body)["acp_clients"]
    claude = next(c for c in clients if c["name"] == "Claude")
    assert claude["available"]


# Keep this test last: loading the server extensions in the test process cannot
# be undone, and prevents the next test servers from starting.
async def test_install_acp_client_extension(jp_fetch, jp_serverapp, monkeypatch):
    # Installing the package using handler.
    response = await jp_fetch(
        "lab",
        "api",
        "extensions",
        method="POST",
        body=json.dumps({"cmd": "install", "extension_name": "jupyter-ai-acp-client"}),
        request_timeout=ACP_INSTALL_TIMEOUT,
    )

    payload = json.loads(response.body)
    assert payload["status"] == "ok", payload.get("message")

    response = await jp_fetch("jupyter-ai-manager", "extensions")
    extensions = json.loads(response.body)["extensions"]
    acp = next(e for e in extensions if e["pip_package"] == "jupyter-ai-acp-client")
    assert acp["installed"]

    # Test loading the server extension without restarting the server.
    monkeypatch.setattr(
        jupyter_core.paths,
        "ENV_CONFIG_PATH",
        [
            *jupyter_core.paths.ENV_CONFIG_PATH,
            os.path.join(sys.prefix, "etc", "jupyter"),
        ],
    )
    response = await jp_fetch(
        "jupyter-ai-manager",
        "load",
        method="POST",
        body=json.dumps({"import_name": "jupyter_ai_acp_client"}),
    )

    assert response.code == 200
    assert "jupyter_ai_acp_client" in jp_serverapp.extension_manager.linked_extensions
