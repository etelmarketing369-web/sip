#!/usr/bin/env python3
"""
Audio Device Manager for SIP Accounts
Handles per-account audio device assignment and routing
"""

import pyaudio
import sounddevice as sd
from typing import Dict, List, Optional, Tuple
from config_manager import ConfigManager

class AudioDeviceManager:
    """Manages audio devices for individual SIP accounts"""
    
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.account_audio_devices = {}  # account_id -> {'input': device_id, 'output': device_id}
        self.device_info = self._get_device_info()
        # Persisted configuration (for fallback device selection per account)
        self._config = ConfigManager()
        
    def _get_device_info(self) -> Dict:
        """Get information about all audio devices"""
        devices = {
            'input': [],
            'output': [],
            'all': []
        }
        
        # Get PyAudio devices
        for i in range(self.audio.get_device_count()):
            try:
                info = self.audio.get_device_info_by_index(i)
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
                print(f"Warning: Could not get info for device {i}: {e}")
                
        return devices
        
    def get_input_devices(self) -> List[Dict]:
        """Get list of available input devices"""
        return self.device_info['input']
        
    def get_output_devices(self) -> List[Dict]:
        """Get list of available output devices"""
        return self.device_info['output']
        
    def get_device_name(self, device_id: int) -> str:
        """Get device name by ID"""
        for device in self.device_info['all']:
            if device['id'] == device_id:
                return device['name']
        return f"Device {device_id}"
        
    def set_account_audio_devices(self, account_id: int, input_device_id: Optional[int], 
                                 output_device_id: Optional[int]):
        """Set audio devices for a specific account"""
        self.account_audio_devices[account_id] = {
            'input': input_device_id,
            'output': output_device_id
        }
        
    def get_account_audio_devices(self, account_id: int) -> Dict:
        """Get effective audio devices for a specific account.
        Order of precedence:
          1) Devices explicitly set via set_account_audio_devices during runtime
          2) Persisted ConfigManager per-account device IDs (if set, -1 means default)
          3) Defaults (None -> system default device)
        Returns dict with keys: input_device_id, output_device_id (values can be None)
        """
        # Reload persisted config to pick up changes made by external tools/UI
        try:
            self._config.load_config()
        except Exception:
            pass
        # 1) Runtime overrides (if any)
        runtime = self.account_audio_devices.get(account_id, {'input': None, 'output': None})
        in_id = runtime.get('input')
        out_id = runtime.get('output')

        # 2) Fallback to persisted config if not set
        if in_id is None or out_id is None:
            try:
                cfg_in, cfg_out = self._config.get_account_audio_devices(account_id)
                # Convert -1 to None for PyAudio (use default)
                cfg_in = None if cfg_in is None or int(cfg_in) < 0 else int(cfg_in)
                cfg_out = None if cfg_out is None or int(cfg_out) < 0 else int(cfg_out)
            except Exception:
                cfg_in, cfg_out = None, None
            if in_id is None:
                in_id = cfg_in
            if out_id is None:
                out_id = cfg_out

        # 3) Return effective mapping
        return {
            'input_device_id': in_id,
            'output_device_id': out_id,
        }
        
    def create_audio_streams(self, account_id: int, sample_rate: int = 8000, 
                           chunk_size: int = 160) -> Tuple[Optional[object], Optional[object], Optional[int], Optional[int]]:
        """Create input and output audio streams for a specific account with fallback.
        Returns (input_stream, output_stream, actual_rate, device_chunk) where actual_rate/device_chunk may
        differ from requested if the device rejected 8 kHz. device_chunk is 20 ms worth of frames at actual_rate.
        """
        # Use effective per-account devices (runtime override or config fallback)
        eff = self.get_account_audio_devices(account_id)
        devices = {
            'input': eff.get('input_device_id'),
            'output': eff.get('output_device_id')
        }
        
        input_stream = None
        output_stream = None
        actual_rate = None
        device_chunk = None
        
        # Try a set of common, device-friendly sample rates; keep 20ms frame durations
        candidate_rates = [sample_rate, 16000, 44100, 48000]
        last_err = None

        def try_open(rate: int, use_default: bool = False):
            nonlocal input_stream, output_stream, actual_rate, device_chunk, last_err
            # Compute a 20ms chunk for this rate
            frames_per_chunk = int(round(rate / 50.0))
            # Close any half-open streams from previous attempts
            if input_stream:
                try: input_stream.close()
                except: pass
                input_stream = None
            if output_stream:
                try: output_stream.close()
                except: pass
                output_stream = None

            # Resolve indices for this pass
            in_idx = None if use_default else devices['input']
            out_idx = None if use_default else devices['output']

            # Open input stream
            input_stream = None
            try:
                if in_idx is not None:
                    input_stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        input=True,
                        input_device_index=in_idx,
                        frames_per_buffer=frames_per_chunk
                    )
                else:
                    input_stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        input=True,
                        frames_per_buffer=frames_per_chunk
                    )
            except Exception as e:
                last_err = e
                input_stream = None

            # Open output stream
            try:
                if out_idx is not None:
                    output_stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        output=True,
                        output_device_index=out_idx,
                        frames_per_buffer=frames_per_chunk
                    )
                else:
                    output_stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        output=True,
                        frames_per_buffer=frames_per_chunk
                    )
            except Exception as e:
                last_err = e
                output_stream = None

            # If both failed at this rate, return False to continue trying
            if not input_stream and not output_stream:
                # ensure everything is closed before next attempt
                if input_stream:
                    try: input_stream.close()
                    except: pass
                    input_stream = None
                if output_stream:
                    try: output_stream.close()
                    except: pass
                    output_stream = None
                return False

            # Success (at least one stream opened); prefer both, but allow partial
            actual_rate = rate
            device_chunk = frames_per_chunk
            return True

        # Phase 1: try with specified devices
        opened = False
        for rate in candidate_rates:
            if try_open(rate, use_default=False):
                opened = True
                break

        # Phase 2: if not opened, try with default devices (ignore mapped indices)
        if not opened:
            for rate in candidate_rates:
                if try_open(rate, use_default=True):
                    opened = True
                    break

        if not opened:
            print(f"Error creating audio streams for account {account_id}: {last_err}")
            return None, None, None, None

        return input_stream, output_stream, actual_rate, device_chunk
        
    def test_device(self, device_id: int, is_input: bool = True, duration: int = 2) -> bool:
        """Test an audio device"""
        try:
            if is_input:
                # Test input device
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=8000,
                    input=True,
                    input_device_index=device_id,
                    frames_per_buffer=160
                )
                
                # Record for the duration
                for _ in range(int(8000 / 160 * duration)):
                    data = stream.read(160, exception_on_overflow=False)
                    
                stream.close()
                
            else:
                # Test output device
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=8000,
                    output=True,
                    output_device_index=device_id,
                    frames_per_buffer=160
                )
                
                # Play silence for the duration
                import struct
                silence = struct.pack('<h', 0) * 160
                for _ in range(int(8000 / 160 * duration)):
                    stream.write(silence)
                    
                stream.close()
                
            return True
            
        except Exception as e:
            print(f"Device test failed for device {device_id}: {e}")
            return False
            
    def get_recommended_devices(self) -> Dict:
        """Get recommended devices for different use cases"""
        recommendations = {
            'professional': [],
            'gaming': [],
            'builtin': []
        }
        
        for device in self.device_info['all']:
            name_lower = device['name'].lower()
            
            # Professional audio devices
            if any(keyword in name_lower for keyword in ['audio interface', 'focusrite', 'presonus', 'motu']):
                recommendations['professional'].append(device)
                
            # Gaming devices
            elif any(keyword in name_lower for keyword in ['gaming', 'steelseries', 'razer', 'corsair', 'hyperx']):
                recommendations['gaming'].append(device)
                
            # Built-in devices
            elif any(keyword in name_lower for keyword in ['realtek', 'intel', 'built-in', 'internal']):
                recommendations['builtin'].append(device)
                
        return recommendations
        
    def cleanup(self):
        """Clean up audio resources"""
        try:
            self.audio.terminate()
        except:
            pass

