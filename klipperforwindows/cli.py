"""Command line interface for Klipper for Windows.

The GUI app wraps these same commands, so everything here is designed to
be scriptable (`status --json`, `serial --json`).
"""
import argparse
import json
import subprocess
import time
import webbrowser
from pathlib import Path

from . import __version__, compat, configgen, detect, paths, versions
# process.py needs psutil (installed into the venv by setup); import it
# lazily so `setup` itself can run from any Python
process = None


def _process():
    global process
    if process is None:
        from . import process as _p
        process = _p
    return process


def _say(msg):
    print(msg, flush=True)


def cmd_setup(args):
    pins = versions.load_pins()
    if args.update:
        updates, errors = versions.check_updates()
        for comp, pinned, latest in updates:
            _say("update: {} {} -> {}".format(comp, pinned, latest))
            pins[comp] = latest
        for e in errors:
            _say("[!] " + e)
    versions.save_pins(pins)
    from . import installer
    installer.setup(verbose=True)
    return 0


def cmd_up(args):
    proc = _process()
    configgen.ensure_configs()
    configgen.sync_data_paths()
    started = _process().start()
    if not started:
        _say("already running")
        return 0
    _say("starting klipper, moonraker, mainsail (:{}), fluidd (:{}) ..."
         .format(paths.WEB_PORT, paths.FLUIDD_PORT))
    deadline = time.time() + 45
    connected = False
    restarted = False
    while time.time() < deadline:
        ok, state, msg = proc.klippy_api_status()
        if ok and state == "ready":
            connected = True
            break
        # Self-heal: an MCU left in shutdown (crash/power loss) blocks
        # startup until FIRMWARE_RESTART - do it once, automatically
        if ok and not restarted and state == "error" and \
                "shutdown" in (msg or "").lower():
            _say("mcu in shutdown state - sending FIRMWARE_RESTART ...")
            proc.klippy_firmware_restart()
            restarted = True
        time.sleep(1.0)
    ok, state, _ = proc.klippy_api_status()
    _say("moonraker api : http://localhost:{} (klippy: {})".format(
        paths.MOONRAKER_PORT, state))
    _say("mainsail      : http://localhost:{}".format(paths.WEB_PORT))
    _say("fluidd        : http://localhost:{}".format(paths.FLUIDD_PORT))
    if not connected and ok is False:
        _say("[!] stack did not report ready within 45s - check "
             "`klipperforwindows logs`")
    if args.open:
        webbrowser.open(paths.ui_url(load_ui()))
    return 0


def load_ui():
    return paths.load_settings().get("ui", "mainsail")


def cmd_down(args):
    if _process().stop():
        _say("stopped")
        return 0
    _say("not running")
    return 0


def cmd_restart(args):
    _process().stop(timeout=6.0)
    time.sleep(0.5)
    args.open = getattr(args, "open", False)
    return cmd_up(args)


def cmd_restart_klipper(args):
    """Restart just the Klipper host (config reload) via Moonraker."""
    ok, state, msg = _process().klippy_api_status()
    if not ok:
        _say("moonraker not reachable - use `restart` for the full stack")
        return 1
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:{}/printer/restart".format(
                paths.MOONRAKER_PORT), method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=8) as r:
            _say("klipper host restart requested" if r.status == 200
                 else "restart failed (http {})".format(r.status))
    except Exception as e:
        _say("restart failed: {}".format(e))
        return 1
    return 0


def cmd_killall(args):
    killed = _process().kill_all()
    for name, pid in killed:
        _say("killed {} (pid {})".format(name, pid))
    _say("done" if killed else "nothing to kill")
    return 0


