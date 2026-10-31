"""Fetches pinned upstream components, builds the venv, applies the Windows
compat patches, and verifies the C helper builds.

Pristine-upstream approach: checkouts live under %LOCALAPPDATA%\\
KlipperForWindows, the Windows layer lives entirely in (a) .patch files
applied with `git apply`, (b) a generated sitecustomize.py in the venv,
(c) compat C headers on the include path, and (d) zig cc as the compiler.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import compat, configgen, paths
from .versions import REPOS, load_pins, save_pins

MIN_PY = (3, 10)
URLS = {
    "klipper": "https://github.com/Klipper3d/klipper",
    "moonraker": "https://github.com/Arksine/moonraker",
}
DESTS = {"klipper": paths.KLIPPER, "moonraker": paths.MOONRAKER}
PATCHES = {"klipper": paths.KLIPPER_PATCH, "moonraker": paths.MOONRAKER_PATCH}
REFS = paths.APP_HOME / "refs.d"

GIT_EXCLUDE = ("c_helper.so", "_temp_c_helper.so*", "klippy.log",
               "__pycache__/")

# Combined requirements: klipper's pins minus jinja2/markupsafe (moonraker's
# newer jinja2 satisfies both - klipper 461c4e3 uses the stable API), plus
# psutil for process management on Windows.
KLIPPER_REQS = [
    "greenlet==3.3.2", "cffi==2.1.1", "pyserial==3.4",
    "python-can==3.3.4", "msgspec==0.19.0", "setuptools==78.1.1",
]
MOONRAKER_REQS = [
    "tornado>=6.2.0,<=6.5.8", "pillow>=9.5.0,<=12.3.0",
    "streaming-form-data>=1.11.0,<=2.1.0", "distro==1.9.0",
    "inotify-simple==2.0.1", "libnacl==2.1.0", "paho-mqtt==2.1.0",
    "zeroconf>=0.131.0,<=0.150.0", "preprocess-cancellation==0.2.1",
    "jinja2==3.1.6", "dbus-fast>=2.21.3,<=5.0.22",
    "apprise>=1.9.3,<=1.13.0", "ldap3==2.9.1",
    "python-periphery==2.4.1", "importlib_metadata>=6.7.0,<=9.0.0",
    "psutil>=5.9",
]


def _run(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def check_prereqs(strict=True):
    problems = []
    if find_python() is None:
        problems.append(
            "No Python >= {} found. Install from python.org (3.10+)".format(
                ".".join(map(str, MIN_PY))))
    if shutil.which("git") is None:
        problems.append("'git' not found. Install Git for Windows.")
    if compat.find_zig() is None:
        problems.append(
            "'zig' not found (used to compile Klipper's C helper). "
            "Install with: winget install zig.zig")
    if problems and strict:
        raise SystemExit("Klipper for Windows setup requires:\n  - " +
                         "\n  - ".join(problems))
    return problems


def find_python():
    env = os.environ.get("KLFW_PYTHON")
    candidates = ([env] if env else []) + [
        sys.executable, "python3.12", "python3.11", "python3.10", "python"]
    for c in candidates:
        if not c:
            continue
        exe = shutil.which(c) or (c if Path(c).is_file() else None)
        if not exe:
            continue
        try:
            out = _run([exe, "-c",
                        "import sys; print('%d.%d' % sys.version_info[:2])"])
            if out.returncode == 0 and \
                    tuple(int(x) for x in out.stdout.strip().split(".")) >= MIN_PY:
                out2 = _run([exe, "-c", "import sys; print(sys.executable)"])
                return out2.stdout.strip()
        except Exception:
            continue
    return None


def _ref_marker(component):
    REFS.mkdir(parents=True, exist_ok=True)
    return REFS / (component + ".ref")


def _head_sha(dest):
    try:
        return _run(["git", "-C", str(dest), "rev-parse",
                     "HEAD"]).stdout.strip()
    except Exception:
        return ""


def _exclude_build_artifacts(dest):
    excl = Path(dest) / ".git" / "info" / "exclude"
    try:
        excl.parent.mkdir(parents=True, exist_ok=True)
        existing = excl.read_text() if excl.exists() else ""
        missing = [p for p in GIT_EXCLUDE if p not in existing]
        if missing:
            with open(excl, "a") as f:
                f.write("\n".join(missing) + "\n")
    except OSError:
        pass


def checkout(component, ref, force=False):
    dest = DESTS[component]
    marker = _ref_marker(component)
    if not force and marker.exists() and marker.read_text().strip() == ref \
            and dest.exists():
        return _head_sha(dest)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    url = URLS[component]
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        _run(["git", "init", "--quiet", str(dest)], check=True)
        _run(["git", "-C", str(dest), "remote", "add", "origin", url],
             check=True)
        _run(["git", "-C", str(dest), "fetch", "--quiet", "--depth", "1",
              "origin", ref], check=True)
        _run(["git", "-C", str(dest), "checkout", "--quiet", "--detach",
              "FETCH_HEAD"], check=True)
    else:
        _run(["git", "clone", "--quiet", "--depth", "1", "--branch", ref,
              url, str(dest)], check=True)
    _exclude_build_artifacts(dest)
    marker.write_text(ref + "\n")
    return _head_sha(dest)


def apply_patch(component):
    """Apply the Windows compat patch; idempotent (skips when applied)."""
    dest = DESTS[component]
    patch = PATCHES[component]
    if not patch.exists():
        raise SystemExit("Missing patch file: {}".format(patch))
    probe = _run(["git", "-C", str(dest), "apply", "--check", str(patch)])
    if probe.returncode == 0:
        res = _run(["git", "-C", str(dest), "apply", str(patch)])
        if res.returncode != 0:
            raise SystemExit("git apply failed for {}:\n{}".format(
                component, res.stderr))
        return "applied"
    # Either already applied or conflicted: verify files exist
    if component == "klipper":
        probe_src = dest / "klippy" / "serialhdl.py"
        ok = "WinSerialBridge" in probe_src.read_text(encoding="utf-8")
    else:
        probe_src = dest / "moonraker" / "components" / "klippy_connection.py"
        ok = "klippy_tcp_address" in probe_src.read_text(encoding="utf-8")
    if ok:
        return "already-applied"
    raise SystemExit(
        "Patch does not apply to {} checkout and Windows markers are "
        "missing. Delete {} and re-run setup.".format(component, dest))


def create_venv():
    if not paths.VENV_PY.exists():
        py = find_python()
        if py is None:
            raise SystemExit("No suitable Python found (see setup error)")
        _run([py, "-m", "venv", str(paths.VENV_DIR)], check=True)
    compat.ensure_runtime_shims()


def install_requirements():
    pkgs = KLIPPER_REQS + MOONRAKER_REQS
    res = _run([str(paths.VENV_PY), "-m", "pip", "install", "--quiet",
                "--upgrade"] + pkgs)
    if res.returncode != 0:
        raise SystemExit("pip install failed:\n" + res.stderr[-2000:])


def test_libsodium():
    """Moonraker's auth component hard-requires libsodium (via libnacl)."""
    res = _run([str(paths.VENV_PY), "-c", "import libnacl"])
    return res.returncode == 0


