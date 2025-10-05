import subprocess
import threading
import time
from typing import Callable, Dict, Optional, Tuple

class WhatsAppCallMonitor:
    """Polls Android emulator notifications to detect active WhatsApp voice call state.

    Strategy:
    - Uses `adb -s emulator-<port> shell dumpsys notification` to read active notifications.
    - Searches for package `com.whatsapp` and key phrases like 'Ongoing voice call', 'WhatsApp voice call', or 'Incoming voice call'.
    - Provides callbacks for state changes per account/emulator.
    - Lightweight polling with backoff.
    """

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = poll_interval
        self._threads: Dict[int, threading.Thread] = {}
        self._stop_flags: Dict[int, threading.Event] = {}
        self._last_state: Dict[int, str] = {}
        self._on_state_change: Optional[Callable[[int, str, Optional[str]], None]] = None
        self._lock = threading.Lock()
        # Enable debug prints (can be toggled externally if needed)
        self.debug = True

    def set_callback(self, cb: Callable[[int, str, Optional[str]], None]):
        self._on_state_change = cb

    def start_monitoring(self, account_id: int, emulator_port: int):
        if account_id in self._threads:
            return
        stop_event = threading.Event()
        self._stop_flags[account_id] = stop_event

        def loop():
            device_id = f"emulator-{emulator_port}"
            while not stop_event.is_set():
                try:
                    # Use --noredact to avoid masked notification text on newer Android builds
                    proc = subprocess.run([
                        'adb', '-s', device_id, 'shell', 'dumpsys', 'notification', '--noredact'
                    ], capture_output=True, text=True, timeout=8)
                    if proc.returncode == 0:
                        text = proc.stdout
                        # Rate-limited debug logging per account
                        if self.debug:
                            now = time.time()
                            last_key = f"dbg_last_{account_id}"
                            last = getattr(self, last_key, 0)
                            if now - last > 15:  # every 15s per account (reduced spam)
                                snippet = '\n'.join(text.splitlines()[:25])
                                print(f"[WA DBG] A{account_id} notif snippet (first 25 lines):\n{snippet}\n---")
                                setattr(self, last_key, now)
                        state, number = self._parse_state(text)
                        with self._lock:
                            prev = self._last_state.get(account_id)
                            if state != prev:
                                self._last_state[account_id] = state
                                if self.debug:
                                    print(f"[WA STATE] A{account_id}: {prev} -> {state} (number: {number})")
                                if self._on_state_change:
                                    try:
                                        self._on_state_change(account_id, state, number)
                                    except Exception as e:
                                        print(f"[WA CALLBACK] Error: {e}")
                            elif self.debug and state == 'CONNECTED' and account_id == 2:
                                # Still log CONNECTED states for account 2 only (main test account)
                                print(f"[WA STATE] A{account_id}: still {state} (number: {number})")
                    else:
                        # adb error - mark unknown
                        with self._lock:
                            if self._last_state.get(account_id) != 'UNKNOWN':
                                self._last_state[account_id] = 'UNKNOWN'
                                if self.debug:
                                    print(f"[WA STATE] A{account_id}: -> UNKNOWN (adb error)")
                                if self._on_state_change:
                                    self._on_state_change(account_id, 'UNKNOWN', None)
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                time.sleep(self.poll_interval)

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        self._threads[account_id] = t

    def stop_monitoring(self, account_id: int):
        ev = self._stop_flags.get(account_id)
        if ev:
            ev.set()
        self._threads.pop(account_id, None)
        self._stop_flags.pop(account_id, None)
        self._last_state.pop(account_id, None)

    def stop_all(self):
        for ev in list(self._stop_flags.values()):
            ev.set()
        self._threads.clear()
        self._stop_flags.clear()
        self._last_state.clear()

    def _parse_state(self, dump: str) -> Tuple[str, Optional[str]]:
        if 'com.whatsapp' not in dump:
            return ('IDLE', None)
        
        # Check if WhatsApp call notification exists (category=call)
        whatsapp_call_found = False
        whatsapp_number = None
        
        for line in dump.splitlines():
            if 'pkg=com.whatsapp' in line and 'category=call' in line:
                whatsapp_call_found = True
                if self.debug:
                    print(f"[WA STRUCT] Found category=call: {line[:80]}...")
                break
        
        if not whatsapp_call_found:
            # No WhatsApp call activity found - return IDLE with current timestamp as number
            import time
            current_time = str(int(time.time() * 1000))  # milliseconds like the notification timestamps
            return ('IDLE', current_time)
        
        # WhatsApp call notification exists - now determine if RINGING or CONNECTED
        # Extract phone number from the entire WhatsApp sections in the dump
        import re
        candidates = []
        for line in dump.splitlines():
            if 'pkg=com.whatsapp' in line:
                # Look for phone numbers in this line and nearby lines
                phone_matches = re.findall(r'(\+?[1-9][0-9]{6,14})', line)
                candidates.extend(phone_matches)
        
        if candidates:
            whatsapp_number = max(candidates, key=len)
        
        # ONLY search for phrases within WhatsApp package notifications, not system ones
        whatsapp_sections = []
        lines = dump.splitlines()
        in_whatsapp_section = False
        current_section = []
        
        for line in lines:
            if 'pkg=com.whatsapp' in line:
                in_whatsapp_section = True
                current_section = [line]
            elif in_whatsapp_section:
                if line.strip() == '' or 'pkg=' in line:
                    # End of this notification section
                    whatsapp_sections.append('\n'.join(current_section))
                    in_whatsapp_section = False
                    current_section = []
                else:
                    current_section.append(line)
        
        if in_whatsapp_section and current_section:
            whatsapp_sections.append('\n'.join(current_section))
        
        # Search within WhatsApp notification sections for RINGING vs CONNECTED
        for section in whatsapp_sections:
            lower = section.lower()
            
            # Extract number from WhatsApp section if found
            section_number = whatsapp_number
            if not section_number:
                import re
                candidates = re.findall(r'(\+?[1-9][0-9]{6,14})', section)
                if candidates:
                    section_number = max(candidates, key=len)
            
            # Check for RINGING phrases first (incoming call)
            ringing_phrases = [
                'whatsapp incoming', 'whatsapp calling', 'whatsapp ringing',
                'incoming voice call', 'incoming call', 'calling...', 'ringing'
            ]
            
            for p in ringing_phrases:
                if p in lower:
                    if self.debug:
                        print(f"[WA PHRASE] Found ringing in WA section: {p}")
                    return ('RINGING', section_number)
            
            # Check for CONNECTED phrases (ongoing call)
            connected_phrases = [
                'ongoing voice call', 'ongoing call', 'whatsapp voice call',
                'call in progress', 'in call', 'call connected',
                'active voice call', 'voip call', 'voice call active'
            ]
            
            for p in connected_phrases:
                if p in lower:
                    if self.debug:
                        print(f"[WA PHRASE] Found connected in WA section: {p}")
                    return ('CONNECTED', section_number)
        
        # WhatsApp call notification exists but no specific phrase detected
        # Default to RINGING for safety (don't auto-answer unless we're sure it's connected)
        if self.debug:
            print(f"[WA DEFAULT] WhatsApp call found but no phrase detected - defaulting to RINGING")
        return ('RINGING', whatsapp_number)

    def get_state(self, account_id: int) -> str:
        return self._last_state.get(account_id, 'UNKNOWN')
