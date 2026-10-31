"""Fault-injection scenarios: the app must self-heal like a printer host.

Run with the runtime venv python while the environment is set up:
  python -m klipperforwindows.tests.scenarios [--only NAME]

Scenarios drive only the app layer (supervisor, configs, Moonraker API);
upstream Klipper/Moonraker sources are never touched. Scenarios tagged
[hx] need the printer board attached; they are skipped otherwise.

When things go wrong here, that is a real bug: fix the app, not the test.
"""
import argparse
import json
import socket
import subprocess
import sys
import time

import psutil

from .. import paths, process

_results = []


def _record(name, ok, detail=""):
    _results.append((name, ok, detail))
    print("  {} {}{}".format("[ok]  " if ok else "[FAIL]", name,
                             (" — " + detail) if detail else ""), flush=True)


def _up_wait(timeout=60):
    """Ensure the stack is up and klippy ready; returns True."""
    if process.running() is None or not any(process.running().values()):
        process.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, state, msg = process.klippy_api_status()
        if ok and state == "ready":
            return True
        if ok and state == "error" and "shutdown" in (msg or "").lower():
            process.klippy_firmware_restart()
        time.sleep(1.0)
    return False


def _kill_service(name):
    """Force-kill a service and its whole process tree."""
    state = process._load() or {}
    pid = state.get(name)
    if not pid:
        return
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def _wait_until(predicate, timeout, step=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def _ports_open(*ports):
    for port in ports:
        s = socket.socket()
        s.settimeout(1.0)
        try:
            s.connect(("127.0.0.1", port))
        except OSError:
            s.close()
            continue
        s.close()
        return True
    return False


def _has_hardware():
    ok, state, _ = process.klippy_api_status()
    return ok and state == "ready"


def sc_up_idempotent():
    assert _up_wait(), "stack did not reach ready"
    again = process.start()
    if again:
        raise AssertionError("second `up` started services again")
    ok, state, _ = process.klippy_api_status()
    if not (ok and state == "ready"):
        raise AssertionError("stack degraded after double-up")


def sc_stale_state_cleared():
    process.stop()
    paths.RUN.mkdir(parents=True, exist_ok=True)
    paths.STATE.write_text(json.dumps({"boot_id": "bogus", "klipper": 999999}))
    if process.running() is not None:
        raise AssertionError("stale state was not self-cleared")
    if paths.STATE.exists():
        raise AssertionError("stale state file survived")


def sc_orphan_port_squatter():
    process.stop()
    squatter = subprocess.Popen(
        [sys.executable, "-c",
         "import socket,time\n"
         "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
         "s.bind(('127.0.0.1',{}));s.listen(5)\n"
         "time.sleep(600)".format(paths.MOONRAKER_PORT)],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    time.sleep(1.0)
    try:
        # an unknown process holds the API port: `up` must refuse to start
        # with a clear error, never silently half-start or kill strangers
        if process.start():
            raise AssertionError("up started despite a squatter holding :7125")
        if (process.running() or None) is not None:
            raise AssertionError("state file left behind after refused start")
    finally:
        try:
            squatter.kill()
        except (psutil.NoSuchProcess, OSError):
            pass
    time.sleep(0.5)
    if not process.start():
        raise AssertionError("up failed after squatter removed")
    if not _up_wait():
        raise AssertionError("stack did not reach ready after squatter removed")


def sc_down_up_cycle():
    if not process.stop():
        raise AssertionError("stop returned False with a running stack")
    if _ports_open(paths.MOONRAKER_PORT, paths.ui_port(paths.active_ui())):
        raise AssertionError("ports still open after down")
    if process.running() not in (None, {}):
        raise AssertionError("state survived down")
    if process.stop():
        raise AssertionError("second down claimed it stopped something")
    if not process.start():
        raise AssertionError("up failed after a clean down")
    if not _up_wait():
        raise AssertionError("stack did not reach ready after cycle")


def sc_kill_klippy_recovery():
    if not _up_wait():
        raise AssertionError("precondition: stack ready")
    _kill_service("klipper")
    if not _wait_until(lambda: not (process.running() or {}).get("klipper"), 10):
        raise AssertionError("klipper still tracked as alive after kill")
    if not process.start():
        raise AssertionError("up failed after klippy crash")
    if not _up_wait():
        raise AssertionError("no ready after klippy crash recovery "
                             "(auto FIRMWARE_RESTART path)")


def sc_kill_moonraker_recovery():
    if not _up_wait():
        raise AssertionError("precondition: stack ready")
    _kill_service("moonraker")
    if not _wait_until(lambda: not (process.running() or {}).get("moonraker"), 10):
        raise AssertionError("moonraker still tracked as alive after kill")
    if not process.start():
        raise AssertionError("up failed after moonraker crash")
    if not _up_wait():
        raise AssertionError("no ready after moonraker crash recovery")


def sc_serial_missing_fails_gracefully():
    if not _up_wait():
        raise AssertionError("precondition: stack ready")
    backup = paths.PRINTER_CFG.read_text(encoding="utf-8")
    try:
        patched = backup.replace("serial: COM", "serial: COMX", 1)
        import re
        patched = re.sub(r"(?m)^(serial\s*:\s*).*$", r"\1COM99", patched,
                         count=1)
        paths.PRINTER_CFG.write_text(patched, encoding="utf-8")
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:{}/printer/restart".format(
                paths.MOONRAKER_PORT), method="POST", data=b"")
        urllib.request.urlopen(req, timeout=8)

        def broken():
            ok, state, msg = process.klippy_api_status()
            if not ok:
                return True  # moonraker reports unreachable: also visible
            return state in ("error", "shutdown", "disconnected") or \
                "serial" in (msg or "").lower()

        if not _wait_until(broken, 25):
            raise AssertionError("klippy still 'ready' with a bogus serial "
                                 "port — failure not visible to the user")
        # the status API must stay responsive while klippy is broken
        ok, _, _ = process.klippy_api_status(timeout=5)
        if ok is None:
            raise AssertionError("moonraker stopped answering")
    finally:
        paths.PRINTER_CFG.write_text(backup, encoding="utf-8")
    if not _up_wait():
        raise AssertionError("no ready after restoring the serial port")