def _download(url, dest_path, timeout=60, max_bytes=200 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "klipperforwindows"})
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            open(dest_path, "wb") as f:
        read = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            read += len(chunk)
            if read > max_bytes:
                raise SystemExit("Download exceeded size cap: " + url)
            f.write(chunk)


def _safe_extract(z, target):
    """Extract only entries that stay inside target (zip-slip guard)."""
    target = str(Path(target).resolve()) + os.sep
    for m in z.infolist():
        d = os.path.realpath(os.path.join(target, m.filename))
        if not d.startswith(target):
            raise SystemExit("Unsafe zip path: " + m.filename)
    z.extractall(target)


def fetch_webui(component, tag, dest):
    marker = _ref_marker(component)
    if marker.exists() and marker.read_text().strip() == tag and dest.exists():
        return
    asset_name = component + ".zip"
    url = "https://github.com/{}/releases/download/{}/{}".format(
        REPOS[component], tag, asset_name)
    zip_path = Path(tempfile.mkstemp(suffix=".zip")[1])
    try:
        _download(url, zip_path)
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(zip_path) as z:
                _safe_extract(z, td)
            root = None
            for p in Path(td).rglob("index.html"):
                root = p.parent
                break
            if root is None:
                raise SystemExit(asset_name + " missing index.html")
            stage = dest.parent / (dest.name + ".new")
            if stage.exists():
                shutil.rmtree(stage)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, stage)
            _patch_ui_config(component, stage)
            (stage / ".klipperforwindows-ref").write_text(tag + "\n")
            old = None
            if dest.exists():
                old = dest.parent / (dest.name + ".old")
                if old.exists():
                    shutil.rmtree(old)
                os.rename(dest, old)
            os.rename(stage, dest)
            if old is not None:
                shutil.rmtree(old, ignore_errors=True)
        marker.write_text(tag + "\n")
    finally:
        zip_path.unlink(missing_ok=True)


def _patch_ui_config(component, dest):
    """Point the UIs at their own proxied origin: the proxy relays REST +
    websocket to Moonraker on the same port, so defaults work."""
    cfg = dest / "config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return
    if component == "mainsail":
        data["hostname"] = None
        data["port"] = None
        data["defaultMode"] = "light"
    cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def setup(verbose=True):
    pins = load_pins()
    save_pins(pins)
    check_prereqs()
    if verbose:
        print("Fetching upstream components (pinned refs)...")
    for comp in ("klipper", "moonraker"):
        sha = checkout(comp, pins[comp])
        pins[comp + "_sha"] = sha
        state = apply_patch(comp)
        if verbose:
            print("  {} @ {} ({}) [windows patch: {}]".format(
                comp, pins[comp], sha[:8], state))
    save_pins(pins)
    if verbose:
        print("Building Python environment...")
    create_venv()
    install_requirements()
    if not test_libsodium():
        raise SystemExit("libsodium/libnacl check failed - Moonraker auth "
                         "will not start")
    compat.ensure_runtime_shims()
    fetch_webui("mainsail", pins["mainsail"], paths.WEB_MAINSAIL)
    fetch_webui("fluidd", pins["fluidd"], paths.WEB_FLUIDD)
    if verbose:
        print("  mainsail @ {}  fluidd @ {}".format(pins["mainsail"],
                                                    pins["fluidd"]))
    created = configgen.ensure_configs()
    for c in created:
        if verbose:
            print("  created {}".format(c))
    if verbose:
        print("Compiling Klipper C helper (zig cc)...")
    compat.test_chelper_build()
    if verbose:
        print("\nSetup complete. Next: connect your printer board, run "
              "`klipperforwindows serial --auto`, then `klipperforwindows up`.")
    return pins
