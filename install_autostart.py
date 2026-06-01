"""
install_autostart.py — Creates a Windows Startup shortcut for Aura.

Run once from the project root after 'uv sync':
    uv run python install_autostart.py

The shortcut points directly to .venv\\Scripts\\pythonw.exe (the Windows
GUI-subsystem Python interpreter) so no console window ever appears on boot.
uv is intentionally bypassed — 'uv run' would spawn python.exe (console
subsystem) as a grandchild process that WindowStyle=7 cannot suppress.

Before creating the new shortcut this script removes ALL legacy startup
entries for this project:
  - Any .lnk file in the Startup folder whose TargetPath or WorkingDirectory
    is inside the project root (catches old entries regardless of their name).
  - The HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Aura registry
    value, if present (from even older autostart implementations).

Requires pywin32 (Windows only):
    uv pip install pywin32
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_subpath(path: Path, parent: Path) -> bool:
    """Return True if *path* is inside *parent* (or is *parent* itself)."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _cleanup_legacy_startup_entries(
    startup_dir: Path,
    project_root: Path,
    shell: object,
) -> None:
    """Delete any .lnk files in *startup_dir* that target this project.

    A shortcut is considered ours when ANY ONE of these conditions is true:

    1. ``TargetPath`` is inside the project root (catches console-script .exe
       shortcuts like ``.venv\\Scripts\\aura.exe``).
    2. ``WorkingDirectory`` equals the project root (catches ``uv run aura`` or
       ``python -m aura.main`` shortcuts regardless of interpreter location).
    3. ``Arguments`` contains ``"aura"`` (case-insensitive, catches shortcuts
       whose interpreter lives outside the project root *and* whose
       WorkingDirectory was left empty, e.g. an old ``uv.exe run aura`` entry
       where uv is installed in ``%LOCALAPPDATA%``).

    All three checks are needed because legacy entries were created with varying
    interpreter paths, working directories, and shortcut filenames.
    """
    for lnk in startup_dir.glob("*.lnk"):
        try:
            sc = shell.CreateShortCut(str(lnk))  # type: ignore[attr-defined]
            target_str: str = sc.TargetPath or ""
            workdir_str: str = sc.WorkingDirectory or ""
            args_str: str = sc.Arguments or ""

            target = Path(target_str).resolve() if target_str else None
            workdir = Path(workdir_str).resolve() if workdir_str else None

            is_ours = (
                (target and _is_subpath(target, project_root))
                or (workdir and workdir == project_root)
                or "aura" in args_str.lower()
            )

            if is_ours:
                lnk.unlink(missing_ok=True)
                print(f"🧹 Removed legacy startup shortcut: {lnk.name}")
        except Exception:
            pass  # skip unreadable or locked shortcuts silently


def _cleanup_registry_run_key() -> None:
    """Remove HKCU\\...\\Run\\Aura if it exists (legacy registry-based autostart)."""
    import winreg  # stdlib on Windows; import is deferred so Linux imports succeed

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as reg_key:
            try:
                winreg.DeleteValue(reg_key, "Aura")
                print("🧹 Removed legacy registry Run key: HKCU\\...\\Run\\Aura")
            except FileNotFoundError:
                pass  # value doesn't exist — nothing to do
    except OSError:
        pass  # can't open the key — skip silently


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if sys.platform != "win32":
        print("ERROR: This script is for Windows only.")
        sys.exit(1)

    try:
        import win32com.client  # type: ignore[import]
    except ImportError:
        print(
            "ERROR: pywin32 is required to create Windows shortcuts.\n"
            "Install it with:\n"
            "    uv pip install pywin32"
        )
        sys.exit(1)

    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("ERROR: %APPDATA% environment variable is not set.")
        sys.exit(1)

    startup_dir = (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    if not startup_dir.is_dir():
        print(f"ERROR: Startup folder not found: {startup_dir}")
        sys.exit(1)

    project_root = Path(__file__).parent.resolve()
    pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"

    if not pythonw.exists():
        print(
            "ERROR: .venv\\Scripts\\pythonw.exe not found.\n"
            "Run 'uv sync' first to create the virtual environment."
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 1 — remove all legacy startup entries for this project
    # ------------------------------------------------------------------
    shell = win32com.client.Dispatch("WScript.Shell")
    _cleanup_legacy_startup_entries(startup_dir, project_root, shell)
    _cleanup_registry_run_key()

    # ------------------------------------------------------------------
    # Step 2 — create the canonical silent shortcut
    # ------------------------------------------------------------------
    shortcut_path = startup_dir / "Aura.lnk"

    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(pythonw)
    shortcut.Arguments = "-m aura.main"
    shortcut.WorkingDirectory = str(project_root)
    shortcut.WindowStyle = 7  # SW_SHOWMINNOACTIVE — defense-in-depth
    shortcut.Description = "Aura — voice transcription (silent autostart)"
    shortcut.Save()

    print("✅ Aura autostart installed.")
    print(f"   Shortcut : {shortcut_path}")
    print(f"   Target   : {pythonw}")
    print("   Arguments: -m aura.main")
    print(f"   WorkDir  : {project_root}")
    print()
    print("To remove autostart, delete the shortcut:")
    print(f'   del "{shortcut_path}"')


if __name__ == "__main__":
    main()
