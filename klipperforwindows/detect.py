"""USB serial device discovery on Windows (pyserial list_ports)."""
import re

# Klipper firmware's own CDC implementation uses the OpenMoko vendor id;
# RP2040 boards in boot/other firmware use Raspberry Pi's.
KLIPPER_VIDS = {0x1D50, 0x2E8A, 0x0483, 0x1A86, 0x10C4, 0x0403}


def lan_ip():
    """This PC's primary LAN IPv4 (UDP connect picks the routed interface;
    no packets are actually sent). None when offline."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _describe(port):
    if port.vid == 0x1D50 and port.pid == 0x614E:
        desc = "Klipper firmware (CDC)"
    elif port.vid == 0x2E8A:
        desc = "RP2040 board"
    else:
        desc = port.description or ""
    if port.vid:
        desc += "  [{}:{}]".format(port.vid, port.pid)
    return desc.strip()


def scan():
    """Returns [{'path': 'COM7', 'description': ...}] candidate printer
    ports: USB serial devices first, then anything else that looks serial."""
    import serial.tools.list_ports
    usb, other = [], []
    for p in serial.tools.list_ports.comports():
        entry = {"path": p.device, "description": _describe(p)}
        if p.vid:
            usb.append(entry)
        elif "bluetooth" not in (p.description or "").lower():
            other.append(entry)
    return usb + other


def guess_auto():
    """Best candidate for --auto: Klipper VID first, then any USB serial."""
    ports = scan()
    for p in ports:
        if "Klipper firmware" in p["description"]:
            return p["path"]
    return ports[0]["path"] if ports else None


def write_serial(cfg_path, device_path):
    """Set `serial:` inside the [mcu] section only. Adds the line if [mcu]
    exists without it; refuses (returns False) if no [mcu] section exists."""
    cfg_path = __import__("pathlib").Path(cfg_path)
    if not cfg_path.exists():
        return False
    lines = cfg_path.read_text(encoding="utf-8").splitlines(True)
    in_mcu = False
    has_mcu = False
    replaced = False
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_mcu = stripped == "[mcu]"
            has_mcu = has_mcu or in_mcu
        if in_mcu and re.match(r"serial\s*:", stripped):
            line = "serial: {}\n".format(device_path)
            in_mcu = False
            replaced = True
        out.append(line)
    if not replaced:
        if not has_mcu:
            return False
        out2 = []
        inserted = False
        for line in out:
            out2.append(line)
            if not inserted and line.strip() == "[mcu]":
                out2.append("serial: {}\n".format(device_path))
                inserted = True
        out = out2
    cfg_path.write_text("".join(out), encoding="utf-8")
    return True
