"""Windows compatibility plumbing: runtime shims, build env, compiler.

Upstream Klipper/Moonraker checkouts are never hand-edited; the Windows
layer consists of (a) .patch files applied by git apply at setup,
(b) a sitecustomize.py generated into the venv, (c) C compat headers on
the include path, and (d) zig cc as the C helper compiler.
"""
import os
import shutil
import subprocess
import urllib.request
import zipfile
import tempfile
from pathlib import Path

from . import paths

ZIG_SEARCH_DIRS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" /
    "Links",
]


def _winget_zig_candidates():
    """winget stores versioned zig binaries under Packages\\zig.zig_*."""
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / \
        "WinGet" / "Packages"
    if not base.is_dir():
        return []
    out = []
    for d in base.glob("zig.zig*"):
        out.extend(d.rglob("zig.exe"))
    return out

SITECUSTOMIZE_SRC = '''\
"""Klipper for Windows runtime shim (auto-imported by the venv's Python).

Windows Python lacks a few attributes that upstream Moonraker/Klipper
touch unconditionally:
- time.CLOCK_BOOTTIME / time.clock_gettime: proc_stats calls it for system
  uptime.  time.monotonic() is QueryPerformanceCounter on Windows, which
  counts from boot, so it doubles as CLOCK_BOOTTIME.
- socket.SOCK_NONBLOCK / SOCK_CLOEXEC: machine._find_public_ip() creates a
  UDP probe socket with these flags; they only make it nonblocking/close-
  on-exec and the probe never reads or writes, so defining them as 0 keeps
  behavior correct.
- socket.CMSG_LEN/CMSG_SPACE/SCM_RIGHTS + select.poll + fcntl/termios
  modules: imported by dbus_fast and inotify_simple at module load; never
  exercised on Windows (no DBus transport, file observer off).
- WindowsSelectorEventLoopPolicy: Moonraker's asyncio loop uses add_reader/
  add_writer, which the default ProactorEventLoop does not support.
Generated file; re-created by setup.
"""
import os

if os.name == "nt":
    import time
    if not hasattr(time, "CLOCK_MONOTONIC"):
        time.CLOCK_MONOTONIC = 1
    if not hasattr(time, "CLOCK_BOOTTIME"):
        time.CLOCK_BOOTTIME = time.CLOCK_MONOTONIC
    if not hasattr(time, "clock_gettime"):
        def clock_gettime(clk_id):
            if clk_id in (time.CLOCK_MONOTONIC, time.CLOCK_BOOTTIME):
                return time.monotonic()
            raise OSError("unsupported clock id %r" % (clk_id,))
        time.clock_gettime = clock_gettime

    import socket
    for _flag, _name in ((0x800, "SOCK_CLOEXEC"), (0x4000, "SOCK_NONBLOCK")):
        if not hasattr(socket, _name):
            setattr(socket, _name, 0)

    # dbus_fast computes an ancillary-data buffer size at import time; the
    # fd-passing constants are never used on Windows (no DBus transport)
    if not hasattr(socket, "CMSG_LEN"):
        socket.CMSG_LEN = lambda length: length + 32
    if not hasattr(socket, "CMSG_SPACE"):
        socket.CMSG_SPACE = lambda length: length + 64
    if not hasattr(socket, "SCM_RIGHTS"):
        socket.SCM_RIGHTS = 0x01

    # inotify_simple needs Linux inotify (and imports select.poll, which
    # would trick klipper's reactor.py into picking its PollReactor) —
    # provide a stub module instead; moonraker's file_manager imports it
    # unconditionally but never uses it (file_system_observer: none)
    import sys as _sys
    import types as _types
    if "inotify_simple" not in _sys.modules:
        _ino = _types.ModuleType("inotify_simple")

        class _INotify:
            def __init__(self, *a, **k):
                raise OSError("inotify is not available on Windows")

        class _Event:
            mask = wd = name = 0

        class _Flags:
            # Real inotify flag values; never exercised on Windows
            CREATE = 0x100
            DELETE = 0x200
            MODIFY = 0x2
            MOVED_TO = 0x80
            MOVED_FROM = 0x40
            ONLYDIR = 0x1000000
            CLOSE_WRITE = 0x8
            IGNORED = 0x8000
            ISDIR = 0x40000000

            @staticmethod
            def from_mask(mask):
                out = []
                for name in ("CREATE", "DELETE", "MODIFY", "MOVED_TO",
                             "MOVED_FROM", "ONLYDIR", "CLOSE_WRITE",
                             "IGNORED", "ISDIR"):
                    bit = getattr(_Flags, name)
                    if mask & bit:
                        out.append(bit)
                return out

        _ino.INotify = _INotify
        _ino.Event = _Event
        _ino.flags = _Flags
        _ino.read_mask = lambda x: x
        _sys.modules["inotify_simple"] = _ino
    if "termios" not in _sys.modules:
        _termios = _types.ModuleType("termios")
        _termios.FIONREAD = 1
        _sys.modules["termios"] = _termios
    if "fcntl" not in _sys.modules:
        _fcntl = _types.ModuleType("fcntl")
        _fcntl.ioctl = lambda *a, **k: 0
        _fcntl.fcntl = lambda *a, **k: 0
        _sys.modules["fcntl"] = _fcntl

    # Preload libsodium next to python.exe so libnacl's LoadLibrary by
    # bare name resolves against the already-loaded module
    import ctypes
    _sodium = os.path.join(os.path.dirname(_sys.executable), "libsodium.dll")
    if os.path.exists(_sodium):
        try:
            ctypes.WinDLL(_sodium)
        except OSError:
            pass

    # Klippy uses ffi_lib.free (and friends) as GC destructors for C
    # allocations; cffi resolves symbols with GetProcAddress, which only
    # sees the DLL's own exports - CRT symbols like free/malloc are not
    # exported by zig-built DLLs. Fall back to ucrtbase for them.
    try:
        import cffi.api as _cffi_api
        _orig_dlopen = _cffi_api.FFI.dlopen

        def _dlopen_with_crt(self, libname, flags=0):
            lib = _orig_dlopen(self, libname, flags)
            crt = ctypes.CDLL("ucrtbase.dll")

            class _Lib:
                def __getattr__(self, name):
                    try:
                        return getattr(lib, name)
                    except AttributeError:
                        return getattr(crt, name)

            return _Lib()

        _cffi_api.FFI.dlopen = _dlopen_with_crt
    except Exception:
        pass

    import asyncio
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
'''

