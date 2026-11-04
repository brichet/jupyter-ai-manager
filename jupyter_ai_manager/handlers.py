import asyncio
import importlib.metadata
import json
import os
import shlex
import shutil
import subprocess
import sys
from functools import partial
from typing import Any

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
import tornado

AI_EXTENSIONS = [
    {
        "name": "ACP client",
        "pip_package": "jupyter-ai-acp-client",
        "import_name": "jupyter_ai_acp_client",
        "description": "ACP client integration for Jupyter AI",
        "homepage_url": "https://pypi.org/project/jupyter-ai-acp-client/",
    },
    {
        "name": "Jupyternaut",
        "pip_package": "jupyter-ai-jupyternaut",
        "import_name": "jupyter_ai_jupyternaut",
        "description": "Jupyternaut chat assistant for JupyterLab",
        "homepage_url": "https://pypi.org/project/jupyter-ai-jupyternaut/",
    },
    {
        "name": "AI lite",
        "pip_package": "jupyter-ai-lite",
        "import_name": "jupyter_ai_lite",
        "description": "AI integration working in the browser (no server needed)",
        "homepage_url": "https://pypi.org/project/jupyter-ai-lite/",
    },
    {
        "name": "AI tools",
        "pip_package": "jupyter-ai-tools",
        "import_name": "jupyter_ai_tools",
        "description": "AI-powered tools and utilities for JupyterLab",
        "homepage_url": "https://pypi.org/project/jupyter-ai-tools/",
    },
    {
        "name": "Jupyter server MCP",
        "pip_package": "jupyter-server-mcp",
        "import_name": "jupyter_server_mcp",
        "description": "Model Context Protocol server extension for Jupyter",
        "homepage_url": "https://pypi.org/project/jupyter-server-mcp/",
    },
]


ACP_CLIENTS = [
    {
        "name": "Claude",
        "executable": "claude-agent-acp",
        "description": "Claude Code as an ACP agent persona.",
        "docs_url": "https://docs.anthropic.com/en/docs/claude-code/quickstart",
        "install_command": "npm install -g @agentclientprotocol/claude-agent-acp",
    },
    {
        "name": "Codex",
        "executable": "codex-acp",
        "description": "OpenAI Codex as an ACP agent persona.",
        "docs_url": "https://developers.openai.com/codex/cli",
        "install_command": "npm install -g @agentclientprotocol/codex-acp",
    },
    {
        "name": "Copilot",
        "executable": "copilot",
        "description": "GitHub Copilot as an ACP agent persona.",
        "docs_url": "https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli",
        "install_command": "npm install -g @github/copilot",
    },
    {
        "name": "Goose",
        "executable": "goose",
        "description": "Block's Goose AI agent as an ACP persona.",
        "docs_url": "https://block.github.io/goose/docs/getting-started/installation",
    },
    {
        "name": "Kilo",
        "executable": "kilo",
        "description": "Kilo AI agent as an ACP persona.",
        "docs_url": "https://kilo.ai/cli",
        "install_command": "npm install -g @kilocode/cli",
    },
    {
        "name": "Kiro",
        "executable": "kiro-cli",
        "description": "Kiro AI agent as an ACP persona.",
        "docs_url": "https://kiro.dev/docs/cli/installation/",
    },
    {
        "name": "Mistral Vibe",
        "executable": "vibe-acp",
        "description": "Mistral Vibe as an ACP agent persona.",
        "docs_url": "https://docs.mistral.ai/mistral-vibe/introduction/install",
        "install_command": "pip install mistral-vibe",
    },
    {
        "name": "OpenCode",
        "executable": "opencode",
        "description": "OpenCode AI agent as an ACP persona.",
        "docs_url": "https://opencode.ai/docs/#install",
        "install_command": "npm install -g opencode-ai",
    },
]


def _is_installed(pip_package: str) -> bool:
    try:
        importlib.metadata.version(pip_package)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


class ExtensionsRouteHandler(APIHandler):
    @tornado.web.authenticated
    def get(self):
        extensions = [
            {**ext, "installed": _is_installed(ext["pip_package"])}
            for ext in AI_EXTENSIONS
        ]
        self.finish({"extensions": extensions})


ACP_INSTALL_TIMEOUT = 600
"""Maximum duration (in seconds) of an ACP client install command."""

_acp_install_lock = asyncio.Lock()


def _install_argv(client: dict) -> list[str] | None:
    """
    Return the arguments to run the install command of an ACP client on the
    server, or None if it has no install command or its installer is missing.
    """
    command = client.get("install_command")
    if not command:
        return None
    argv = shlex.split(command)
    if argv[0] == "pip":
        # Install into the Python environment running the server.
        return [sys.executable, "-m", "pip", *argv[1:]]
    # Use the resolved path, so that wrappers like `npm.cmd` run on Windows.
    executable = shutil.which(argv[0])
    if executable is None:
        return None
    return [executable, *argv[1:]]


class AcpClientsRouteHandler(APIHandler):
    @tornado.web.authenticated
    def get(self):
        clients = [
            {
                **client,
                "available": shutil.which(client["executable"]) is not None,
                "installable": _install_argv(client) is not None,
            }
            for client in ACP_CLIENTS
        ]
        self.finish({"acp_clients": clients})


