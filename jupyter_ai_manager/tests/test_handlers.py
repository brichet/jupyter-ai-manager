import json
import os
import shutil
import sys

import pytest
from tornado.httpclient import HTTPClientError

from ..handlers import ACP_CLIENTS, AI_EXTENSIONS, _install_argv


async def test_pip_packages_list(jp_fetch):
    response = await jp_fetch("jupyter-ai-manager", "extensions")

    assert response.code == 200
    payload = json.loads(response.body)
    default = sorted([ext["pip_package"] for ext in AI_EXTENSIONS])
    fetched = sorted([ext["pip_package"] for ext in payload["extensions"]])

    assert default == fetched


async def test_acp_clients_list(jp_fetch):
    response = await jp_fetch("jupyter-ai-manager", "acp-clients")

    assert response.code == 200
    clients = json.loads(response.body)["acp_clients"]
    assert sorted(c["name"] for c in clients) == sorted(c["name"] for c in ACP_CLIENTS)
    for client in clients:
        assert isinstance(client["available"], bool)
        assert isinstance(client["installable"], bool)


def test_install_argv_pip_uses_server_python():
    argv = _install_argv({"install_command": "pip install some-package"})
    assert argv == [sys.executable, "-m", "pip", "install", "some-package"]


def test_install_argv_resolves_installer_path(monkeypatch):
    # On Windows, npm is a `npm.cmd` wrapper which must be run by its full path.
    resolved = os.path.join("some", "path", "npm.cmd")
    monkeypatch.setattr(shutil, "which", lambda name: resolved if name == "npm" else None)
    argv = _install_argv({"install_command": "npm install -g some-package"})
    assert argv == [resolved, "install", "-g", "some-package"]


def test_install_argv_missing_installer(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert _install_argv({"install_command": "npm install -g some-package"}) is None


def test_install_argv_without_install_command():
    assert _install_argv({"name": "Goose"}) is None


async def test_install_unknown_acp_client(jp_fetch):
    with pytest.raises(HTTPClientError) as exc_info:
        await jp_fetch(
            "jupyter-ai-manager",
            "acp-clients",
            "install",
            method="POST",
            body=json.dumps({"name": "unknown"}),
        )
    assert exc_info.value.code == 404


async def test_install_acp_client_without_install_command(jp_fetch):
    with pytest.raises(HTTPClientError) as exc_info:
        await jp_fetch(
            "jupyter-ai-manager",
            "acp-clients",
            "install",
            method="POST",
            body=json.dumps({"name": "Goose"}),
        )
    assert exc_info.value.code == 400
