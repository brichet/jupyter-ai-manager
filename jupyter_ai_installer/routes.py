import importlib
import importlib.util
import json
import os
import sys
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
        "description": "Lightweight AI integration for JupyterLab",
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


def _is_installed(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


class ExtensionsRouteHandler(APIHandler):
    @tornado.web.authenticated
    def get(self):
        extensions = [
            {**ext, "installed": _is_installed(ext["import_name"])}
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

        # Evict stale cached modules so the newly installed package is picked up fresh.
        for key in list(sys.modules.keys()):
            if key == import_name or key.startswith(import_name + "."):
                del sys.modules[key]

        if not _is_installed(import_name):
            self.set_status(404)
            self.finish({"message": f"Package '{import_name}' is not installed"})
            return

        try:
            module = importlib.import_module(import_name)
        except ImportError as exc:
            self.set_status(500)
            self.finish({"message": f"Failed to import '{import_name}': {exc}"})
            return

        try:
            _register_server_extension(module, import_name, self.application, self.log)
        except Exception as exc:
            self.log.exception(f"jupyter_ai_installer: error registering '{import_name}'")
            self.set_status(500)
            self.finish({"message": f"Failed to register handlers for '{import_name}': {exc}"})
            return

        self.finish({"status": "ok"})


def _register_server_extension(
    module: Any, import_name: str, web_app: Any, log: Any
) -> None:
    # Prefer the real ServerApp so extensions get a fully-populated server object.
    server_app = web_app.settings.get("serverapp")
    if server_app is None:
        # Fallback: minimal wrapper covering the two attributes most extensions need.
        class _AppWrapper:
            pass
        _AppWrapper.web_app = web_app
        _AppWrapper.log = log
        server_app = _AppWrapper

    # Load the declared entry points of the specified module.
    _load_extension_points(module, import_name, server_app, log)

    # Also discover and load any other server extensions that are now configured
    # but not yet running — this picks up packages installed as dependencies
    # (e.g. jupyter_ai_router installed alongside jupyter-ai-lite).
    _load_new_configured_extensions(server_app, web_app, log)


def _load_module(module: Any, import_name: str, server_app: Any, log: Any) -> bool:
    """Load a server extension module, handling both legacy and ExtensionApp patterns.

    Returns True if at least one entry point was loaded.
    """
    if hasattr(module, "_jupyter_server_extension_points"):
        loaded = False
        for point in module._jupyter_server_extension_points():
            mod_name = point.get("module", import_name)
            app_class = point.get("app")
            try:
                if app_class is not None:
                    # ExtensionApp pattern: the classmethod is _load_jupyter_server_extension
                    # (with leading underscore — no public alias in jupyter_server 2.x).
                    if hasattr(app_class, "_load_jupyter_server_extension"):
                        app_class._load_jupyter_server_extension(server_app)
                        loaded = True
                else:
                    mod = importlib.import_module(mod_name)
                    if hasattr(mod, "_load_jupyter_server_extension"):
                        mod._load_jupyter_server_extension(server_app)
                        loaded = True
            except Exception as exc:
                log.warning(
                    f"jupyter_ai_installer: error loading extension point '{mod_name}': {exc}"
                )
        return loaded

    if hasattr(module, "_load_jupyter_server_extension"):
        module._load_jupyter_server_extension(server_app)
        return True

    return False


def _load_extension_points(
    module: Any, import_name: str, server_app: Any, log: Any
) -> None:
    if not _load_module(module, import_name, server_app, log):
        log.warning(
            f"jupyter_ai_installer: no server extension entry point found in '{import_name}'"
        )


def _load_new_configured_extensions(
    server_app: Any, web_app: Any, log: Any
) -> None:
    """Load server extensions that are configured on disk but not yet running.

    jupyter_server registers extensions by writing JSON files into
    jupyter_server_config.d/ at install time.  We replicate the same discovery
    here so that dependency packages (which install their own config files) are
    also picked up without a server restart.
    """
    from jupyter_core.paths import jupyter_config_path

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

    # Determine which extensions are truly running: only those whose ExtensionApp
    # instance was successfully created (app is not None in extension_points).
    # Using ext_manager.extensions would also include failed / not-yet-loaded ones.
    ext_manager = getattr(server_app, "extension_manager", None)
    already_loaded: set[str] = set()
    if ext_manager is not None:
        for name, point in getattr(ext_manager, "extension_points", {}).items():
            if getattr(point, "app", None) is not None:
                already_loaded.add(name)

    for ext_name, enabled in configured.items():
        if not enabled or ext_name in already_loaded:
            continue
        # Skip ourselves to avoid recursion.
        if ext_name == "jupyter_ai_installer":
            continue
        try:
            mod = importlib.import_module(ext_name)
            if _load_module(mod, ext_name, server_app, log):
                log.info(f"jupyter_ai_installer: dynamically loaded '{ext_name}'")
        except Exception as exc:
            log.warning(
                f"jupyter_ai_installer: could not load '{ext_name}': {exc}"
            )


def setup_route_handlers(web_app: Any) -> None:
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    handlers = [
        (
            url_path_join(base_url, "jupyter-ai-installer", "extensions"),
            ExtensionsRouteHandler,
        ),
        (
            url_path_join(base_url, "jupyter-ai-installer", "load"),
            LoadExtensionRouteHandler,
        ),
    ]
    web_app.add_handlers(host_pattern, handlers)