class AcpClientInstallRouteHandler(APIHandler):
    @tornado.web.authenticated
    async def post(self):
        """
        Run the install command of an ACP client, then refresh the personas so
        that the new agent becomes available without restarting the server.
        """
        name = (self.get_json_body() or {}).get("name", "")
        client = next((c for c in ACP_CLIENTS if c["name"] == name), None)
        if client is None:
            self.set_status(404)
            self.finish({"message": f"Unknown ACP client '{name}'"})
            return

        argv = _install_argv(client)
        if argv is None:
            self.set_status(400)
            self.finish(
                {
                    "message": f"'{name}' cannot be installed from JupyterLab, "
                    "see its documentation instead."
                }
            )
            return

        command = client["install_command"]
        # Run in a thread rather than with asyncio subprocesses, which are not
        # supported by the selector event loop used by Jupyter Server on Windows.
        async with _acp_install_lock:
            try:
                proc = await asyncio.get_running_loop().run_in_executor(
                    None,
                    partial(
                        subprocess.run,
                        argv,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=ACP_INSTALL_TIMEOUT,
                    ),
                )
            except subprocess.TimeoutExpired:
                self.set_status(504)
                self.finish({"message": f"`{command}` timed out"})
                return
            except OSError as exc:
                self.set_status(500)
                self.finish({"message": f"Failed to run `{command}`: {exc}"})
                return

        if proc.returncode != 0:
            tail = proc.stdout.decode(errors="replace").strip()[-2000:]
            self.log.error(f"jupyter_ai_manager: `{command}` failed:\n{tail}")
            self.set_status(500)
            self.finish(
                {
                    "message": f"`{command}` failed "
                    f"(exit code {proc.returncode}):\n{tail}"
                }
            )
            return

        available = shutil.which(client["executable"]) is not None
        if available:
            _refresh_persona_managers(self.application, self.log)
        self.finish({"available": available})


class LoadExtensionRouteHandler(APIHandler):
    @tornado.web.authenticated
    def post(self):
        body = self.get_json_body()
        import_name = (body or {}).get("import_name", "")

        if not import_name:
            self.set_status(400)
            self.finish({"message": "Missing import_name"})
            return

        pip_package = next(
            (e["pip_package"] for e in AI_EXTENSIONS if e["import_name"] == import_name),
            None,
        )
        if pip_package is None or not _is_installed(pip_package):
            self.set_status(404)
            self.finish({"message": f"Package '{import_name}' is not installed"})
            return

        try:
            _register_server_extension(self.application, self.log)
        except Exception as exc:
            self.log.exception(f"jupyter_ai_manager: error registering '{import_name}'")
            self.set_status(500)
            self.finish({"message": f"Failed to register handlers for '{import_name}': {exc}"})
            return

        self.finish({"status": "ok"})


def _register_server_extension(web_app: Any, log: Any) -> None:
    from jupyter_core.paths import jupyter_config_path
    from jupyter_server.extension.manager import ExtensionManager

    server_app = web_app.settings.get("serverapp")
    if server_app is None:
        raise RuntimeError("serverapp not found in web_app settings")

    ext_manager: ExtensionManager = server_app.extension_manager

    # Collect every extension declared in jupyter_server_config.d files.
    configured: dict[str, bool] = {}
    for config_dir in jupyter_config_path():
        ext_dir = os.path.join(config_dir, "jupyter_server_config.d")
        if not os.path.isdir(ext_dir):
            continue
        for fname in os.listdir(ext_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(ext_dir, fname)) as fh:
                    data = json.load(fh)
                configured.update(
                    data.get("ServerApp", {}).get("jpserver_extensions", {})
                )
            except Exception:
                pass

    already_loaded: set[str] = set(ext_manager.linked_extensions.keys())

    to_load = [
        ext_name
        for ext_name, enabled in configured.items()
        if enabled
        and ext_name not in already_loaded
        and ext_name != "jupyter_ai_manager"
    ]

    for ext_name in to_load:
        ext_manager.add_extension(ext_name, enabled=True)
        ext_manager.link_extension(ext_name)
        ext_manager.load_extension(ext_name)

    _refresh_persona_managers(web_app, log)


def _refresh_persona_managers(web_app: Any, log: Any) -> None:
    """Invalidate the persona class cache and refresh all active persona managers."""
    try:
        from jupyter_ai_persona_manager.persona_manager import PersonaManager
    except ImportError:
        return

    # Reset the class-level entry-point cache so the next scan picks up new personas.
    PersonaManager._ep_persona_classes = None

    persona_managers = (
        web_app.settings.get("jupyter-ai", {}).get("persona-managers", {})
    )
    if not persona_managers:
        return

    import asyncio

    async def _refresh_all():
        for pm in list(persona_managers.values()):
            try:
                await pm.refresh_personas()
            except Exception:
                log.exception("jupyter_ai_manager: error refreshing persona manager")

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_refresh_all())
    except Exception:
        log.exception("jupyter_ai_manager: error scheduling persona refresh")


def setup_route_handlers(web_app: Any) -> None:
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    handlers = [
        (
            url_path_join(base_url, "jupyter-ai-manager", "extensions"),
            ExtensionsRouteHandler,
        ),
        (
            url_path_join(base_url, "jupyter-ai-manager", "acp-clients"),
            AcpClientsRouteHandler,
        ),
        (
            url_path_join(base_url, "jupyter-ai-manager", "acp-clients", "install"),
            AcpClientInstallRouteHandler,
        ),
        (
            url_path_join(base_url, "jupyter-ai-manager", "load"),
            LoadExtensionRouteHandler,
        ),
    ]
    web_app.add_handlers(host_pattern, handlers)