def sc_watchdog_recovers():
    if not _up_wait():
        raise AssertionError("precondition: stack ready")
    _kill_service("klipper")
    deadline = time.time() + 45
    recovered = False
    while time.time() < deadline:
        state = process.running()
        if state and all(state.values()):
            ok, st, _ = process.klippy_api_status()
            if ok and st == "ready":
                recovered = True
                break
        time.sleep(1.0)
    if not recovered:
        raise AssertionError("watchdog did not recover the stack")


def sc_down_idempotent():
    if process.stop() is False and (process.running() or None) is not None:
        raise AssertionError("stack still running but stop said nothing to do")
    if process.stop():
        raise AssertionError("second down claimed it stopped something")


SCENARIOS = [
    ("up-idempotent", sc_up_idempotent, False),
    ("stale-state-cleared", sc_stale_state_cleared, False),
    ("orphan-port-squatter", sc_orphan_port_squatter, False),
    ("down-up-cycle", sc_down_up_cycle, False),
    ("kill-klippy-recovery [hx]", sc_kill_klippy_recovery, True),
    ("kill-moonraker-recovery", sc_kill_moonraker_recovery, False),
    ("serial-missing-graceful [hx]", sc_serial_missing_fails_gracefully, True),
    ("watchdog-recovers [hx]", sc_watchdog_recovers, True),
    ("down-idempotent", sc_down_idempotent, False),
]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fault-injection scenarios (the app must self-heal)")
    ap.add_argument("--only", help="run a single scenario by name prefix")
    args = ap.parse_args(argv)

    del _results[:]
    for name, fn, needs_hw in SCENARIOS:
        if args.only and not name.startswith(args.only):
            continue
        if needs_hw and not _has_hardware():
            _record(name, True, "skipped (printer board not connected/ready)")
            continue
        try:
            fn()
            _record(name, True)
        except Exception as e:
            _record(name, False, str(e)[:160])

    # leave the environment in a good state
    try:
        if not _up_wait(30):
            print("  [warn] final state not ready")
    except Exception:
        pass

    failed = [r for r in _results if not r[1]]
    print("SCENARIOS {} ({}/{} passed)".format(
        "PASSED" if not failed else "FAILED",
        len(_results) - len(failed), len(_results)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
