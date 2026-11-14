"""Build the program for this system with PyInstaller and pack it for download.

  python tools/build.py        -> dist/Stream-Scheduler-Windows.zip      (Stream Scheduler.exe in a folder)
                                  dist/Stream-Scheduler-macOS.zip        (Stream Scheduler.app)
                                  dist/Stream-Scheduler-Linux-x86_64.tar.gz

Needs: pip install -r requirements.txt -r requirements-build.txt. The release workflow runs this on
each system. The builds are not code-signed.
"""
import os
import platform
import shutil
import subprocess
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)
os.chdir(root)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

import paths  # noqa: E402
import ui  # noqa: E402

NAME = paths.APP_NAME
work = os.path.join(root, "build")
os.makedirs(work, exist_ok=True)


def picture(size):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    ui.draw_app_icon(p, size)
    p.end()
    return image


def icon():
    """The program's icon file, drawn by the same code as the icon in the window."""
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (painting text-free pictures needs one)
    if sys.platform == "win32":
        path = os.path.join(work, "icon.ico")
        if not picture(256).save(path, "ICO"):
            raise SystemExit("could not write icon.ico")
        return path
    if sys.platform == "darwin":
        folder = os.path.join(work, "icon.iconset")
        os.makedirs(folder, exist_ok=True)
        for size in (16, 32, 128, 256, 512):
            picture(size).save(os.path.join(folder, f"icon_{size}x{size}.png"))
            picture(size * 2).save(os.path.join(folder, f"icon_{size}x{size}@2x.png"))
        path = os.path.join(work, "icon.icns")
        subprocess.run(["iconutil", "-c", "icns", folder, "-o", path], check=True)
        return path
    return None


def main():
    shutil.rmtree(os.path.join(root, "dist"), ignore_errors=True)
    args = [sys.executable, "-m", "PyInstaller", "app.py", "--name", NAME, "--noconfirm", "--clean",
            "--windowed", "--workpath", work, "--specpath", work,
            # keyring finds its backends by their package data and by name: take them along
            "--copy-metadata", "keyring", "--collect-submodules", "keyring.backends",
            "--exclude-module", "tkinter"]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "com.leavenlabs.stream-scheduler"]
    made = icon()
    if made:
        args += ["--icon", made]
    subprocess.run(args, check=True)

    dist = os.path.join(root, "dist")
    if sys.platform == "win32":
        out = shutil.make_archive(os.path.join(dist, "Stream-Scheduler-Windows"), "zip", dist, NAME)
    elif sys.platform == "darwin":
        out = os.path.join(dist, "Stream-Scheduler-macOS.zip")   # ditto keeps the app's links and flags
        subprocess.run(["ditto", "-c", "-k", "--keepParent", os.path.join(dist, NAME + ".app"), out], check=True)
    else:
        shutil.copy(os.path.join(root, "assets", "icon.svg"), os.path.join(dist, NAME, "icon.svg"))
        out = shutil.make_archive(os.path.join(dist, f"Stream-Scheduler-Linux-{platform.machine()}"), "gztar",
                                  dist, NAME)
    print("built", out, f"({os.path.getsize(out) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