# Enhanced RTP Manager with per-account audio devices
class EnhancedRTPManager:
    """Enhanced RTP Manager with per-account audio device support"""
    
    def __init__(self, audio_device_manager: AudioDeviceManager):
        self.audio_device_manager = audio_device_manager
        self.active_streams = {}
        self.sample_rate = 8000
        self.chunk_size = 160
        
    def start_rtp_stream(self, call_id: int, account_id: int, local_port: int, 
                        remote_ip: str, remote_port: int):
        """Start RTP audio stream for a call using account-specific audio devices"""
        try:
            # Create RTP socket
            import socket
            rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rtp_socket.bind(('', local_port))
            
            # Create account-specific audio streams
            input_stream, output_stream, _rate, _dev_chunk = self.audio_device_manager.create_audio_streams(
                account_id, self.sample_rate, self.chunk_size
            )
            
            if not input_stream or not output_stream:
                print(f"Failed to create audio streams for account {account_id}")
                return False
                
            stream_info = {
                'socket': rtp_socket,
                'input_stream': input_stream,
                'output_stream': output_stream,
                'account_id': account_id,
                'remote_ip': remote_ip,
                'remote_port': remote_port,
                'local_port': local_port,
                'sequence': 0,
                'timestamp': 0,
                'ssrc': 12345 + account_id,  # Unique SSRC per account
                'running': True
            }
            
            self.active_streams[call_id] = stream_info
            
            # Start send/receive threads
            import threading
            send_thread = threading.Thread(
                target=self._send_audio_thread, 
                args=(call_id,), 
                daemon=True
            )
            receive_thread = threading.Thread(
                target=self._receive_audio_thread, 
                args=(call_id,), 
                daemon=True
            )
            
            send_thread.start()
            receive_thread.start()
            
            # Get device names for logging
            devices = self.audio_device_manager.account_audio_devices.get(account_id, {'input': None, 'output': None})
            input_name = self.audio_device_manager.get_device_name(devices['input']) if devices['input'] else 'Default'
            output_name = self.audio_device_manager.get_device_name(devices['output']) if devices['output'] else 'Default'
            
            print(f"RTP stream started for call {call_id} (Account {account_id}): {local_port} -> {remote_ip}:{remote_port}")
            print(f"  Input device: {input_name}")
            print(f"  Output device: {output_name}")
            return True
            
        except Exception as e:
            print(f"Failed to start RTP stream for call {call_id}: {e}")
            return False
            
    def stop_rtp_stream(self, call_id: int):
        """Stop RTP audio stream for a call"""
        if call_id in self.active_streams:
            stream = self.active_streams[call_id]
            stream['running'] = False
            
            # Close audio streams
            try:
                stream['input_stream'].stop_stream()
                stream['input_stream'].close()
                stream['output_stream'].stop_stream()
                stream['output_stream'].close()
                stream['socket'].close()
            except:
                pass
                
            del self.active_streams[call_id]
            print(f"RTP stream stopped for call {call_id}")
            
    def _send_audio_thread(self, call_id: int):
        """Thread for sending audio via RTP"""
        if call_id not in self.active_streams:
            return
            
        stream = self.active_streams[call_id]
        
        while stream['running']:
            try:
                # Read audio from account-specific microphone
                audio_data = stream['input_stream'].read(
                    self.chunk_size, exception_on_overflow=False
                )
                
                # Create RTP packet
                rtp_packet = self._create_rtp_packet(
                    stream['sequence'],
                    stream['timestamp'],
                    stream['ssrc'],
                    audio_data
                )
                
                # Send to remote
                stream['socket'].sendto(
                    rtp_packet,
                    (stream['remote_ip'], stream['remote_port'])
                )
                
                # Update sequence and timestamp
                stream['sequence'] = (stream['sequence'] + 1) & 0xFFFF
                stream['timestamp'] = (stream['timestamp'] + self.chunk_size) & 0xFFFFFFFF
                
                # Sleep for packet timing (20ms)
                import time
                time.sleep(0.02)
                
            except Exception as e:
                if stream['running']:
                    print(f"Error in send audio thread for call {call_id}: {e}")
                break
                
    def _receive_audio_thread(self, call_id: int):
        """Thread for receiving audio via RTP"""
        if call_id not in self.active_streams:
            return
            
        stream = self.active_streams[call_id]
        stream['socket'].settimeout(1.0)
        
        while stream['running']:
            try:
                # Receive RTP packet
                packet, addr = stream['socket'].recvfrom(4096)
                
                # Parse RTP packet and extract audio
                audio_data = self._parse_rtp_packet(packet)
                if audio_data:
                    # Play audio through account-specific speaker
                    stream['output_stream'].write(audio_data)
                    
            except Exception as e:
                if stream['running'] and 'timed out' not in str(e):
                    print(f"Error in receive audio thread for call {call_id}: {e}")
                    
    def _create_rtp_packet(self, sequence: int, timestamp: int, ssrc: int, payload: bytes) -> bytes:
        """Create RTP packet with audio payload"""
        import struct
        
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        payload_type = 0  # PCMU
        
        header = struct.pack(
            '>BBHII',
            (version << 6) | (padding << 5) | (extension << 4) | cc,
            (marker << 7) | payload_type,
            sequence,
            timestamp,
            ssrc
        )
        
        return header + payload
        
    def _parse_rtp_packet(self, packet: bytes) -> bytes:
        """Parse RTP packet and extract audio payload"""
        if len(packet) < 12:
            return b''
        return packet[12:]
        
    def cleanup(self):
        """Clean up all RTP streams"""
        for call_id in list(self.active_streams.keys()):
            self.stop_rtp_stream(call_id)

