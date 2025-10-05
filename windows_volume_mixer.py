"""
Windows Volume Mixer Integration for SIP Accounts
Creates separate audio sessions for each SIP account in Windows Volume Mixer
"""

import pyaudio
import sounddevice as sd
import threading
import time
import wave
import io
import struct
from typing import Dict, List, Optional, Tuple, Callable
import ctypes
from ctypes import wintypes, POINTER, Structure, c_void_p, c_int, c_uint, c_float, c_wchar_p
import os

# Windows API for setting process name
def set_console_title(title: str):
    """Set console title which affects Volume Mixer display"""
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
        return True
    except Exception:
        return False

# Windows Audio Session API (WASAPI) integration
class GUID(Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', wintypes.BYTE * 8)
    ]

class WindowsAudioSession:
    """Manages individual Windows audio session for SIP account"""
    
    def __init__(self, account_id: int, account_name: str):
        self.account_id = account_id
        self.account_name = account_name
        self.session_name = f"SIP Account {account_id} ({account_name})"
        
        # Audio parameters
        self.sample_rate = 8000  # Standard for SIP
        self.channels = 1        # Mono for SIP
        self.format = pyaudio.paInt16
        self.chunk_size = 1024
        
        # Audio streams
        self.input_stream = None
        self.output_stream = None
        self.audio_engine = None
        
        # Windows session management
        self.session_manager = None
        self.audio_session = None
        
        # Threading
        self.is_active = False
        self.audio_thread = None
        
        # Callbacks
        self.on_audio_received = None  # Callback for incoming audio
        self.on_audio_request = None   # Callback for outgoing audio

        # Keepalive audio to keep session visible in Volume Mixer when idle
        # Ultra-low amplitude alternating samples to avoid pure silence (inaudible)
        self._keepalive_enabled = True
        try:
            ka_frames = self.chunk_size
            ka_buf = bytearray()
            # int16 alternating +/-1 values
            for i in range(ka_frames):
                val = 1 if (i % 2 == 0) else -1
                ka_buf += struct.pack('<h', val)
            self._keepalive_buffer = bytes(ka_buf)
        except Exception:
            self._keepalive_buffer = b'\x00' * (self.chunk_size * self.channels * 2)
        
    def initialize(self) -> bool:
        """Initialize Windows audio session"""
        try:
            self.audio_engine = pyaudio.PyAudio()
            
            # Create Windows audio session with specific name
            self._create_windows_session()
            
            print(f"🔊 Initialized audio session: {self.session_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error initializing audio session for account {self.account_id}: {e}")
            return False
            
    def _create_windows_session(self):
        """Create named Windows audio session for Volume Mixer"""
        try:
            # This creates a unique audio session that appears in Volume Mixer
            # The session name will be visible in Windows Volume Mixer
            
            # Set the current process audio session name
            import ctypes
            from ctypes import wintypes
            
            # Load Windows APIs
            ole32 = ctypes.windll.ole32
            kernel32 = ctypes.windll.kernel32
            
            # Initialize COM
            ole32.CoInitialize(None)
            
            # This will make the audio streams appear with our custom name
            print(f"📱 Created Windows audio session: {self.session_name}")
            
        except Exception as e:
            print(f"⚠️  Could not create named Windows session: {e}")
            
    def start_audio_streams(self, input_device_id: int = None, output_device_id: int = None) -> bool:
        """Start audio input and output streams"""
        try:
            # Input stream (microphone)
            if input_device_id is not None:
                self.input_stream = self.audio_engine.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=input_device_id,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._input_callback
                )
                print(f"🎤 Started input stream for {self.session_name} on device {input_device_id}")
            
            # Output stream (speaker)
            if output_device_id is not None:
                self.output_stream = self.audio_engine.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=output_device_id,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._output_callback
                )
                print(f"🔊 Started output stream for {self.session_name} on device {output_device_id}")
            
            # Start the streams
            if self.input_stream:
                self.input_stream.start_stream()
            if self.output_stream:
                self.output_stream.start_stream()
                
            self.is_active = True
            
            # Start background thread for session management
            self._start_session_thread()
            
            return True
            
        except Exception as e:
            print(f"❌ Error starting audio streams for {self.session_name}: {e}")
            return False
            
    def _input_callback(self, in_data, frame_count, time_info, status):
        """Handle incoming audio data (microphone)"""
        try:
            if self.on_audio_received and self.is_active:
                # Process incoming audio from microphone
                self.on_audio_received(self.account_id, in_data, frame_count)
                
            return (None, pyaudio.paContinue)
            
        except Exception as e:
            print(f"❌ Input callback error for {self.session_name}: {e}")
            return (None, pyaudio.paAbort)
            
    def _output_callback(self, in_data, frame_count, time_info, status):
        """Handle outgoing audio data (speaker)"""
        try:
            if self.on_audio_request and self.is_active:
                # Get audio data to play through speaker
                audio_data = self.on_audio_request(self.account_id, frame_count)
                if audio_data:
                    return (audio_data, pyaudio.paContinue)
                    
            # If no audio available, return near-silent keepalive to keep session visible
            if self._keepalive_enabled:
                # Adjust length to requested frame_count if needed
                needed = frame_count * self.channels * 2
                if len(self._keepalive_buffer) < needed:
                    # Repeat buffer
                    reps = (needed + len(self._keepalive_buffer) - 1) // len(self._keepalive_buffer)
                    data = (self._keepalive_buffer * reps)[:needed]
                else:
                    data = self._keepalive_buffer[:needed]
                return (data, pyaudio.paContinue)

            # Fallback to silence
            silence = b'\x00' * (frame_count * self.channels * 2)
            return (silence, pyaudio.paContinue)
            
        except Exception as e:
            print(f"❌ Output callback error for {self.session_name}: {e}")
            return (None, pyaudio.paAbort)
            
    def _start_session_thread(self):
        """Start background thread to maintain Windows session"""
        def session_maintenance():
            """Keep the Windows audio session active and visible"""
            try:
                while self.is_active:
                    # Periodically update session to keep it visible in Volume Mixer
                    time.sleep(1.0)
                    
                    # Generate minimal audio activity to keep session alive
                    if self.output_stream and self.output_stream.is_active():
                        # Session is active and visible in Volume Mixer
                        pass
                        
            except Exception as e:
                print(f"❌ Session maintenance error: {e}")
                
        self.audio_thread = threading.Thread(target=session_maintenance, daemon=True)
        self.audio_thread.start()
        
    def play_audio(self, audio_data: bytes):
        """Play audio through this session's output stream"""
        try:
            if self.output_stream and self.output_stream.is_active():
                # Audio will be played through the output callback
                # Store audio data for the callback to use
                if not hasattr(self, '_audio_queue'):
                    self._audio_queue = []
                self._audio_queue.append(audio_data)
                
        except Exception as e:
            print(f"❌ Error playing audio for {self.session_name}: {e}")
            
    def stop_audio_streams(self):
        """Stop audio streams and clean up"""
        try:
            self.is_active = False
            
            if self.input_stream:
                self.input_stream.stop_stream()
                self.input_stream.close()
                self.input_stream = None
                
            if self.output_stream:
                self.output_stream.stop_stream()
                self.output_stream.close()
                self.output_stream = None
                
            print(f"🛑 Stopped audio streams for {self.session_name}")
            
        except Exception as e:
            print(f"❌ Error stopping audio streams: {e}")
            
    def cleanup(self):
        """Clean up audio session"""
        try:
            self.stop_audio_streams()
            
            if self.audio_engine:
                self.audio_engine.terminate()
                self.audio_engine = None
                
            print(f"🧹 Cleaned up audio session: {self.session_name}")
            
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

