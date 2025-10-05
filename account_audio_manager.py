#!/usr/bin/env python3
"""
Account Audio Manager
- Spawns one worker process per SIP account
- Each worker shows as its own entry in Windows Volume Mixer with the account name
- Uses per-account input/output device IDs from ConfigManager
"""

import subprocess
import sys
import os
from typing import Dict, Optional
from config_manager import ConfigManager


class AccountAudioManager:
    def __init__(self, python_exe: Optional[str] = None):
        # Select Python executable and init state
        self.python_exe = python_exe or sys.executable
        self.processes = {}  # type: Dict[int, subprocess.Popen]
        self.config = ConfigManager()
        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        # Proactively clean up any orphaned workers from previous runs to avoid duplicate Mixer entries
        try:
            self.reap_orphans()
        except Exception:
            pass

    def reap_orphans(self) -> int:
        """Terminate any stray account_audio_worker.py processes from previous runs.
        Returns the number of processes terminated.
        """
        killed = 0
        try:
            # Use PowerShell to find python processes invoking account_audio_worker.py
            cmd = (
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'account_audio_worker.py' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $_ } catch {} } | Measure-Object | ForEach-Object { $_.Count }"
            )
            try:
                out = subprocess.check_output(cmd, cwd=self._base_dir, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                try:
                    killed = int(out.decode(errors='ignore').strip() or '0')
                except Exception:
                    killed = 0
            except subprocess.CalledProcessError:
                killed = 0
        except Exception:
            killed = 0
        if killed:
            print(f"🧹 Cleaned up {killed} orphan audio worker(s)")
        return killed

    def _kill_existing_worker_for_account(self, account_id: int) -> int:
        """Ensure no external worker is running for this account by scanning CommandLine args."""
        killed = 0
        try:
            ps_cmd = (
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -like 'python*' -and $_.CommandLine -match 'account_audio_worker.py' -and $_.CommandLine -match '--account-id {account_id}' }} | ForEach-Object {{ try {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $_ }} catch {{}} }} | Measure-Object | ForEach-Object {{ $_.Count }}"
            )
            try:
                out = subprocess.check_output(ps_cmd, cwd=self._base_dir, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                try:
                    killed = int(out.decode(errors='ignore').strip() or '0')
                except Exception:
                    killed = 0
            except subprocess.CalledProcessError:
                killed = 0
        except Exception:
            killed = 0
        if killed:
            print(f"🧹 Removed {killed} pre-existing worker(s) for account {account_id}")
        return killed

    def start_for_account(self, account_id: int, account_name: str) -> bool:
        # If already running, do nothing
        if account_id in self.processes:
            proc = self.processes.get(account_id)
            if proc and proc.poll() is None:
                return True

        # Kill any stray worker for this account (from prior app run) to prevent duplicates
        try:
            self._kill_existing_worker_for_account(account_id)
        except Exception:
            pass

        # Resolve device IDs (-1 means default)
        in_id, out_id = self.config.get_account_audio_devices(account_id)
        worker_path = os.path.join(self._base_dir, 'account_audio_worker.py')
        args = [
            self.python_exe,
            worker_path,
            '--account-id', str(account_id),
            '--account-name', str(account_name),
            '--input-id', str(in_id),
            '--output-id', str(out_id),
        ]
        try:
            # Start hidden (no console window). Separate processes still create distinct Mixer entries.
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            startupinfo = None
            try:
                # Further ensure hidden window on Windows
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, 'STARTF_USESHOWWINDOW', 0)
                startupinfo.wShowWindow = 0  # SW_HIDE
            except Exception:
                startupinfo = None

            proc = subprocess.Popen(
                args,
                creationflags=creationflags,
                cwd=self._base_dir,
                startupinfo=startupinfo,
            )
            self.processes[account_id] = proc
            print(f"▶️  Started audio worker for account {account_id} ({account_name}) PID={proc.pid}")
            return True
        except Exception as e:
            print(f"Failed to start audio worker for account {account_id}: {e}")
            return False

    def stop_for_account(self, account_id: int) -> bool:
        proc = self.processes.get(account_id)
        if not proc:
            # Try to kill any still-running worker by scanning command line
            try:
                self._kill_existing_worker_for_account(account_id)
            except Exception:
                pass
            return False
        try:
            # Attempt graceful terminate
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            # Fallback to PowerShell Stop-Process with -Force
            try:
                pid = proc.pid
                ps_cmd = (
                    "powershell", "-NoProfile", "-Command",
                    f"try {{ Stop-Process -Id {pid} -Force -ErrorAction Stop }} catch {{}}"
                )
                subprocess.run(ps_cmd, cwd=self._base_dir, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except Exception:
                pass
        finally:
            try:
                del self.processes[account_id]
            except Exception:
                pass
        return True

    def stop_all(self) -> None:
        for aid in list(self.processes.keys()):
            self.stop_for_account(aid)
        # As a final sweep, kill any stray workers
        try:
            self.reap_orphans()
        except Exception:
            pass


if __name__ == '__main__':
    print("This module is intended to be used by the SIP dialer.")