if __name__ == "__main__":
    print("🎵 Audio Device Manager Test")
    print("=" * 50)
    
    audio_mgr = AudioDeviceManager()
    
    try:
        print("📋 Available Input Devices:")
        for i, device in enumerate(audio_mgr.get_input_devices()):
            print(f"  {device['id']}: {device['name']} ({device['max_input_channels']} channels)")
            
        print(f"\n📋 Available Output Devices:")
        for i, device in enumerate(audio_mgr.get_output_devices()):
            print(f"  {device['id']}: {device['name']} ({device['max_output_channels']} channels)")
            
        print(f"\n💡 Recommended Devices:")
        recommendations = audio_mgr.get_recommended_devices()
        for category, devices in recommendations.items():
            if devices:
                print(f"  {category.title()}: {len(devices)} devices")
                for device in devices[:3]:  # Show first 3
                    print(f"    - {device['name']}")
                    
        # Test creating streams for different accounts
        print(f"\n🧪 Testing Account-Specific Audio Streams:")
        
        # Set different devices for account 0 and 1 (if available)
        input_devices = audio_mgr.get_input_devices()
        output_devices = audio_mgr.get_output_devices()
        
        if len(input_devices) >= 1 and len(output_devices) >= 1:
            audio_mgr.set_account_audio_devices(0, input_devices[0]['id'], output_devices[0]['id'])
            print(f"  Account 0: Input={input_devices[0]['name']}, Output={output_devices[0]['name']}")
            
            if len(input_devices) >= 2 and len(output_devices) >= 2:
                audio_mgr.set_account_audio_devices(1, input_devices[1]['id'], output_devices[1]['id'])
                print(f"  Account 1: Input={input_devices[1]['name']}, Output={output_devices[1]['name']}")
                
        # Test stream creation
        input_stream, output_stream, rate, dev_chunk = audio_mgr.create_audio_streams(0)
        if input_stream and output_stream:
            print("  ✅ Account 0 audio streams created successfully")
            input_stream.close()
            output_stream.close()
        else:
            print("  ❌ Failed to create audio streams for account 0")
            
        print(f"\n✅ Audio Device Manager ready for per-account audio routing!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        audio_mgr.cleanup()