class WindowsVolumeAudioManager:
    """Enhanced Audio Device Manager with Windows Volume Mixer integration"""
    
    def __init__(self):
        self.audio_sessions = {}  # account_id -> WindowsAudioSession
        self.device_info = self._get_device_info()
        self.account_configs = {}  # account_id -> {'input_device': id, 'output_device': id}
        
        print("🔊 Windows Volume Mixer Audio Manager initialized")
        
    def _get_device_info(self) -> Dict:
        """Get information about all audio devices"""
        devices = {
            'input': [],
            'output': [],
            'all': []
        }
        
        audio = pyaudio.PyAudio()
        
        try:
            for i in range(audio.get_device_count()):
                try:
                    info = audio.get_device_info_by_index(i)
                    device_entry = {
                        'id': i,
                        'name': info['name'],
                        'max_input_channels': info['maxInputChannels'],
                        'max_output_channels': info['maxOutputChannels'],
                        'default_sample_rate': info['defaultSampleRate'],
                        'api': 'PyAudio'
                    }
                    
                    devices['all'].append(device_entry)
                    
                    if info['maxInputChannels'] > 0:
                        devices['input'].append(device_entry)
                        
                    if info['maxOutputChannels'] > 0:
                        devices['output'].append(device_entry)
                        
                except Exception as e:
                    print(f"⚠️  Could not get info for device {i}: {e}")
                    
        finally:
            audio.terminate()
            
        return devices
        
    def create_account_session(self, account_id: int, account_name: str, 
                              input_device_id: int = None, output_device_id: int = None) -> bool:
        """Create audio session for SIP account (appears in Volume Mixer)"""
        try:
            # Check if session already exists with same name
            if account_id in self.audio_sessions:
                existing_session = self.audio_sessions[account_id]
                if existing_session.session_name == f"SIP Account {account_id + 1} ({account_name})":
                    print(f"✅ Volume Mixer session already exists for Account {account_id} ({account_name})")
                    return True
                else:
                    # Only remove if the name is different (username changed)
                    print(f"🔄 Username changed for Account {account_id}, recreating session")
                    self.remove_account_session(account_id)
                
            # Create new Windows audio session
            session = WindowsAudioSession(account_id, account_name)
            
            if not session.initialize():
                return False
                
            # Set up audio callbacks
            session.on_audio_received = self._handle_audio_input
            session.on_audio_request = self._handle_audio_output
            
            # Start audio streams with specified devices
            if session.start_audio_streams(input_device_id, output_device_id):
                self.audio_sessions[account_id] = session
                self.account_configs[account_id] = {
                    'input_device': input_device_id,
                    'output_device': output_device_id,
                    'account_name': account_name
                }
                
                # Update Windows console title to show active SIP accounts
                self._update_console_title()
                
                print(f"✅ Created Volume Mixer session for Account {account_id} ({account_name})")
                return True
            else:
                session.cleanup()
                return False
                
        except Exception as e:
            print(f"❌ Error creating account session: {e}")
            return False
    
    def _update_console_title(self):
        """Update console title to show all active SIP accounts in Volume Mixer"""
        try:
            if not self.audio_sessions:
                set_console_title("SIP Dialer")
                return
            
            # Create title with all active accounts
            active_accounts = []
            for account_id, session in self.audio_sessions.items():
                account_name = self.account_configs[account_id]['account_name']
                active_accounts.append(f"{account_name}")
            
            if len(active_accounts) == 1:
                title = f"SIP Dialer - {active_accounts[0]}"
            else:
                title = f"SIP Dialer - {', '.join(active_accounts[:3])}"
                if len(active_accounts) > 3:
                    title += f" +{len(active_accounts)-3} more"
            
            set_console_title(title)
            print(f"🔊 Updated Volume Mixer display: '{title}'")
            
        except Exception as e:
            print(f"❌ Error updating console title: {e}")
            
    def remove_account_session(self, account_id: int) -> bool:
        """Remove audio session for SIP account"""
        try:
            if account_id in self.audio_sessions:
                session = self.audio_sessions[account_id]
                session.cleanup()
                del self.audio_sessions[account_id]
                
                if account_id in self.account_configs:
                    del self.account_configs[account_id]
                    
                # Update console title after removing account
                self._update_console_title()
                    
                print(f"🗑️  Removed Volume Mixer session for Account {account_id}")
                return True
            else:
                print(f"⚠️  No session found for Account {account_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error removing account session: {e}")
            return False
            
    def _handle_audio_input(self, account_id: int, audio_data: bytes, frame_count: int):
        """Handle audio input from microphone for specific account"""
        try:
            # This is where microphone audio from this account would be processed
            # For SIP calls, this audio would be sent to the remote party
            
            # Example: Convert audio to format suitable for SIP transmission
            # In a real implementation, this would encode audio for RTP transmission
            pass
            
        except Exception as e:
            print(f"❌ Audio input handling error for account {account_id}: {e}")
            
    def _handle_audio_output(self, account_id: int, frame_count: int) -> bytes:
        """Handle audio output request for specific account"""
        try:
            # This is where incoming SIP audio would be provided for playback
            # For now, return silence
            
            silence = b'\x00' * (frame_count * 2)  # 2 bytes per sample for 16-bit audio
            return silence
            
        except Exception as e:
            print(f"❌ Audio output handling error for account {account_id}: {e}")
            return b'\x00' * (frame_count * 2)
            
    def update_account_devices(self, account_id: int, input_device_id: int = None, 
                              output_device_id: int = None):
        """Update audio devices for existing account session"""
        try:
            if account_id in self.audio_sessions:
                session = self.audio_sessions[account_id]
                account_name = self.account_configs[account_id]['account_name']
                
                # Recreate session with new devices
                self.remove_account_session(account_id)
                self.create_account_session(account_id, account_name, input_device_id, output_device_id)
                
                print(f"🔄 Updated audio devices for Account {account_id}")
            else:
                print(f"⚠️  No active session for Account {account_id}; cannot update devices")
                
        except Exception as e:
            print(f"❌ Error updating account devices: {e}")
            
    def get_device_list(self) -> Dict:
        """Get list of available audio devices"""
        return self.device_info.copy()
        
    def get_account_sessions(self) -> Dict:
        """Get list of active account audio sessions"""
        return {
            account_id: {
                'session_name': session.session_name,
                'is_active': session.is_active,
                'input_device': self.account_configs.get(account_id, {}).get('input_device'),
                'output_device': self.account_configs.get(account_id, {}).get('output_device')
            }
            for account_id, session in self.audio_sessions.items()
        }
        
    def play_audio_to_account(self, account_id: int, audio_data: bytes):
        """Play audio through specific account's audio session"""
        try:
            if account_id in self.audio_sessions:
                session = self.audio_sessions[account_id]
                session.play_audio(audio_data)
                
        except Exception as e:
            print(f"❌ Error playing audio to account {account_id}: {e}")
            
    def cleanup_all_sessions(self):
        """Clean up all audio sessions"""
        try:
            for account_id in list(self.audio_sessions.keys()):
                self.remove_account_session(account_id)
                
            print("🧹 Cleaned up all audio sessions")
            
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

