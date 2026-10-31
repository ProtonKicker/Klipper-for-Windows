"""Path layout for the Windows runtime and the user-visible data folder."""
import json
import os
from pathlib import Path


def _p(env, default):
    return Path(os.environ.get(env, default)).expanduser()


APP_HOME = _p("KLFW_HOME", str(Path(os.environ.get("LOCALAPPDATA",
                                                    "~/AppData/Local"))
                                / "KlipperForWindows"))

# User-visible data folder. Resolution order: env var, settings.json
# (written by `klipperforwindows data --set`), then the default.
SETTINGS = APP_HOME / "settings.json"


def _default_data():
    """Documents folder, honoring OneDrive Known Folder Move (where the
    real Documents lives under %OneDrive%\\Documents)."""
    profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    onedrive = os.environ.get("ONEDRIVE")
    if onedrive:
        candidate = Path(onedrive) / "Documents"
        if candidate.is_dir():
            return candidate / "Klipper for Windows"
    return profile / "Documents" / "Klipper for Windows"


DEFAULT_DATA = None  # computed via _default_data() at resolve time


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    APP_HOME.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(SETTINGS)


def _resolve_data():
    env = os.environ.get("KLFW_DATA")
    if env:
        return Path(env).expanduser()
    saved = load_settings().get("data")
    if saved:
        return Path(saved).expanduser()
    return _default_data()


WEB_PORT = int(os.environ.get("KLFW_WEB_PORT", "8080"))
FLUIDD_PORT = int(os.environ.get("KLFW_FLUIDD_PORT", "8081"))
MOONRAKER_PORT = int(os.environ.get("KLFW_MOONRAKER_PORT", "7125"))
# Klippy's API socket is TCP loopback on Windows (no unix sockets)
KLIPPY_API_HOST = "127.0.0.1"
KLIPPY_API_PORT = int(os.environ.get("KLFW_KLIPPY_API_PORT", "7126"))


def set_data(path):
    """Point all data-derived paths at a new folder (relocation-safe)."""
    global DATA, CONFIG, PRINTER_CFG, MOONRAKER_CONF, RUN, STATE
    global LOGS, WEB, WEB_MAINSAIL, WEB_FLUIDD, KLIPPY_LOG, MOONRAKER_LOG
    global KLIPPY_API
    DATA = Path(path).expanduser()
    CONFIG = DATA / "config"
    PRINTER_CFG = CONFIG / "printer.cfg"
    MOONRAKER_CONF = CONFIG / "moonraker.conf"
    RUN = DATA / "run"
    STATE = RUN / "state.json"
    LOGS = DATA / "logs"
    WEB = DATA / "web"
    WEB_MAINSAIL = WEB / "mainsail"
    WEB_FLUIDD = WEB / "fluidd"
    KLIPPY_LOG = LOGS / "klippy.log"
    MOONRAKER_LOG = LOGS / "moonraker.log"
    KLIPPY_API = (KLIPPY_API_HOST, KLIPPY_API_PORT)


set_data(_resolve_data())

KLIPPER = APP_HOME / "klipper"
MOONRAKER = APP_HOME / "moonraker"
VENV_DIR = APP_HOME / "venv"
VENV_PY = VENV_DIR / "Scripts" / "python.exe"
LOCKFILE = APP_HOME / "lockfile.json"
# Patch files applied on top of the pristine upstream checkouts
REPO_ROOT = Path(__file__).resolve().parent.parent
KLIPPER_PATCH = REPO_ROOT / "patches" / "klipper" / "klipper-windows-compat.patch"
MOONRAKER_PATCH = REPO_ROOT / "patches" / "moonraker" / "moonraker-windows-compat.patch"
WINCOMPAT_INCLUDE = REPO_ROOT / "patches" / "wincompat"


def lan_enabled():
    return bool(load_settings().get("lan"))


def ui_port(ui):
    return WEB_PORT if ui == "mainsail" else FLUIDD_PORT


def ui_url(ui):
    return "http://localhost:{}".format(ui_port(ui))


def web_url():
    ui = load_settings().get("ui", "mainsail")
    return ui_url("mainsail" if ui == "mainsail" else "fluidd")


def ensure_dirs():
    for d in (APP_HOME, DATA, CONFIG, RUN, LOGS, WEB, DATA / "gcodes",
              DATA / "database"):
        d.mkdir(parents=True, exist_ok=True)
