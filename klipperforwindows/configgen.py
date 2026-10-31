"""Generates the initial user-editable configs under the data folder."""
import re
import time

from . import paths

# Starter config = the upstream BTT SKR Pico example (the board this app
# was developed against), with the serial placeholder and the Moonraker-
# required extras appended. Users replace it with their printer's config.
STARTER_EXAMPLE = "generic-bigtreetech-skr-pico-v1.0.cfg"

HEADER = """\
# Klipper for Windows starter config, derived from upstream {example} on {date}.
# Replace this whole file with the printer.cfg for your machine if you have
# one (see https://github.com/Klipper3d/klipper/tree/master/config).
# Tip: `klipperforwindows serial` lists connected USB printer boards, and the
# app's Setup page can pick the port for you.

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
    src = paths.KLIPPER / "config" / STARTER_EXAMPLE
    if not src.exists():
        return None
    text = re.sub(r"serial: [^\n]*",
                  "serial: REPLACE_WITH_YOUR_PRINTER_PORT",
                  src.read_text(), count=1)
    extras = "" if "[virtual_sdcard]" in text else EXTRAS.format(
        gcodes_dir=str(paths.DATA / "gcodes").replace("\\", "/"))
    macros = "" if "[gcode_macro PAUSE]" in text else MACROS
    return HEADER.format(example=STARTER_EXAMPLE,
                         date=time.strftime("%Y-%m-%d")) + text + extras + macros


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
    if not paths.PRINTER_CFG.exists():
        text = starter_cfg_text()
        if text is None:
            raise SystemExit(
                "No starter example found in the Klipper checkout. Run "
                "'klipperforwindows setup' first, then again.")
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