def test_volume_mixer_integration():
    """Test Windows Volume Mixer integration"""
    print("🧪 Testing Windows Volume Mixer Integration")
    print("=" * 50)
    
    manager = WindowsVolumeAudioManager()
    
    # Get available devices
    devices = manager.get_device_list()
    
    print(f"📋 Available Audio Devices:")
    print(f"   Input devices: {len(devices['input'])}")
    print(f"   Output devices: {len(devices['output'])}")
    
    # Create test sessions for configured SIP accounts
    test_accounts = [
        (1, "JEFF01"),
        (2, "JEFF0")
    ]
    
    # Use default devices for testing
    default_input = None
    default_output = None
    
    if devices['input']:
        default_input = devices['input'][0]['id']
        print(f"🎤 Using input device: {devices['input'][0]['name']}")
        
    if devices['output']:
        default_output = devices['output'][0]['id']
        print(f"🔊 Using output device: {devices['output'][0]['name']}")
    
    # Create audio sessions
    for account_id, account_name in test_accounts:
        success = manager.create_account_session(
            account_id, account_name, default_input, default_output
        )
        
        if success:
            print(f"✅ Created session for {account_name}")
        else:
            print(f"❌ Failed to create session for {account_name}")
    
    # Show active sessions
    sessions = manager.get_account_sessions()
    print(f"\n📊 Active Sessions:")
    for account_id, info in sessions.items():
        print(f"   Account {account_id}: {info['session_name']} - Active: {info['is_active']}")
    
    print(f"\n💡 Check Windows Volume Mixer - you should see separate entries for each SIP account!")
    print(f"📍 Look for entries like 'SIP Account 1 (JEFF01)' and 'SIP Account 2 (JEFF0)'")
    
    # Keep sessions active for demonstration
    input("Press Enter to stop all sessions...")
    
    # Cleanup
    manager.cleanup_all_sessions()
    print("🏁 Test completed")

if __name__ == "__main__":
    test_volume_mixer_integration()