LIBSODIUM_URL = ("https://github.com/jedisct1/libsodium/releases/download/"
                 "1.0.22-RELEASE/libsodium-1.0.22-msvc.zip")

_cache = {}


def find_zig():
    """Locate zig.exe (env, winget links/packages, PATH)."""
    if "zig" in _cache:
        return _cache["zig"]
    candidates = []
    env = os.environ.get("KLFW_ZIG")
    if env:
        candidates.append(Path(env))
    for d in ZIG_SEARCH_DIRS:
        candidates.append(d / "zig.exe")
    candidates.extend(_winget_zig_candidates())
    which = shutil.which("zig")
    if which:
        candidates.append(Path(which))
    for cand in candidates:
        if cand and cand.is_file():
            _cache["zig"] = str(cand)
            return str(cand)
    _cache["zig"] = None
    return None


def build_env():
    """Environment for klippy/moonraker/proxy children."""
    env = dict(os.environ)
    if paths.PORTABLE:
        # bundled interpreter + libsodium dir; the klipperforwindows package
        # and its patches live in app\, so children can always import it
        pydir = str(paths.VENV_DIR)
        env["PATH"] = pydir + os.pathsep + env.get("PATH", "")
        repo = str(paths.REPO_ROOT)
        env["PYTHONPATH"] = repo + (os.pathsep + env["PYTHONPATH"]
                                    if env.get("PYTHONPATH") else "")
    else:
        vbin = str(paths.VENV_DIR / "Scripts")
        env["PATH"] = vbin + os.pathsep + env.get("PATH", "")
    env.setdefault("KLFW_HOME", str(paths.APP_HOME))
    env.setdefault("KLFW_DATA", str(paths.DATA))
    return env


def chelper_env():
    """Env for anything that may (re)build klipper's c_helper."""
    env = build_env()
    zig = find_zig()
    if zig:
        # Forward slashes: cmd.exe's quote handling mangles embedded
        # quotes in the value, and the zig path never contains spaces.
        env["KLFW_CC"] = str(zig).replace("\\", "/") + " cc"
    env["KLFW_COMPAT_INCLUDE"] = str(paths.WINCOMPAT_INCLUDE)
    return env


def ensure_runtime_shims():
    """Write sitecustomize.py into the site-packages and install
    libsodium.dll next to the interpreter (layout-aware)."""
    if paths.PORTABLE:
        sp = paths.VENV_DIR.parent / "site-packages"
        dll_dir = paths.VENV_DIR
    else:
        sp = paths.VENV_DIR / "Lib" / "site-packages"
        dll_dir = paths.VENV_DIR / "Scripts"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / "sitecustomize.py").write_text(SITECUSTOMIZE_SRC, encoding="utf-8")
    dll = dll_dir / "libsodium.dll"
    if not dll.exists():
        _install_libsodium(dll)


def _install_libsodium(dest):
    tmp = Path(tempfile.mkstemp(suffix=".zip")[1])
    try:
        req = urllib.request.Request(LIBSODIUM_URL,
                                     headers={"User-Agent":
                                              "klipperforwindows"})
        with urllib.request.urlopen(req, timeout=120) as r, \
                open(tmp, "wb") as f:
            f.write(r.read())
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(tmp) as z:
                z.extractall(td)
            src = None
            for p in Path(td).rglob("libsodium.dll"):
                if "x64" in str(p) and "Release" in str(p):
                    src = p
                    break
            if src is None:
                raise RuntimeError("libsodium.dll not found in release zip")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def invalidate_stale_build():
    """Force a c_helper rebuild when the compiler or shims change."""
    for name in ("c_helper.so", "_temp_c_helper.so"):
        p = paths.KLIPPER / "klippy" / "chelper" / name
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                # the running stack has the library loaded; it will be
                # reused as-is (still a valid load check)
                pass


def test_chelper_build():
    """Compile + load c_helper exactly the way klippy will at first run."""
    invalidate_stale_build()
    script = (
        "import sys; sys.path.insert(0, {klippy!r}); "
        "import chelper; chelper.get_ffi(); print('c_helper OK')"
    ).format(klippy=str(paths.KLIPPER / "klippy"))
    res = subprocess.run([str(paths.VENV_PY), "-c", script],
                         env=chelper_env(), capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("c_helper build FAILED:\n" + res.stderr[-2000:])
    return True