def cmd_status(args):
    proc = _process()
    state = proc.running() or {n: False for n in proc.SERVICES}
    ok, klippy_state, msg = proc.klippy_api_status()
    pins = versions.load_pins()
    serial = _current_serial()
    updates, errors = versions.check_updates()
    payload = {
        "version": __version__,
        "services": state,
        "klippy_connected": ok,
        "klippy_state": klippy_state,
        "state_message": msg,
        "pins": {k: pins[k] for k in
                 ("klipper", "moonraker", "mainsail", "fluidd")},
        "updates": [{"component": c, "pinned": pinned, "latest": latest}
                    for c, pinned, latest in updates],
        "update_errors": errors,
        "serial": serial,
        "data": str(paths.DATA),
        "app_home": str(paths.APP_HOME),
        "urls": {
            "mainsail": paths.ui_url("mainsail"),
            "fluidd": paths.ui_url("fluidd"),
            "api": "http://localhost:{}".format(paths.MOONRAKER_PORT),
        },
        "lan": paths.lan_enabled(),
        "lan_ip": detect.lan_ip(),
        "ui": load_ui(),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    def mark(ok):
        return "running" if ok else "stopped"
    _say("Klipper for Windows {}  ({})".format(__version__, "up" if any(
        state.values()) else "down"))
    for name in proc.SERVICES:
        _say("  {:<14} {}".format(name, mark(state.get(name))))
    _say("  klippy state  {}{}".format(
        klippy_state, "" if ok else " (moonraker unreachable)"))
    _say("  printer port  {}".format(serial or "not set"))
    if payload["updates"]:
        for u in payload["updates"]:
            _say("  update        {} {} -> {}".format(
                u["component"], u["pinned"], u["latest"]))
    _say("  mainsail      " + payload["urls"]["mainsail"])
    _say("  fluidd        " + payload["urls"]["fluidd"])
    _say("  data folder   " + str(paths.DATA))
    return 0


def _current_serial():
    if not paths.PRINTER_CFG.exists():
        return None
    import re
    text = paths.PRINTER_CFG.read_text(encoding="utf-8")
    m = re.search(r"(?m)^\s*serial\s*:\s*(.+)$", text)
    return m.group(1).strip() if m else None


def cmd_serial(args):
    ports = detect.scan()
    if args.json:
        print(json.dumps({"ports": ports, "current": _current_serial()}))
        return 0
    for p in ports:
        _say("  {:<8} {}".format(p["path"], p["description"]))
    if not ports:
        _say("  (no serial devices found)")
        return 0
    if args.auto or args.set:
        device = args.set or detect.guess_auto()
        if not device:
            _say("[!] nothing to auto-select")
            return 1
        if configgen.ensure_configs() or paths.PRINTER_CFG.exists():
            if detect.write_serial(paths.PRINTER_CFG, device):
                _say("printer.cfg [mcu] serial -> {}".format(device))
            else:
                _say("[!] no [mcu] section found in printer.cfg")
                return 1
    return 0


def cmd_lan(args):
    settings = paths.load_settings()
    if args.action in ("on", "off"):
        settings["lan"] = args.action == "on"
        paths.save_settings(settings)
        changed = configgen.apply_lan(settings["lan"])
        _say("lan {}{}".format(
            args.action, " (restart the stack to apply)" if changed else ""))
    else:
        _say("lan is {}".format("on" if paths.lan_enabled() else "off"))
        ip = detect.lan_ip()
        if ip and paths.lan_enabled():
            _say("  from other devices: http://{}:{}, :{} (api :{})".format(
                ip, paths.WEB_PORT, paths.FLUIDD_PORT, paths.MOONRAKER_PORT))
    return 0


def cmd_data(args):
    if args.set:
        target = Path(args.set).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.mkdir(parents=True, exist_ok=True)
        settings = paths.load_settings()
        settings["data"] = str(target)
        paths.save_settings(settings)
        _say("data folder set to {} (restart the stack to apply)".format(
            target))
        return 0
    _say(str(paths.DATA))
    return 0


def cmd_ui(args):
    if args.name in ("mainsail", "fluidd"):
        settings = paths.load_settings()
        settings["ui"] = args.name
        paths.save_settings(settings)
        _say("default interface: {}".format(args.name))
        return 0
    _say(load_ui())
    return 0


def cmd_open(args):
    webbrowser.open(paths.ui_url(args.ui))
    return 0


def cmd_logs(args):
    files = []
    if args.klipper or not args.moonraker:
        files.append(("klippy.log", paths.KLIPPY_LOG))
    if args.moonraker or not args.klipper:
        files.append(("moonraker.log", paths.MOONRAKER_LOG))
    for label, p in files:
        _say("=== {} ===".format(label))
        if p.exists():
            lines = p.read_text(encoding="utf-8", errors="replace") \
                      .splitlines()
            for line in lines[-args.tail:]:
                _say(line)
        else:
            _say("  (no log yet)")
    return 0


def cmd_doctor(args):
    problems = []
    oks = []
    from . import installer
    try:
        installer.check_prereqs()
        oks.append("prerequisites present (python/git/zig)")
    except SystemExit as e:
        problems.append(str(e))
    expected_modified = {
        "klipper": {
            "klippy/chelper/__init__.py", "klippy/extras/statistics.py",
            "klippy/gcode.py", "klippy/klippy.py", "klippy/reactor.py",
            "klippy/serialhdl.py", "klippy/util.py", "klippy/webhooks.py",
        },
        "moonraker": {
            "moonraker/components/klippy_connection.py",
            "moonraker/components/machine.py", "moonraker/components/extensions.py",
            "moonraker/server.py",
        },
    }
    for comp, dest in (("klipper", paths.KLIPPER),
                       ("moonraker", paths.MOONRAKER)):
        if (dest / ".git").exists():
            oks.append("{} checkout present @ {}".format(
                comp, _short_sha(dest)))
            # upstream purity guard: nothing may be modified beyond the
            # reviewed Windows compat patch (guards hand-edits and drift)
            out = subprocess.run(
                ["git", "-C", str(dest), "status", "--porcelain"],
                capture_output=True, text=True).stdout
            modified = {line[3:].strip() for line in out.splitlines()
                        if line[:2].strip() in ("M", "MM")}
            unexpected = modified - expected_modified.get(comp, set())
            if unexpected:
                problems.append(
                    "{} upstream drift (files changed outside the patch): {}"
                    .format(comp, ", ".join(sorted(unexpected))))
            else:
                oks.append("{} upstream clean (only windows patch files)"
                           .format(comp))
        else:
            problems.append("{} checkout missing - run setup".format(comp))
    if paths.VENV_PY.exists():
        oks.append("venv present")
        if compat.test_chelper_build():
            oks.append("c_helper compiles and loads")
    else:
        problems.append("venv missing - run setup")
    if compat.find_zig():
        oks.append("zig compiler found")
    else:
        problems.append("zig not found (winget install zig.zig)")
    if paths.WEB_MAINSAIL.exists() and paths.WEB_FLUIDD.exists():
        oks.append("mainsail + fluidd fetched")
    else:
        problems.append("web UIs missing - run setup")
    if paths.PRINTER_CFG.exists():
        oks.append("printer.cfg present (serial: {})".format(
            _current_serial()))
    else:
        problems.append("printer.cfg missing - run setup")
    if paths.MOONRAKER_CONF.exists():
        oks.append("moonraker.conf present")
    else:
        problems.append("moonraker.conf missing - run setup")
    if _process().klippy_api_status()[0]:
        oks.append("moonraker reachable, klippy connected")
    else:
        oks.append("stack not running (that is fine; try `up`)")
    for o in oks:
        _say("  [ok] " + o)
    for p in problems:
        _say("  [!!] " + p)
    return 1 if problems else 0


def _short_sha(dest):
    try:
        out = subprocess.run(["git", "-C", str(dest), "rev-parse", "--short",
                              "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() or "?"
    except Exception:
        return "?"


def cmd_selftest(args):
    from .tests import selftest
    return selftest.main(["--full"] if args.full else [])


def cmd_scenarios(args):
    from .tests import scenarios
    return scenarios.main(["--only", args.only] if args.only else [])


def build_parser():
    ap = argparse.ArgumentParser(
        prog="klipperforwindows",
        description="Run Klipper, Moonraker, Mainsail and Fluidd natively "
                    "on Windows (no VM).")
    ap.add_argument("--version", action="version",
                    version="klipperforwindows " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("setup", help="fetch components, build venv, verify")
    p.add_argument("--update", action="store_true",
                   help="move pins to the latest upstream tags first")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("up", help="start the stack")
    p.add_argument("--open", action="store_true",
                   help="open the web UI in the default browser")
    p.set_defaults(func=cmd_up)

    sub.add_parser("down", help="stop the stack").set_defaults(func=cmd_down)
    sub.add_parser("restart",
                   help="restart the stack").set_defaults(func=cmd_restart)
    sub.add_parser("restart-klipper", help="restart the Klipper host only"
                   ).set_defaults(func=cmd_restart_klipper)
    sub.add_parser("killall",
                   help="force-kill everything").set_defaults(func=cmd_killall)

    p = sub.add_parser("status", help="service state and versions")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("serial", help="list/set USB printer ports")
    p.add_argument("--auto", action="store_true",
                   help="pick the best candidate and write printer.cfg")
    p.add_argument("--set", metavar="PORT", help="write a specific port")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_serial)

    p = sub.add_parser("lan", help="reach the stack from other devices")
    p.add_argument("action", nargs="?", choices=("on", "off"))
    p.set_defaults(func=cmd_lan)

    p = sub.add_parser("data", help="show/move the data folder")
    p.add_argument("--set", metavar="PATH")
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("ui", help="show/set default web interface")
    p.add_argument("name", nargs="?", choices=("mainsail", "fluidd"))
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("open", help="open a web UI in the browser")
    p.add_argument("ui", nargs="?", choices=("mainsail", "fluidd"),
                   default="mainsail")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("logs", help="tail service logs")
    p.add_argument("--klipper", action="store_true")
    p.add_argument("--moonraker", action="store_true")
    p.add_argument("--tail", type=int, default=50)
    p.set_defaults(func=cmd_logs)

    sub.add_parser("doctor",
                   help="verify the installation").set_defaults(func=cmd_doctor)

    p = sub.add_parser("selftest",
                       help="live endpoint test (stack must be up)")
    p.add_argument("--full", action="store_true",
                   help="also run a real gcode round-trip")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("scenarios",
                       help="fault-injection robustness scenarios")
    p.add_argument("--only", help="run one scenario by name prefix")
    p.set_defaults(func=cmd_scenarios)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
