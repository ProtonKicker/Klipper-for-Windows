"""Assemble the self-contained portable package for the installer.

Bundles everything a fresh Windows PC needs - no Python, Git, zig or
internet required at install time:
  app/       klipperforwindows package + patches (repair/doctor support)
  runtime/python/      embeddable Python 3.12 + all wheels + libsodium
  runtime/klipper/     patched Klipper checkout (c_helper prebuilt)
  runtime/moonraker/   patched Moonraker checkout
  runtime/web/         Mainsail + Fluidd
  runtime/refs.json    pins/shas for doctor
  <root>               the GUI publish output (Klipper for Windows.exe)

Usage: python scripts/build_portable.py <gui-publish-dir> <out-dir>
"""
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from klipperforwindows import paths  # noqa: E402
from klipperforwindows import versions as versions_mod  # noqa: E402

# the build machine may itself have a portable install laid down; the
# packager always packs the DEV layout (venv + git checkouts)
paths.PORTABLE = False
paths.KLIPPER = paths.APP_HOME / "klipper"
paths.MOONRAKER = paths.APP_HOME / "moonraker"
paths.VENV_DIR = paths.APP_HOME / "venv"
paths.VENV_PY = paths.VENV_DIR / "Scripts" / "python.exe"

EMBEDDED_PY_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
EXCLUDE_SITE = ("__editable__", "klipperforwindows-0.1.0.dist-info",
                "pip", "setuptools", "pkg_resources", "_distutils_hack",
                "distutils-precedence.pth", "wheel", "easy_install.py")


def copytree(src, dst, ignore=None):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*(ignore or [])),
                    dirs_exist_ok=True)


def git(args, cwd):
    return subprocess.run(["git", "-C", str(cwd)] + args,
                          capture_output=True, text=True).stdout.strip()


def main(publish_dir, out_dir):
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    app = out / "app"
    runtime = out / "runtime"

    print("1/7 klipperforwindows package + patches")
    copytree(REPO / "klipperforwindows", app / "klipperforwindows",
             ignore=("__pycache__", "*.pyc"))
    copytree(REPO / "patches", app / "patches")

    print("2/7 embeddable Python")
    py = runtime / "python"
    py.mkdir(parents=True)
    zip_path = Path("python-embed.zip")
    with urllib.request.urlopen(EMBEDDED_PY_URL, timeout=120) as r:
        zip_path.write_bytes(r.read())
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(py)
    zip_path.unlink()
    # enable site-packages relative to the exe; ._pth isolation ignores
    # PYTHONPATH and the script dir, so code dirs are listed explicitly
    # (relative to runtime\python)
    pth = py / "python312._pth"
    pth.write_text("python312.zip\n.\n..\\site-packages\n"
                   "..\\klipper\\klippy\n..\\moonraker\nimport site\n",
                   encoding="utf-8")
    # libnacl preloader looks next to the interpreter
    sodium = paths.VENV_DIR / "Scripts" / "libsodium.dll"
    if sodium.exists():
        shutil.copy2(sodium, py / "libsodium.dll")

    print("3/7 site-packages (all wheels, prebuilt)")
    sp_src = paths.VENV_DIR / "Lib" / "site-packages"
    sp_dst = runtime / "site-packages"
    sp_dst.mkdir(parents=True)
    for entry in sp_src.iterdir():
        if any(entry.name.startswith(x) for x in EXCLUDE_SITE):
            continue
        shutil.copy2(entry, sp_dst / entry.name) if entry.is_file() \
            else copytree(entry, sp_dst / entry.name)
    # the embeddable interpreter ignores PYTHONPATH
    # (._pth isolation), so the klipperforwindows package
    # itself ships inside site-packages
    copytree(REPO / "klipperforwindows",
             sp_dst / "klipperforwindows",
             ignore=("__pycache__", "*.pyc"))
    # always ship a fresh runtime shim (cffi CRT fallback etc.)
    from klipperforwindows.compat import SITECUSTOMIZE_SRC
    (sp_dst / "sitecustomize.py").write_text(SITECUSTOMIZE_SRC,
                                             encoding="utf-8")

    for comp, src in (("klipper", paths.KLIPPER),
                      ("moonraker", paths.MOONRAKER)):
        print(f"4-5/7 {comp} checkout (no .git, prebuilt artifacts)")
        copytree(src, runtime / comp, ignore=(".git", "__pycache__",
                                              "*.pyc", "klippy.log"))
    # pretty version for gitless installs
    if not (runtime / "klipper" / "klippy" / ".version").exists():
        desc = git(["describe", "--always", "--tags", "--long"], paths.KLIPPER)
        (runtime / "klipper" / "klippy" / ".version").write_text(
            desc or "?", encoding="utf-8")

    print("6/7 web UIs")
    copytree(paths.WEB_MAINSAIL, runtime / "web" / "mainsail")
    copytree(paths.WEB_FLUIDD, runtime / "web" / "fluidd")

    print("7/7 refs + GUI")
    sha_k = git(["rev-parse", "HEAD"], paths.KLIPPER)
    sha_m = git(["rev-parse", "HEAD"], paths.MOONRAKER)
    pins = versions_mod.load_pins()
    (runtime / "refs.json").write_text(json.dumps({
        "klipper": {"pin": pins["klipper"], "sha": sha_k},
        "moonraker": {"pin": pins["moonraker"], "sha": sha_m},
        "mainsail": {"pin": pins["mainsail"]},
        "fluidd": {"pin": pins["fluidd"]},
    }, indent=2), encoding="utf-8")
    copytree(Path(publish_dir), out, ignore=("*.pdb",))

    getting_started = "\n".join([
        "Klipper for Windows - portable build",
        "===================================",
        "",
        "1. Run 'Klipper for Windows.exe' (keep this folder in place - the",
        "   app manages services from here).",
        "2. First launch: press 'Run setup' on the Dashboard.",
        "   (one-time; fetches pinned upstream components - needs Python",
        "   3.10+, Git and zig on PATH: winget install zig.zig)",
        "3. Plug in your printer board, Auto-detect the serial port, Apply.",
        "4. Start the stack - the selected interface opens under Printer.",
        "",
        "Data folder: Documents\\Klipper for Windows",
        "CLI: bin\\klipperforwindows.cmd status",
    ])
    (out / "GETTING STARTED.txt").write_text(getting_started,
                                             encoding="utf-8")

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print("package: {} ({:.0f} MB)".format(out, size / 1e6))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
