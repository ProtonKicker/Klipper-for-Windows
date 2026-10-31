"""Process lifecycle for the Klipper stack on Windows.

  klipper -> moonraker -> web proxies (+ sleep guard)

Modeled on the Klipper for Mac supervisor, adapted for Windows:
  * Children get CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW and outlive
    the console/GUI that started them.
  * Process identity is re-validated on every read (pid + cmdline marker)
    via psutil, so stale state files after crashes/reboots are tolerated.
  * Orphan reaping kills untracked leftovers that would squat the
    ports/serial and make fresh children die on bind.
  * The sleep guard keeps the system awake (SetThreadExecutionState) while
    the stack runs, like caffeinate does on the Mac.
"""
import json
import os
import subprocess
import time

import psutil

from . import compat, paths

SERVICES = ("web_mainsail", "web_fluidd", "moonraker", "klipper",
            "sleep_guard")
MARKERS = {
    "klipper": "klippy.py",
    "moonraker": "moonraker",
    "web_mainsail": "klipperforwindows.proxy {} ".format(paths.WEB_PORT),
    "web_fluidd": "klipperforwindows.proxy {} ".format(paths.FLUIDD_PORT),
    "sleep_guard": "klipperforwindows.keepawake",
}
_STOP_ORDER = ("web_mainsail", "web_fluidd", "moonraker", "klipper",
               "sleep_guard")
CREATE_FLAGS = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)


def _home_token():
    return str(paths.APP_HOME)


def _cmdline(proc):
    try:
        return " ".join(proc.cmdline() or [])
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


def _load():
    if not paths.STATE.exists():
        return None
    try:
        with open(paths.STATE) as f:
            return json.load(f)
    except Exception:
        return None


def _clear():
    try:
        paths.STATE.unlink()
    except OSError:
        pass


def _save(procs):
    paths.RUN.mkdir(parents=True, exist_ok=True)
    data = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "boot_id": _boot_id()}
    for name, proc in procs.items():
        data[name] = proc.pid
    with open(paths.STATE, "w") as f:
        json.dump(data, f, indent=2)


def _boot_id():
    try:
        import platform
        # int(): boot_time is computed from wallclock-minus-uptime and
        # drifts by microseconds between calls; quantize for stability
        return platform.system() + "-" + str(int(psutil.boot_time()))
    except Exception:
        return "?"


def _live_cmd(pids):
    """pid -> command for the given pids, dropping dead/zombie entries."""
    result = {}
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                result[pid] = _cmdline(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result


def running():
    """{name: bool} from persisted state, or None if not started at all."""
    state = _load()
    if state is None:
        return None
    if state.get("boot_id") != _boot_id():
        _clear()
        return None
    pids = {name: state.get(name) for name in SERVICES}
    live = _live_cmd([p for p in pids.values() if p])
    return {name: bool(pids.get(name)) and
            MARKERS[name] in live.get(pids[name], "")
            for name in SERVICES}


def _popen(cmd, **kw):
    defaults = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=CREATE_FLAGS,
                    cwd=str(paths.APP_HOME), env=compat.build_env(),
                    close_fds=True)
    defaults.update(kw)
    return subprocess.Popen(cmd, **defaults)


def _scan_service_pids():
    """Pids of running service processes, tracked or not.  A process counts
    as ours when its marker matches AND its command line references our app
    home or data folder (guards against killing unrelated tools)."""
    mine = os.getpid()
    home_token = _home_token()
    data_token = str(paths.DATA)
    out = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.info["pid"] == mine:
                continue
            cmd = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied,
                psutil.ZombieProcess):
            continue
        if home_token not in cmd and data_token not in cmd:
            continue
        for name, marker in MARKERS.items():
            if marker in cmd:
                out.append((proc.info["pid"], name, cmd))
                break
    return out


def _reap_orphans():
    """Kill service processes not tracked by a live state file (crash,
    reboot, or stale state from a previous stack)."""
    state = _load()
    tracked = set()
    if state:
        tracked = {state.get(n) for n in SERVICES if state.get(n)}
    pids = [pid for pid, name, cmd in _scan_service_pids()
            if pid not in tracked]
    for pid in pids:
        _terminate(pid)
    if pids:
        deadline = time.time() + 4.0
        live = set(pids)
        while live and time.time() < deadline:
            time.sleep(0.2)
            live = {p for p in live if p in _live_cmd(live)}
        for pid in live:
            _kill(pid)


