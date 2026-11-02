import importlib.metadata
import json
import os
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
            url_path_join(base_url, "jupyter-ai-manager", "load"),
            LoadExtensionRouteHandler,
        ),
    ]
    web_app.add_handlers(host_pattern, handlers)
