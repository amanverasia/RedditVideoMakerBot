"""
Make a usable `ffmpeg` and `ffprobe` available on PATH without requiring a
system-wide install.

IMPORTANT: this bot's final render uses the `drawtext` filter (for the fancy
thumbnail / overlay text). Many prebuilt static ffmpeg binaries DO NOT include
`drawtext`:
  - imageio-ffmpeg's bundled binary: no drawtext, and ships no ffprobe at all.
  - johnvansickle static builds: no drawtext (dropped libharfbuzz).
The BtbN FFmpeg-Builds *do* include drawtext, so we download those.

Import-and-call ensure_ffmpeg() as early as possible in startup.
"""

import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# BtbN FFmpeg-Builds (include the drawtext filter).
_BTBN_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"


def _has_drawtext(exe: str) -> bool:
    """Return True if the given ffmpeg binary exposes the drawtext filter."""
    import subprocess

    try:
        out = subprocess.run(
            [exe, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
        return " drawtext " in out
    except Exception:
        return False


def ensure_ffmpeg() -> bool:
    """Ensure `ffmpeg` (with drawtext) and `ffprobe` resolve on PATH.

    Returns True if both are available and ffmpeg supports drawtext.
    """
    bin_dir = Path(__file__).resolve().parent.parent / ".ffmpeg_bin"
    bin_dir.mkdir(exist_ok=True)

    # Put our local bin dir on PATH first so any binaries we provide win.
    if str(bin_dir) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}" + os.environ.get("PATH", "")

    local_ffmpeg = bin_dir / _exe_name("ffmpeg")
    local_ffprobe = bin_dir / _exe_name("ffprobe")

    # 1) If we already have a local ffmpeg with drawtext + ffprobe, we're done.
    if local_ffmpeg.exists() and local_ffprobe.exists() and _has_drawtext(str(local_ffmpeg)):
        return True

    # 2) If a system ffmpeg supports drawtext and ffprobe exists, use those.
    sys_ffmpeg = shutil.which("ffmpeg")
    sys_ffprobe = shutil.which("ffprobe")
    if sys_ffmpeg and sys_ffprobe and _has_drawtext(sys_ffmpeg):
        return True

    # 3) Otherwise download a BtbN static build that includes drawtext.
    if _download_btbn(bin_dir):
        if local_ffmpeg.exists() and _has_drawtext(str(local_ffmpeg)) and local_ffprobe.exists():
            return True

    # Final fallback: at least make *something* named ffmpeg/ffprobe available
    # (without drawtext) so non-render stages can still run.
    _fallback_imageio_ffmpeg(bin_dir)
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _exe_name(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


def _btbn_asset() -> str:
    """Pick the right BtbN release asset for this platform/arch."""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "ffmpeg-master-latest-linux64-gpl.tar.xz"
        if machine in ("aarch64", "arm64"):
            return "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
    elif system == "Windows":
        return "ffmpeg-master-latest-win64-gpl.zip"
    # macOS: BtbN doesn't publish mac builds; rely on system ffmpeg/brew.
    return ""


def _download_btbn(bin_dir: Path) -> bool:
    """Download BtbN ffmpeg+ffprobe (with drawtext) into bin_dir."""
    asset = _btbn_asset()
    if not asset:
        return False
    url = f"{_BTBN_BASE}/{asset}"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = os.path.join(tmp, asset)
            urllib.request.urlretrieve(url, archive)

            wanted = {_exe_name("ffmpeg"), _exe_name("ffprobe")}
            extracted = 0

            if asset.endswith(".zip"):
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.namelist():
                        base = os.path.basename(member)
                        if base in wanted:
                            with zf.open(member) as src, open(bin_dir / base, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            extracted += 1
            else:
                with tarfile.open(archive) as tf:
                    for member in tf.getmembers():
                        base = os.path.basename(member.name)
                        if member.isfile() and base in wanted:
                            member.name = base  # flatten path
                            tf.extract(member, path=str(bin_dir))
                            extracted += 1

            for name in wanted:
                p = bin_dir / name
                if p.exists():
                    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            return extracted >= 2
    except Exception:
        return False


def _fallback_imageio_ffmpeg(bin_dir: Path) -> None:
    """Last resort: expose imageio-ffmpeg's bundled binary (no drawtext)."""
    if (bin_dir / _exe_name("ffmpeg")).exists():
        return
    try:
        import imageio_ffmpeg

        src = imageio_ffmpeg.get_ffmpeg_exe()
        if src and os.path.exists(src):
            link = bin_dir / _exe_name("ffmpeg")
            try:
                os.symlink(src, link)
            except OSError:
                shutil.copy2(src, link)
            link.chmod(link.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass
