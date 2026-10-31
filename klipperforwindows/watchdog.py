"""Stack watchdog: automatically recover from service crashes.

Runs as part of the stack (`up` starts it). Every few seconds it checks
the tracked services; any dead service is respawned in place — at most 5
recoveries per 30 minutes, persisted across watchdog replacements. After
a klippy respawn it also sends FIRMWARE_RESTART when the MCU reports
itself in shutdown (the usual aftermath of a crashed host). If the budget
is exhausted the watchdog gives up and logs; exiting when state.json
disappears means the user asked for `down`.
"""
import json
import time

from . import paths, process

CHECK_INTERVAL = 5
MAX_RECOVERIES = 5
WINDOW = 30 * 60.0

WATCHDOG_STATE = "watchdog.json"


def _state_path():
    return paths.RUN / WATCHDOG_STATE


def _recent_recoveries():
    try:
        stamps = json.loads(_state_path().read_text())
    except Exception:
        return []
    now = time.time()
    return [t for t in stamps if now - t < WINDOW]


def _record_recovery():
    stamps = _recent_recoveries()
    stamps.append(time.time())
    try:
        paths.RUN.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(json.dumps(stamps))
    except OSError:
        pass


def _log(msg):
    try:
        with open(paths.LOGS / "watchdog.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except OSError:
        pass


def _heal_mcu_shutdown():
    """After a klippy crash the MCU often reports shutdown; give Moonraker
    a moment, then send FIRMWARE_RESTART once."""
    deadline = time.time() + 15
    while time.time() < deadline:
        ok, state, msg = process.klippy_api_status()
        if ok:
            if state == "error" and "shutdown" in (msg or "").lower():
                _log("mcu in shutdown after recovery; FIRMWARE_RESTART")
                process.klippy_firmware_restart()
            return
        time.sleep(1.0)


def main():
    _log("watchdog started")
    while True:
        time.sleep(process.WATCHDOG_INTERVAL)
        try:
            state = process.running()
        except Exception as e:
            _log("status check failed: {!r}".format(e))
            continue
        if state is None:
            # state file gone: the user ran `down` — exit quietly
            _log("stack stopped by user; watchdog exiting")
            return
        if (paths.RUN / ".downing").exists():
            return  # a manual stop is in progress
        dead = sorted(n for n, alive in state.items()
                      if not alive and n != "watchdog")
        if not dead:
            continue
        recent = _recent_recoveries()
        if len(recent) >= MAX_RECOVERIES:
            _log("recovery budget exhausted ({} in {}s); giving up: {}".format(
                len(recent), int(WINDOW), ", ".join(dead)))
            return
        _record_recovery()
        _log("respawning dead services: {}".format(", ".join(dead)))
        if not process.respawn(dead):
            _log("respawn failed (see app output)")
            continue
        _log("recovered: {}".format(", ".join(dead)))
        if "klipper" in dead:
            _heal_mcu_shutdown()


if __name__ == "__main__":
    main()