def _terminate(pid):
    try:
        psutil.Process(pid).terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def _kill(pid):
    try:
        psutil.Process(pid).kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def start():
    state = running()
    if state is not None:
        if any(state.values()):
            return False
        _clear()  # crashed/stale: self-heal, then start fresh
    paths.ensure_dirs()
    _reap_orphans()

    py = str(paths.VENV_PY)
    klipper_klippy = paths.KLIPPER / "klippy"
    env = compat.chelper_env()

    kproc = _popen(
        [py, str(klipper_klippy / "klippy.py"),
         "-a", "{}:{}".format(paths.KLIPPY_API_HOST, paths.KLIPPY_API_PORT),
         "-l", str(paths.KLIPPY_LOG),
         str(paths.PRINTER_CFG)],
        cwd=str(klipper_klippy), env=env,
    )
    mproc = _popen(
        [py, "-m", "moonraker",
         "-d", str(paths.DATA), "-c", str(paths.MOONRAKER_CONF),
         "-l", str(paths.MOONRAKER_LOG)],
        cwd=str(paths.MOONRAKER), env=env,
    )
    repo_root = str(paths.REPO_ROOT)
    wproc = _popen(
        [py, "-m", "klipperforwindows.proxy", str(paths.WEB_PORT),
         str(paths.WEB_MAINSAIL), str(paths.MOONRAKER_PORT),
         "0.0.0.0" if paths.lan_enabled() else "127.0.0.1"],
        cwd=repo_root,
        env={**compat.build_env(),
             "PYTHONPATH": repo_root + os.pathsep +
                           os.environ.get("PYTHONPATH", "")},
    )
    fproc = _popen(
        [py, "-m", "klipperforwindows.proxy", str(paths.FLUIDD_PORT),
         str(paths.WEB_FLUIDD), str(paths.MOONRAKER_PORT),
         "0.0.0.0" if paths.lan_enabled() else "127.0.0.1"],
        cwd=repo_root,
        env={**compat.build_env(),
             "PYTHONPATH": repo_root + os.pathsep +
                           os.environ.get("PYTHONPATH", "")},
    )
    sproc = _popen([py, "-m", "klipperforwindows.keepawake"],
                   cwd=repo_root,
                   env={**compat.build_env(),
                        "PYTHONPATH": repo_root})

    procs = {"klipper": kproc, "moonraker": mproc, "web_mainsail": wproc,
             "web_fluidd": fproc, "sleep_guard": sproc}
    _save(procs)
    # Fail fast if a child died on startup (e.g. port already in use)
    time.sleep(3.0)
    dead = [n for n, p in procs.items() if p.poll() is not None]
    if dead:
        for n in dead:
            log = paths.KLIPPY_LOG if n == "klipper" else (
                paths.MOONRAKER_LOG if n == "moonraker" else None)
            hint = ""
            if log and log.exists():
                tail = log.read_text(encoding="utf-8", errors="replace") \
                    .splitlines()[-3:]
                hint = "\n".join(tail)
            print("[!] service '{}' exited immediately. {}".format(n, hint))
        _clear()
        return False
    return True


def stop(timeout=8.0):
    state = _load()
    if state is None:
        return False
    pids = [(n, state.get(n)) for n in _STOP_ORDER if state.get(n)]

    def _alive():
        live = _live_cmd([p for _, p in pids])
        return [p for _, p in pids if p in live and
                MARKERS[dict(pids)[p]] in live[p]]

    for _, pid in pids:
        _terminate(pid)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _alive():
            break
        time.sleep(0.2)
    stragglers = [(n, p) for n, p in pids if p in _live_cmd([p])]
    for _, p in stragglers:
        _kill(p)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not [p for _, p in stragglers if p in _live_cmd([p])]:
            break
        time.sleep(0.2)
    still = [n for n, p in stragglers if p in _live_cmd([p])]
    if still:
        print("[!] {} refused to die; leaving state file for inspection: {}"
              .format(", ".join(still), paths.STATE))
        return False
    _clear()
    return True


def kill_all():
    """Force-stop everything: tracked services plus strays."""
    targets = {}
    state = _load()
    if state:
        for name in SERVICES:
            if state.get(name):
                targets[state[name]] = name
    for pid, name, cmd in _scan_service_pids():
        targets.setdefault(pid, name)
    for pid in targets:
        _kill(pid)
    deadline = time.time() + 3.0
    live = set(targets)
    while live and time.time() < deadline:
        live = {p for p in live if p in _live_cmd(live)}
        if live:
            time.sleep(0.2)
    _clear()
    return sorted((name, pid) for pid, name in targets.items())


def klippy_api_status(timeout=2.0):
    """(connected, state, state_message) from Moonraker, or (False, ..)."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:{}/server/info".format(
                    paths.MOONRAKER_PORT), timeout=timeout) as r:
            d = json.loads(r.read())
        res = d.get("result", {})
        return (bool(res.get("klippy_connected")),
                res.get("klippy_state", "unknown"),
                res.get("state_message", ""))
    except Exception:
        return False, "offline", "Moonraker API not reachable"


def klippy_firmware_restart(timeout=5.0):
    """Send FIRMWARE_RESTART to recover an MCU left in shutdown state."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:{}/printer/firmware_restart".format(
                paths.MOONRAKER_PORT), method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False
