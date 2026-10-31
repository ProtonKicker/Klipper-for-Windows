"""Generates the initial user-editable configs under the data folder."""
import re
import shutil
import time

from . import paths

# Starter config: a bench-safe minimal config so the FIRST start reaches
# "ready" even on a bare board (a full printer example would shutdown
# immediately with "ADC out of range" on unconnected thermistor pins).
# The matching full board example is copied next to it as
# example-<board>.cfg for users to grow into; replace with your real
# printer config either way.
STARTER_EXAMPLE = "generic-bigtreetech-skr-pico-v1.0.cfg"

HEADER = """\
# Klipper for Windows starter config ({date}).
# This minimal config starts safely on a bare board (no motors/heaters
# attached). Replace it with your printer's real config when ready - a
# full example for the BTT SKR Pico is next to this file as
# example-skr-pico.cfg, and more are in the Klipper repo:
# https://github.com/Klipper3d/klipper/tree/master/config
# Tip: `klipperforwindows serial` lists connected USB printer boards, and the
# app's Setup page can pick the port for you.

"""

STARTER_BODY = """\
[mcu]
serial: REPLACE_WITH_YOUR_PRINTER_PORT
restart_method: command

[printer]
kinematics: none
max_velocity: 100
max_accel: 1000

[virtual_sdcard]
path: {gcodes_dir}

[pause_resume]

[display_status]

[idle_timeout]
timeout: 600

"""

EXTRAS = """
[virtual_sdcard]
path: {gcodes_dir}

[pause_resume]

[display_status]
"""

MACROS = """
# Standard print-control macros expected by Mainsail/Fluidd
[gcode_macro PAUSE]
description: Pause the current print
rename_existing: PAUSE_BASE
gcode:
    PAUSE_BASE

[gcode_macro RESUME]
description: Resume the paused print
rename_existing: RESUME_BASE
gcode:
    RESUME_BASE

[gcode_macro CANCEL_PRINT]
description: Cancel the current print
rename_existing: CANCEL_PRINT_BASE
gcode:
    CANCEL_PRINT_BASE
"""

MOONRAKER_CFG = """\
# Klipper for Windows generated Moonraker config (Windows-tuned).
# Loopback-only by default; use `klipperforwindows lan on` to reach the
# stack from other devices on your network.

[server]
host: {host}
port: {moonraker_port}
# Windows: Klippy's API server is a TCP loopback socket (no unix sockets)
klippy_tcp_address: {klippy_api}

[file_manager]
# Windows has no inotify; refresh lists on access
file_system_observer: none

[machine]
# systemd/DBus does not exist on Windows; the app manages processes
provider: none

[authorization]
cors_domains:
    http://localhost:{web_port}
    http://127.0.0.1:{web_port}
    http://localhost:{fluidd_port}
    http://127.0.0.1:{fluidd_port}
trusted_clients:
    127.0.0.1
    ::1

[announcements]

[history]
"""

# Written verbatim into [authorization].trusted_clients when LAN access is
# on; RFC1918 private ranges, so only a local network can talk to Moonraker.
LAN_CIDRS = ("192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12")


def apply_lan(enabled):
    """Sync the managed lines of an existing moonraker.conf with the LAN
    setting: [server] host + our CIDR entries in trusted_clients. Returns
    True when the file changed (Moonraker needs a restart)."""
    if not paths.MOONRAKER_CONF.exists():
        return False
    text = paths.MOONRAKER_CONF.read_text(encoding="utf-8")
    want_host = "0.0.0.0" if enabled else "127.0.0.1"
    updated = re.sub(r"(?m)^host: \S+.*$", "host: " + want_host,
                     text, count=1)

    def _repl(m):
        items = [ln for ln in m.group(0).splitlines()[1:] if ln.strip()]
        keep = [ln for ln in items if ln.strip() not in LAN_CIDRS]
        if enabled:
            keep += ["    " + c for c in LAN_CIDRS]
        return "trusted_clients:\n" + "\n".join(keep) + "\n"

    updated = re.sub(r"trusted_clients:\n(?:[ \t]+\S[^\n]*\n)*", _repl,
                     updated, count=1)
    if updated != text:
        paths.MOONRAKER_CONF.write_text(updated, encoding="utf-8")
        return True
    return False


def starter_cfg_text():
    text = STARTER_BODY.format(
        gcodes_dir=str(paths.DATA / "gcodes").replace("\\", "/"))
    return HEADER.format(date=time.strftime("%Y-%m-%d")) + text + MACROS


def copy_board_example():
    """Ship the full board example next to printer.cfg as a template."""
    src = paths.KLIPPER / "config" / STARTER_EXAMPLE
    dst = paths.CONFIG / "example-skr-pico.cfg"
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        return dst
    return None


def sync_virtual_sdcard():
    """Keep [virtual_sdcard] path pointing into the current data folder."""
    if not paths.PRINTER_CFG.exists():
        return False
    text = paths.PRINTER_CFG.read_text(encoding="utf-8")
    if "[virtual_sdcard]" not in text:
        return False
    desired = str(paths.DATA / "gcodes").replace("\\", "/")
    updated = re.sub(
        r"(\[virtual_sdcard\]\s*\n\s*path:\s*)[^\n]*",
        lambda m: m.group(1) + desired,
        text, count=1)
    if updated != text:
        paths.PRINTER_CFG.write_text(updated, encoding="utf-8")
        return True
    return False


def sync_moonraker_conf():
    """Keep moonraker.conf's klippy TCP address in sync."""
    if not paths.MOONRAKER_CONF.exists():
        return False
    text = paths.MOONRAKER_CONF.read_text(encoding="utf-8")
    desired = "{}:{}".format(paths.KLIPPY_API_HOST, paths.KLIPPY_API_PORT)
    updated, n = re.subn(
        r"(klippy_tcp_address:\s*)[^\n]*",
        lambda m: m.group(1) + desired,
        text)
    if n and updated != text:
        paths.MOONRAKER_CONF.write_text(updated, encoding="utf-8")
        return True
    return False


def sync_data_paths():
    changed = sync_virtual_sdcard()
    changed = sync_moonraker_conf() or changed
    return changed


def ensure_configs():
    paths.ensure_dirs()
    created = []
    example = copy_board_example()
    if example:
        created.append(example)
    if not paths.PRINTER_CFG.exists():
        text = starter_cfg_text()
        paths.PRINTER_CFG.write_text(text, encoding="utf-8")
        created.append(paths.PRINTER_CFG)
    if not paths.MOONRAKER_CONF.exists():
        paths.MOONRAKER_CONF.write_text(
            MOONRAKER_CFG.format(
                host="0.0.0.0" if paths.lan_enabled() else "127.0.0.1",
                moonraker_port=paths.MOONRAKER_PORT,
                klippy_api="{}:{}".format(paths.KLIPPY_API_HOST,
                                          paths.KLIPPY_API_PORT),
                web_port=paths.WEB_PORT,
                fluidd_port=paths.FLUIDD_PORT,
            ), encoding="utf-8")
        if paths.lan_enabled():
            apply_lan(True)
        created.append(paths.MOONRAKER_CONF)
    return created
