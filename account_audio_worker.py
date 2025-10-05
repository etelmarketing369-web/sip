#!/usr/bin/env python3
"""
Account Audio Worker
- Runs as a separate process per SIP account
- Sets its own console title so it shows as a unique app in Windows Volume Mixer
- Opens input and output streams for the specified devices (or defaults)
- Plays near-silent keepalive so the session stays visible even when idle
"""

import argparse
import ctypes
import sys
import time
import pyaudio
import struct
import os
import tempfile
import msvcrt


def set_console_title(title: str) -> bool:
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
        return True
    except Exception:
        return False


def set_mixer_display_name(display_name: str, retries: int = 10, delay: float = 0.3) -> bool:
    """Try to set the Windows audio session display name for this process using pycaw.
    Falls back silently if pycaw is unavailable or if session isn't found yet.
    """
    try:
        from pycaw.pycaw import AudioUtilities
    except Exception as e:
        # pycaw not installed
        print(f"[INFO] pycaw not available; Mixer will show Python executable name (ok): {e}")
        return False

    pid = os.getpid()
    for _ in range(retries):
        try:
            sessions = AudioUtilities.GetAllSessions()
            updated = False
            for s in sessions:
                try:
                    if s.Process and s.Process.pid == pid and hasattr(s, '_ctl') and s._ctl:
                        # SetDisplayName takes (LPCWSTR, LPCGUID) where context can be None
                        s._ctl.SetDisplayName(display_name, None)
                        updated = True
                except Exception:
                    # Ignore per-session errors and continue
                    pass
            if updated:
                print(f"[SUCCESS] Set Volume Mixer display name to: {display_name}")
                return True
        except Exception:
            # Enumerating sessions may fail until stream is active
            pass
        time.sleep(delay)
    print(f"⚠️  Could not set Mixer display name after retries; continuing")
    return False


def open_streams(account_name: str, input_id: int | None, output_id: int | None,
                 sample_rate: int = 8000, channels: int = 1, chunk: int = 160):
    pa = pyaudio.PyAudio()
    input_stream = None
    output_stream = None

    try:
    # Do NOT open input stream here to avoid creating extra Recording/Mixer entries.
    # The main SIP process handles real input during calls.

        # Output stream (required to appear in Volume Mixer)
        output_kwargs = dict(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            output=True,
            frames_per_buffer=chunk,
        )
        if output_id is not None and output_id >= 0:
            output_kwargs['output_device_index'] = output_id
        try:
            output_stream = pa.open(**output_kwargs)
        except Exception as e:
            # Fallback to 16000 Hz to improve device compatibility
            print(f"⚠️  [{account_name}] 8kHz output open failed ({e}); retrying at 16kHz")
            output_kwargs['rate'] = 16000
            try:
                output_stream = pa.open(**output_kwargs)
                sample_rate = 16000
                chunk = 320
            except Exception as e2:
                raise

        print(f"[SUCCESS] [{account_name}] Streams open (in={input_id if input_id is not None else 'default'}, "
              f"out={output_id if output_id is not None else 'default'})")

        return pa, input_stream, output_stream

    except Exception as e:
        print(f"[ERROR] [{account_name}] Failed to open streams: {e}")
        if input_stream:
            try: input_stream.close()
            except: pass
        if output_stream:
            try: output_stream.close()
            except: pass
        pa.terminate()
        return None, None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--account-id', type=int, required=True)
    parser.add_argument('--account-name', type=str, required=True)
    parser.add_argument('--input-id', type=int, default=-1)
    parser.add_argument('--output-id', type=int, default=-1)
    args = parser.parse_args()

    title = f"SIP Account {args.account_id} ({args.account_name})"
    set_console_title(title)
    print(f"[AUDIO] Worker started: {title}")

    # Acquire a single-instance guard per account (robust):
    # 1) Try a named Windows mutex (preferred)
    # 2) Fallback to a file lock using msvcrt on a fixed byte offset

    # Named mutex
    mutex_handle = None
    ERROR_ALREADY_EXISTS = 183
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        # Global namespace to ensure uniqueness across sessions
        mutex_name = f"Global\\SIPAccount_{args.account_id}"
        mutex_handle = kernel32.CreateMutexW(None, False, ctypes.c_wchar_p(mutex_name))
        last_err = ctypes.get_last_error()
        if not mutex_handle or last_err == ERROR_ALREADY_EXISTS:
            # Another instance already created the mutex
            print(f"[EXIT] Worker already running for account {args.account_id} (mutex); exiting")
            try:
                if mutex_handle:
                    kernel32.CloseHandle(mutex_handle)
            except Exception:
                pass
            return 0
    except Exception:
        mutex_handle = None

    # File lock fallback (ensure we lock the first byte consistently)
    lock_file_path = os.path.join(tempfile.gettempdir(), f"sip_account_{args.account_id}.lock")
    lock_fh = None
    try:
        lock_fh = open(lock_file_path, 'a+b')
        # Ensure file has at least 1 byte
        try:
            lock_fh.seek(0, os.SEEK_END)
            if lock_fh.tell() == 0:
                lock_fh.write(b"\0")
                lock_fh.flush()
        except Exception:
            pass
        # Lock the first byte
        try:
            lock_fh.seek(0)
            msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            # Another worker already holds the lock; exit quietly
            print(f"[EXIT] Worker already running for account {args.account_id} (file lock); exiting")
            try:
                lock_fh.close()
            except Exception:
                pass
            # Release mutex if we created it
            try:
                if mutex_handle:
                    try:
                        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                        kernel32.CloseHandle(mutex_handle)
                    except Exception:
                        pass
            except Exception:
                pass
            return 0
    except Exception:
        # If locking fails unexpectedly, continue; mutex should still protect us
        lock_fh = None

    input_id = None if args.input_id < 0 else args.input_id
    output_id = None if args.output_id < 0 else args.output_id

    pa, in_stream, out_stream = open_streams(args.account_name, input_id, output_id)
    if not pa or not out_stream:
        print(f"[ERROR] [{args.account_name}] No output stream; exiting")
        return 1

    # Attempt to set the Windows Volume Mixer session display name to the account title
    # Wait a brief moment to ensure the session exists, then try a few times
    try:
        time.sleep(0.25)
        set_mixer_display_name(title)
    except Exception:
        pass

    # Prepare keepalive buffer: use true digital silence (zeros) to avoid audible tones
    # Use standard 160 samples for 8kHz (20ms)
    chunk = 160
    keepalive = b"\x00\x00" * chunk

    try:
        while True:
            # Write tiny buffer to output to keep app visible in Volume Mixer
            try:
                out_stream.write(keepalive)
            except Exception:
                pass

            time.sleep(0.02)  # ~20ms pacing

    except KeyboardInterrupt:
        print(f"[STOP] [{args.account_name}] Worker stopping")
    finally:
        try:
            # No input stream opened
            if out_stream:
                try: out_stream.stop_stream(); out_stream.close()
                except: pass
        finally:
            pa.terminate()

    # Release lock on exit
    try:
        # Close named mutex handle if held
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            if 'mutex_handle' in locals() and mutex_handle:
                kernel32.CloseHandle(mutex_handle)
        except Exception:
            pass
        if lock_fh:
            try:
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            try:
                lock_fh.close()
            except Exception:
                pass
    except Exception:
        pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
