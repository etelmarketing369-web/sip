#!/usr/bin/env python3
"""
Enhanced SIP Manager with RTP Media Support
Handles SIP calls with audio streaming using RTP
"""

import socket
import threading
import time
import random
import hashlib
import re
import struct
import pyaudio
import wave
import os

# Audioop replacement for Python 3.13+ compatibility
class AudioConverter:
    """Custom audio format converter to replace audioop module"""
    
    @staticmethod
    def ulaw2lin(data, width):
        """Convert μ-law (G.711 PCMU) to linear PCM"""
        import array
        
        # μ-law decoding table (128 entries, sign bit handled separately)
        ULAW_TABLE = [
            -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
            -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
            -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
            -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
            -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
            -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
            -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
            -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
            -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
            -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
            -876, -844, -812, -780, -748, -716, -684, -652,
            -620, -588, -556, -524, -492, -460, -428, -396,
            -372, -356, -340, -324, -308, -292, -276, -260,
            -244, -228, -212, -196, -180, -164, -148, -132,
            -120, -112, -104, -96, -88, -80, -72, -64,
            -56, -48, -40, -32, -24, -16, -8, 0
        ]
        
        if width != 2:
            raise ValueError("Only 16-bit linear samples supported")
            
        result = array.array('h')  # signed 16-bit integers
        
        for byte in data:
            # Extract sign bit (bit 7) and magnitude (bits 0-6)
            sign = byte & 0x80
            magnitude = (byte & 0x7F)
            
            # Get linear value from table
            linear = ULAW_TABLE[magnitude]
            
            # Apply sign
            if not sign:
                linear = -linear
                
            result.append(linear)
            
        return result.tobytes()
    
    @staticmethod
    def alaw2lin(data, width):
        """Convert A-law (G.711 PCMA) to linear PCM"""
        import array
        
        # A-law decoding table (128 entries, sign bit handled separately)
        ALAW_TABLE = [
            -5504, -5248, -6016, -5760, -4480, -4224, -4992, -4736,
            -7552, -7296, -8064, -7808, -6528, -6272, -7040, -6784,
            -2752, -2624, -3008, -2880, -2240, -2112, -2496, -2368,
            -3776, -3648, -4032, -3904, -3264, -3136, -3520, -3392,
            -22016, -20992, -24064, -23040, -17920, -16896, -19968, -18944,
            -30208, -29184, -32256, -31232, -26112, -25088, -28160, -27136,
            -11008, -10496, -12032, -11520, -8960, -8448, -9984, -9472,
            -15104, -14592, -16128, -15616, -13056, -12544, -14080, -13568,
            -344, -328, -376, -360, -280, -264, -312, -296,
            -472, -456, -504, -488, -408, -392, -440, -424,
            -88, -72, -120, -104, -24, -8, -56, -40,
            -216, -200, -248, -232, -152, -136, -184, -168,
            -1376, -1312, -1504, -1440, -1120, -1056, -1248, -1184,
            -1888, -1824, -2016, -1952, -1632, -1568, -1760, -1696,
            -688, -656, -752, -720, -560, -528, -624, -592,
            -944, -912, -1008, -976, -816, -784, -880, -848
        ]
        
        if width != 2:
            raise ValueError("Only 16-bit linear samples supported")
            
        result = array.array('h')  # signed 16-bit integers
        
        for byte in data:
            # Extract sign bit (bit 7) and magnitude (bits 0-6)
            sign = byte & 0x80
            magnitude = (byte & 0x7F)
            
            # Get linear value from table
            linear = ALAW_TABLE[magnitude]
            
            # Apply sign
            if sign:
                linear = -linear
                
            result.append(linear)
            
        return result.tobytes()
    
    @staticmethod
    def lin2ulaw(data, width):
        """Convert linear PCM to μ-law (G.711 PCMU)"""
        import array
        
        if width != 2:
            raise ValueError("Only 16-bit linear samples supported")
            
        # Convert bytes to signed 16-bit integers
        samples = array.array('h')
        samples.frombytes(data)
        
        result = bytearray()
        
        for sample in samples:
            # Bias the sample and get absolute value
            biased = sample + 33
            if biased < 0:
                biased = -biased
                sign = 0x00
            else:
                sign = 0x80
                
            # Clip to prevent overflow
            if biased > 32767:
                biased = 32767
                
            # Find segment (logarithmic quantization)
            seg = 0
            temp = biased >> 7
            while temp != 0 and seg < 7:
                seg += 1
                temp >>= 1
                
            # Get quantization step within segment
            if seg == 0:
                uval = (biased >> 1) & 0x0F
            else:
                uval = ((biased >> seg) & 0x0F) | 0x10
                
            # Combine sign, segment, and quantization
            ulaw_byte = sign | (seg << 4) | uval
            
            # Complement for transmission
            result.append(ulaw_byte ^ 0xFF)
            
        return bytes(result)
    
    @staticmethod
    def lin2alaw(data, width):
        """Convert linear PCM to A-law (G.711 PCMA)"""
        import array
        
        if width != 2:
            raise ValueError("Only 16-bit linear samples supported")
            
        # Convert bytes to signed 16-bit integers
        samples = array.array('h')
        samples.frombytes(data)
        
        result = bytearray()
        
        for sample in samples:
            # Get absolute value and sign
            if sample < 0:
                sample = -sample
                sign = 0x00
            else:
                sign = 0x80
                
            # Clip to prevent overflow
            if sample > 32767:
                sample = 32767
                
            # Compress using A-law algorithm
            if sample >= 256:
                # Find segment (logarithmic quantization)
                seg = 1
                temp = sample >> 8
                while temp != 1 and seg < 7:
                    seg += 1
                    temp >>= 1
                    
                # Get quantization step within segment
                if seg == 1:
                    aval = (sample >> 4) & 0x0F
                else:
                    aval = (sample >> (seg + 3)) & 0x0F
                    
                # Combine segment and quantization
                alaw_byte = (seg << 4) | aval
            else:
                # Linear quantization for small values
                alaw_byte = sample >> 4
                
            # Apply sign and XOR
            result.append((sign | alaw_byte) ^ 0x55)
            
        return bytes(result)
    
    @staticmethod
    def ratecv(fragment, width, nchannels, inrate, outrate, state):
        """Basic sample rate conversion using linear interpolation"""
        import array
        
        if width != 2 or nchannels != 1:
            raise ValueError("Only 16-bit mono samples supported")
            
        if inrate == outrate:
            return fragment, state
            
        # Convert to array of samples
        in_samples = array.array('h')
        in_samples.frombytes(fragment)
        
        # Calculate conversion ratio
        ratio = inrate / outrate
        out_length = int(len(in_samples) / ratio)
        
        # Simple linear interpolation
        out_samples = array.array('h')
        for i in range(out_length):
            # Calculate corresponding input position
            pos = i * ratio
            idx = int(pos)
            frac = pos - idx
            
            if idx + 1 < len(in_samples):
                # Linear interpolation between two samples
                sample = int(in_samples[idx] * (1 - frac) + in_samples[idx + 1] * frac)
            else:
                # Use last sample if at end
                sample = in_samples[idx] if idx < len(in_samples) else 0
                
            out_samples.append(sample)
            
        return out_samples.tobytes(), None

# Create compatibility layer
audioop = AudioConverter()
from typing import Dict, Optional, Callable, List
from working_sip_manager import WorkingSipManager
from audio_device_manager import AudioDeviceManager

class EnhancedRTPManager:
    """Enhanced RTP Manager with per-account audio device support"""
    
    def __init__(self, audio_device_manager: AudioDeviceManager):
        self.audio_device_manager = audio_device_manager
        self.active_streams = {}
        self.sample_rate = 8000  # Standard for telephony
        self.chunk_size = 160    # 20ms at 8kHz
        self.format = pyaudio.paInt16
        self.channels = 1

    def set_main_process_mixer_name(self, display_name: str, retries: int = 10, delay: float = 0.3) -> bool:
        """Set the Windows Volume Mixer display name for the current process's audio session.
        Uses pycaw to find sessions for this PID and call SetDisplayName.
        Returns True if any session name was updated.
        """
        try:
            from pycaw.pycaw import AudioUtilities
        except Exception as e:
            print(f"ℹ️  pycaw not available; Mixer may show Python executable name: {e}")
            return False

        pid = os.getpid()
        for _ in range(retries):
            try:
                sessions = AudioUtilities.GetAllSessions()
                updated = False
                for s in sessions:
                    try:
                        if getattr(s, 'Process', None) and s.Process and s.Process.pid == pid and hasattr(s, '_ctl') and s._ctl:
                            # SetDisplayName takes (LPCWSTR, LPCGUID) where context can be None
                            s._ctl.SetDisplayName(display_name, None)
                            updated = True
                    except Exception:
                        # Ignore and continue searching
                        pass
                if updated:
                    print(f"🔊 Volume Mixer session name set: {display_name}")
                    return True
            except Exception:
                # Enumerating sessions may fail until streams are active
                pass
            time.sleep(delay)
        print("⚠️  Could not set Mixer display name for main process; continuing")
        return False
        
    def start_rtp_stream(self, call_id: int, account_id: int, local_port: int, remote_ip: str, remote_port: int,
                         payload_type: int = 0, codec: str = 'PCMU'):
        """Start RTP audio stream for a call with account-specific audio devices"""
        try:
            # Avoid double-start for same call
            if call_id in self.active_streams:
                stream = self.active_streams[call_id]
                print(f"RTP already active for call {call_id}: {stream.get('local_port')} -> {stream.get('remote_ip')}:{stream.get('remote_port')}")
                return True
            # Get audio devices for this account
            devices = self.audio_device_manager.get_account_audio_devices(account_id)
            input_device_id = devices.get('input_device_id')
            output_device_id = devices.get('output_device_id')
            
            # Create RTP socket
            rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Bind with small retry in case of recent reuse
            bind_ok = False
            bind_port = local_port
            for i in range(2):
                try:
                    rtp_socket.bind(('', bind_port))
                    bind_ok = True
                    break
                except OSError as e:
                    if i == 0 and getattr(e, 'winerror', None) == 10048:
                        # Try next even port
                        bind_port = local_port + 2
                        continue
                    raise
            if not bind_ok:
                raise OSError("Failed to bind RTP socket")
            
            # Create audio streams for this account using the AudioDeviceManager
            input_stream, output_stream, device_rate, device_chunk = self.audio_device_manager.create_audio_streams(
                account_id, self.sample_rate, self.chunk_size
            )
            if not input_stream or not output_stream:
                try:
                    rtp_socket.close()
                except Exception:
                    pass
                print(f"Failed to create audio streams for account {account_id}")
                return False
            # Default to our RTP rate/chunk if manager didn't provide alternatives
            if not device_rate:
                device_rate = self.sample_rate
            if not device_chunk:
                device_chunk = self.chunk_size
            
            stream_info = {
                'socket': rtp_socket,
                'input_stream': input_stream,
                'output_stream': output_stream,
                'account_id': account_id,
                'input_device_id': input_device_id,
                'output_device_id': output_device_id,
                'remote_ip': remote_ip,
                'remote_port': remote_port,
                'local_port': bind_port,
                'sequence': 0,
                'timestamp': 0,
                'ssrc': random.randint(1, 0xFFFFFFFF),
                'running': True,
                'payload_type': payload_type,
                'codec': codec.upper() if isinstance(codec, str) else 'PCMU',
                'tx_count': 0,
                'rx_count': 0,
                'device_rate': device_rate,
                'device_chunk': device_chunk,
            }
            
            self.active_streams[call_id] = stream_info
            
            # Start send/receive threads
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
            
            # Friendly names for logs
            try:
                input_name = self.audio_device_manager.get_device_name(input_device_id) if input_device_id is not None else 'Default'
                output_name = self.audio_device_manager.get_device_name(output_device_id) if output_device_id is not None else 'Default'
            except Exception:
                input_name = str(input_device_id)
                output_name = str(output_device_id)

            print(f"RTP stream started for call {call_id}, account {account_id}: {bind_port} -> {remote_ip}:{remote_port}")
            print(f"Using audio devices - Input: {input_name}, Output: {output_name}")
            if device_rate != self.sample_rate:
                print(f"  Note: Device rate {device_rate} Hz (chunk {device_chunk}) with transparent resampling from 8000 Hz")
            return True
            
        except Exception as e:
            print(f"Failed to start RTP stream for call {call_id}: {e}")
            return False
            
    def stop_rtp_stream(self, call_id: int):
        """Stop RTP audio stream for a call"""
        if call_id in self.active_streams:
            stream = self.active_streams[call_id]
            stream['running'] = False
            
            # Close audio streams and socket
            try:
                inp = stream.get('input_stream')
                outp = stream.get('output_stream')
                if inp:
                    try:
                        inp.stop_stream()
                    except Exception:
                        pass
                    try:
                        inp.close()
                    except Exception:
                        pass
                if outp:
                    try:
                        outp.stop_stream()
                    except Exception:
                        pass
                    try:
                        outp.close()
                    except Exception:
                        pass
                try:
                    stream['socket'].close()
                except Exception:
                    pass
            except Exception as e:
                print(f"Error stopping RTP stream: {e}")
                
            del self.active_streams[call_id]
            print(f"RTP stream stopped for call {call_id}")
            
    def _send_audio_thread(self, call_id: int):
        """Thread for sending audio via RTP"""
        if call_id not in self.active_streams:
            return
            
        stream = self.active_streams[call_id]
        
        while stream['running']:
            try:
                # Read audio from microphone at device rate
                dev_chunk = int(stream.get('device_chunk') or self.chunk_size)
                dev_rate = int(stream.get('device_rate') or self.sample_rate)
                audio_data = stream['input_stream'].read(
                    dev_chunk, exception_on_overflow=False
                )
                # If device rate != RTP rate, downsample to 8kHz for encoding
                if dev_rate != self.sample_rate:
                    try:
                        # audioop.ratecv returns (converted_data, state)
                        converted, _ = audioop.ratecv(audio_data, 2, 1, dev_rate, self.sample_rate, None)
                        pcm8 = converted
                    except Exception as rerr:
                        # On failure, fall back to silence for this frame
                        pcm8 = b"\x00\x00" * self.chunk_size
                else:
                    pcm8 = audio_data
                # Convert 16-bit PCM -> G.711 (mu-law or A-law) based on negotiated codec
                try:
                    if stream.get('codec', 'PCMU') == 'PCMA':
                        payload = audioop.lin2alaw(pcm8, 2)
                    else:
                        payload = audioop.lin2ulaw(pcm8, 2)
                except Exception as conv_err:
                    # On failure, send encoded silence rather than raw PCM to avoid static
                    silence = b"\x00\x00" * self.chunk_size
                    try:
                        payload = audioop.lin2ulaw(silence, 2)
                    except Exception:
                        # Give up on this frame
                        print(f"G.711 encode failed (call {call_id}): {conv_err}")
                        time.sleep(0.02)
                        continue
                
                # Create RTP packet
                rtp_packet = self._create_rtp_packet(
                    stream['sequence'],
                    stream['timestamp'],
                    stream['ssrc'],
                    payload,
                    stream.get('payload_type', 0)
                )
                
                # Send to remote
                stream['socket'].sendto(
                    rtp_packet,
                    (stream['remote_ip'], stream['remote_port'])
                )
                
                # Update sequence and timestamp
                stream['sequence'] = (stream['sequence'] + 1) & 0xFFFF
                stream['timestamp'] = (stream['timestamp'] + self.chunk_size) & 0xFFFFFFFF
                stream['tx_count'] += 1
                if stream['tx_count'] <= 5:
                    print(f"RTP TX call {call_id}: PT={stream.get('payload_type',0)} seq={stream['sequence']} ts={stream['timestamp']} bytes={len(payload)} -> {stream['remote_ip']}:{stream['remote_port']}")
                
                # Sleep for packet timing (20ms)
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
                
                # Parse RTP packet, extract payload type and audio
                pt, audio_data = self._parse_rtp_header_and_payload(packet)
                if audio_data and pt in (0, 8):
                    # Convert G.711 to 16-bit PCM before playback based on payload type
                    try:
                        if pt == 8:  # PCMA
                            pcm = audioop.alaw2lin(audio_data, 2)
                        else:       # PCMU (0)
                            pcm = audioop.ulaw2lin(audio_data, 2)
                    except Exception as dec_err:
                        # Drop frame to avoid static
                        print(f"G.711 decode failed (call {call_id}): {dec_err}")
                        continue
                    # If device rate != RTP rate, upsample from 8k to device rate for playback
                    dev_rate = int(stream.get('device_rate') or self.sample_rate)
                    if dev_rate != self.sample_rate:
                        try:
                            pcm, _ = audioop.ratecv(pcm, 2, 1, self.sample_rate, dev_rate, None)
                        except Exception as rerr:
                            # On failure, write the 8k data directly (driver may resample) or skip
                            pass
                    # Play audio through speaker
                    stream['output_stream'].write(pcm)
                    stream['rx_count'] += 1
                    if stream['rx_count'] <= 5:
                        print(f"RTP RX call {call_id}: PT={pt} bytes={len(audio_data)} from {addr}")
                elif audio_data and pt not in (0, 8):
                    # Ignore non-G711 payloads like telephone-event (DTMF)
                    stream['rx_count'] += 1
                    if stream['rx_count'] <= 3:
                        print(f"RTP RX call {call_id}: Ignoring PT={pt} bytes={len(audio_data)} (non-G711)")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if stream['running']:
                    print(f"Error in receive audio thread for call {call_id}: {e}")
                break
                
    def _create_rtp_packet(self, sequence: int, timestamp: int, ssrc: int, payload: bytes, payload_type: int) -> bytes:
        """Create RTP packet with audio payload"""
        # RTP Header (12 bytes)
        # V(2) + P(1) + X(1) + CC(4) = 8 bits
        # M(1) + PT(7) = 8 bits  (PT=0 for PCMU, PT=8 for PCMA)
        # Sequence Number = 16 bits
        # Timestamp = 32 bits
        # SSRC = 32 bits
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = int(payload_type) if payload_type in (0, 8) else 0
        header = struct.pack(
            '>BBHII',
            (version << 6) | (padding << 5) | (extension << 4) | cc,
            (marker << 7) | pt,
            sequence & 0xFFFF,
            timestamp & 0xFFFFFFFF,
            ssrc & 0xFFFFFFFF,
        )
        return header + payload
        
    def _parse_rtp_header_and_payload(self, packet: bytes) -> tuple[int, Optional[bytes]]:
        """Parse RTP header, return (payload_type, payload) handling CSRC, extensions, and padding."""
        try:
            if len(packet) < 12:
                return (0, None)
            b1, b2, seq, ts, ssrc = struct.unpack('>BBHII', packet[:12])
            version = (b1 >> 6) & 0x03
            padding = (b1 >> 5) & 0x01
            extension = (b1 >> 4) & 0x01
            csrc_count = b1 & 0x0F
            pt = b2 & 0x7F
            # Base header size
            offset = 12
            # Skip CSRC list if present
            csrc_bytes = csrc_count * 4
            if len(packet) < offset + csrc_bytes:
                return (pt, None)
            offset += csrc_bytes
            # Skip extension header if present
            if extension:
                if len(packet) < offset + 4:
                    return (pt, None)
                ext_profile, ext_len_words = struct.unpack('>HH', packet[offset:offset+4])
                offset += 4
                ext_len_bytes = ext_len_words * 4
                if len(packet) < offset + ext_len_bytes:
                    return (pt, None)
                offset += ext_len_bytes
            # Handle padding
            end = len(packet)
            if padding:
                padlen = packet[-1]
                if padlen < end - offset:
                    end -= padlen
            if offset >= end:
                return (pt, None)
            return (pt, packet[offset:end])
        except Exception:
            return (0, None)
            
    def cleanup(self):
        """Clean up all RTP streams"""
        for call_id in list(self.active_streams.keys()):
            self.stop_rtp_stream(call_id)
        self.audio_device_manager.cleanup()

class EnhancedSipManager(WorkingSipManager):
    """Enhanced SIP Manager with full call and per-account audio device support"""
    
    def __init__(self):
        super().__init__()
        self.audio_device_manager = AudioDeviceManager()
        self.rtp_manager = EnhancedRTPManager(self.audio_device_manager)
        self.active_calls = {}
        self.call_id_counter = 1000
        # Map SIP Call-ID -> internal call id for incoming calls
        self._incoming_sip_to_internal = {}
        
    def _is_public_ip(self, ip: str) -> bool:
        """Return True if IP appears publicly routable (basic RFC1918 check)."""
        try:
            if not ip or ip == '0.0.0.0':
                return False
            parts = [int(p) for p in ip.split('.')]
            if len(parts) != 4:
                return False
            if parts[0] == 10:
                return False
            if parts[0] == 172 and 16 <= parts[1] <= 31:
                return False
            if parts[0] == 192 and parts[1] == 168:
                return False
            if parts[0] == 127:
                return False
            return True
        except Exception:
            return False
        
    def set_account_audio_devices(self, account_id: int, input_device_id: Optional[int], 
                                 output_device_id: Optional[int]):
        """Set audio devices for a specific account"""
        self.audio_device_manager.set_account_audio_devices(account_id, input_device_id, output_device_id)
        
    def get_account_audio_devices(self, account_id: int) -> Dict:
        """Get audio devices for a specific account"""
        return self.audio_device_manager.get_account_audio_devices(account_id)
        
    def get_available_input_devices(self) -> List[Dict]:
        """Get list of available input devices"""
        return self.audio_device_manager.get_input_devices()
        
    def get_available_output_devices(self) -> List[Dict]:
        """Get list of available output devices"""
        return self.audio_device_manager.get_output_devices()
        
    def shutdown(self):
        """Enhanced shutdown with audio device cleanup"""
        self.rtp_manager.cleanup()
        self.audio_device_manager.cleanup()
        super().shutdown()

    # --- Incoming call handling with media (overrides base listener) ---
    def _start_incoming_call_listener(self, account_id: int, sock: socket.socket):
        """Start background listener for incoming calls with RTP/media setup"""
        def listen_loop():
            try:
                print(f"📞 Starting incoming call listener (media) for account {account_id}")
                while account_id in self.registered_accounts:
                    try:
                        sock.settimeout(0.2)
                        data, addr = sock.recvfrom(4096)
                        message = data.decode('utf-8', errors='ignore')
                        first_token = message.split()[0] if message.split() else 'UNKNOWN'
                        if first_token == 'INVITE':
                            self._handle_incoming_invite_with_media(account_id, message, addr, sock)
                        elif first_token == 'ACK':
                            self._handle_incoming_ack_with_media(account_id, message, addr, sock)
                        elif first_token == 'BYE':
                            self._handle_incoming_bye_with_media(account_id, message, addr, sock)
                        elif first_token == 'OPTIONS':
                            self._send_options_response(sock, message, addr)
                        else:
                            # Ignore other messages
                            pass
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"❌ Incoming loop error (acct {account_id}): {e}")
                        time.sleep(0.05)
            except Exception as e:
                print(f"❌ Error starting incoming media listener: {e}")

        threading.Thread(target=listen_loop, daemon=True).start()
        print(f"✅ Incoming call (media) listener started for account {account_id}")

    def _send_options_response(self, sock: socket.socket, request: str, addr: tuple):
        """Send OPTIONS response"""
        try:
            via = self._extract_header(request, 'Via') or ''
            from_h = self._extract_header(request, 'From') or ''
            to_h = self._extract_header(request, 'To') or ''
            call_id = self._extract_header(request, 'Call-ID') or ''
            cseq = self._extract_header(request, 'CSeq') or ''
            
            response = f"""SIP/2.0 200 OK
Via: {via}
From: {from_h}
To: {to_h}
Call-ID: {call_id}
CSeq: {cseq}
Contact: <sip:{self.local_ip}:5060>
Allow: INVITE, ACK, CANCEL, BYE, OPTIONS
Content-Length: 0

"""
            sock.sendto(response.encode('utf-8'), addr)
        except Exception as e:
            print(f"Error sending OPTIONS response: {e}")

    def _create_sip_response_fast(self, request: str, status: str) -> str:
        """Create quick SIP response (100, 180, etc.)"""
        try:
            via = self._extract_header(request, 'Via') or ''
            from_h = self._extract_header(request, 'From') or ''
            to_h = self._extract_header(request, 'To') or ''
            call_id = self._extract_header(request, 'Call-ID') or ''
            cseq = self._extract_header(request, 'CSeq') or ''
            
            response = f"""SIP/2.0 {status}
Via: {via}
From: {from_h}
To: {to_h}
Call-ID: {call_id}
CSeq: {cseq}
Content-Length: 0

"""
            return response
        except Exception as e:
            print(f"Error creating SIP response: {e}")
            return ""

    def _create_sip_response(self, request: str, status: str) -> str:
        """Create SIP response with proper headers"""
        try:
            via = self._extract_header(request, 'Via') or ''
            from_h = self._extract_header(request, 'From') or ''
            to_h = self._extract_header(request, 'To') or ''
            call_id = self._extract_header(request, 'Call-ID') or ''
            cseq = self._extract_header(request, 'CSeq') or ''
            
            response = f"""SIP/2.0 {status}
Via: {via}
From: {from_h}
To: {to_h}
Call-ID: {call_id}
CSeq: {cseq}
Contact: <sip:{self.local_ip}:5060>
Content-Length: 0

"""
            return response
        except Exception as e:
            print(f"Error creating SIP response: {e}")
            return ""

    def _extract_header(self, message: str, name: str) -> Optional[str]:
        for line in message.split('\n'):
            if line.lower().startswith(name.lower() + ':'):
                return line.split(':', 1)[1].strip()
        return None

    def _parse_sdp_offer(self, message: str) -> Dict[str, Optional[str]]:
        info = {'ip': None, 'port': None, 'pts': [], 'rtpmap': {}}
        sep = message.find('\r\n\r\n')
        if sep == -1:
            sep = message.find('\n\n')
        if sep == -1:
            return info
        sdp = message[sep+4:]
        for line in sdp.split('\n'):
            line = line.strip()
            if line.startswith('c=IN IP4 '):
                info['ip'] = line.split()[-1]
            elif line.startswith('m=audio '):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    info['port'] = int(parts[1])
                    # gather offered payload types
                    if len(parts) > 3:
                        for tok in parts[3:]:
                            if tok.isdigit():
                                info['pts'].append(int(tok))
            elif line.startswith('a=rtpmap:'):
                try:
                    after = line.split(':', 1)[1]
                    pt_str, rest = after.split(None, 1)
                    pt = int(pt_str)
                    codec = rest.split('/')[0].upper()
                    info['rtpmap'][pt] = codec
                except Exception:
                    pass
        return info

    def _create_200ok_with_sdp(self, request: str, local_rtp_port: int, payload_type: int = 0, codec: str = 'PCMU') -> str:
        via = self._extract_header(request, 'Via') or ''
        from_h = self._extract_header(request, 'From') or ''
        to_h = self._extract_header(request, 'To') or ''
        call_id = self._extract_header(request, 'Call-ID') or ''
        cseq = self._extract_header(request, 'CSeq') or ''
        # Ensure To has a tag
        if to_h and 'tag=' not in to_h:
            to_h += f";tag=resp-{int(time.time()*1000)}"

        sdp = f"""v=0
o=user 123456 123456 IN IP4 {self.local_ip}
s=-
c=IN IP4 {self.local_ip}
t=0 0
m=audio {local_rtp_port} RTP/AVP {payload_type}
a=rtpmap:{payload_type} {codec}/8000
a=sendrecv
"""

        lines = [
            "SIP/2.0 200 OK",
            f"Via: {via}",
            f"From: {from_h}",
            f"To: {to_h}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq}",
            f"Contact: <sip:{self.local_ip}:5060>",
            "Content-Type: application/sdp",
            f"Content-Length: {len(sdp)}",
            "",
            sdp.rstrip(),
            "",
        ]
        return "\n".join(lines)

    def _handle_incoming_invite_with_media(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        try:
            # Basic identifiers
            call_id_hdr = self._extract_header(message, 'Call-ID') or f"unknown-{int(time.time())}"
            from_h = self._extract_header(message, 'From') or ''
            # Extract caller number (naive): look for sip:user@ or "Name" <sip:user@ pattern
            caller_number = None
            try:
                frag = from_h
                if '<' in frag and '>' in frag:
                    inside = frag.split('<',1)[1].split('>',1)[0]
                else:
                    inside = frag
                if 'sip:' in inside:
                    user_part = inside.split('sip:',1)[1].split('@',1)[0]
                    # Strip non-dial chars except +
                    num = re.sub(r'[^0-9+]', '', user_part)
                    if num:
                        caller_number = num
            except Exception:
                caller_number = None

            # Parse remote SDP offer
            sdp_offer = self._parse_sdp_offer(message)
            offer_ip = sdp_offer.get('ip')
            remote_ip = offer_ip if self._is_public_ip(offer_ip or '') else addr[0]
            remote_port = sdp_offer.get('port') or None
            # Choose codec: prefer PCMU(0), else PCMA(8)
            offered_pts = sdp_offer.get('pts', []) or []
            rtpmap = sdp_offer.get('rtpmap', {}) or {}
            chosen_pt = 0 if 0 in offered_pts else (8 if 8 in offered_pts else 0)
            chosen_codec = rtpmap.get(chosen_pt, 'PCMU') if chosen_pt in (0, 8) else 'PCMU'

            # Allocate internal call id and local RTP port
            internal_id = self.call_id_counter
            self.call_id_counter += 1
            local_rtp_port = 10000 + (internal_id % 1000) * 2

            # Send 100 Trying and 180 Ringing fast
            trying = self._create_sip_response_fast(message, "100 Trying")
            sock.sendto(trying.encode('utf-8'), addr)
            ringing = self._create_sip_response_fast(message, "180 Ringing")
            sock.sendto(ringing.encode('utf-8'), addr)

            # NOTE: We do NOT immediately send 200 OK now. We defer answering until external condition
            # (WhatsApp 'ongoing voice call' notification) is met. Store offer details for later answer.
            # Store call and mapping; RTP will start after deferred 200 OK + ACK.
            self._incoming_sip_to_internal[call_id_hdr] = internal_id
            self.active_calls[internal_id] = {
                'account_id': account_id,
                'destination': from_h,
                'caller_number': caller_number,
                'sip_call_id': call_id_hdr,
                'from_tag': '',
                'to_tag': '',
                'state': 'RINGING',
                'rtp_port': local_rtp_port,
                'remote_rtp_port': remote_port,
                'remote_ip': remote_ip,
                'remote_pt': chosen_pt,
                'remote_codec': chosen_codec,
                'auth_attempts': 0,
                'incoming': True,
                'raw_invite': message,
                'invite_received_ts': time.time(),
                'deferred_answer': True,
                'sip_addr': addr,
            }
            if self.on_incoming_call:
                # Notify application; it may trigger conditional answer later
                self.on_incoming_call(account_id, internal_id, from_h)

        except Exception as e:
            print(f"❌ Incoming INVITE (media) error: {e}")

    def answer_deferred_call(self, internal_id: int):
        """Send 200 OK + SDP for a previously deferred incoming call.

        This finalizes the answer after an external condition (e.g. WhatsApp call active)
        has been satisfied. Safe to call multiple times; will no-op if already answered
        or call not in deferred ringing state.
        """
        try:
            call_info = self.active_calls.get(internal_id)
            if not call_info:
                return False
            if not call_info.get('incoming') or not call_info.get('deferred_answer'):
                return False
            if call_info.get('state') != 'RINGING':
                return False

            raw_invite = call_info.get('raw_invite')
            addr = call_info.get('sip_addr')
            account_id = call_info.get('account_id')
            if not raw_invite or not addr or account_id is None:
                return False

            # Build 200 OK with negotiated RTP port/codec
            local_rtp_port = call_info.get('rtp_port')
            pt = call_info.get('remote_pt', 0)
            codec = call_info.get('remote_codec', 'PCMU')
            ok_response = self._create_200ok_with_sdp(raw_invite, local_rtp_port, pt, codec)
            # Need the account's SIP socket to send
            # Retrieve underlying UDP socket from base manager (WorkingSipManager uses self.sockets)
            sock = None
            try:
                if hasattr(self, 'sockets'):
                    sock = self.sockets.get(account_id)
            except Exception:
                sock = None
            if not sock:
                return False
            # Adjust Contact header port to actual bound port if different
            try:
                bound_port = sock.getsockname()[1]
                if f":{bound_port}>" not in ok_response:
                    # Replace original Contact port (rudimentary replace for :5060>)
                    ok_response = ok_response.replace(':5060>', f':{bound_port}>')
            except Exception:
                pass
            sock.sendto(ok_response.encode('utf-8'), addr)
            call_info['deferred_answer'] = False
            call_info['state'] = 'ANSWERED'
            # ACK will arrive later -> _handle_incoming_ack_with_media will start RTP
            print(f"✅ Deferred answer sent for call {internal_id} (acct {account_id})")
            if self.on_call_state_changed:
                try:
                    self.on_call_state_changed(internal_id, 'ANSWERED', '200 OK sent (deferred)')
                except Exception:
                    pass
            return True
        except Exception as e:
            print(f"❌ Error answering deferred call {internal_id}: {e}")
            return False

    def _handle_incoming_ack_with_media(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        try:
            call_id_hdr = self._extract_header(message, 'Call-ID')
            if not call_id_hdr:
                return
            internal_id = self._incoming_sip_to_internal.get(call_id_hdr)
            if internal_id is None:
                return
            call_info = self.active_calls.get(internal_id)
            if not call_info:
                return

            # If we have remote IP/port and RTP is not already active, start RTP now
            if call_info.get('remote_ip') and call_info.get('remote_rtp_port') and not call_info.get('rtp_active'):
                time.sleep(0.1) 
                started = self.rtp_manager.start_rtp_stream(
                    internal_id,
                    call_info['account_id'],
                    call_info['rtp_port'],
                    call_info['remote_ip'],
                    call_info['remote_rtp_port'],
                    call_info.get('remote_pt', 0),
                    call_info.get('remote_codec', 'PCMU')
                )
                if started:
                    call_info['rtp_active'] = True
                    call_info['state'] = 'ESTABLISHED'
                    # Ensure the main process audio session shows the SIP account name in Volume Mixer
                    try:
                        acct_id = call_info['account_id']
                        username = self.accounts.get(acct_id, {}).get('username', f'Account{acct_id+1}')
                        self.rtp_manager.set_main_process_mixer_name(f"SIP Account {acct_id + 1} ({username})")
                    except Exception:
                        pass
                    print(f"📡 Incoming call {internal_id}: Media established")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(internal_id, 'ESTABLISHED', 'Call established')

        except Exception as e:
            print(f"❌ Incoming ACK handling error: {e}")

    def _handle_incoming_bye_with_media(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        try:
            call_id_hdr = self._extract_header(message, 'Call-ID')
            internal_id = self._incoming_sip_to_internal.get(call_id_hdr)
            # Send 200 OK
            response = self._create_sip_response(message, "200 OK")
            sock.sendto(response.encode('utf-8'), addr)

            if internal_id is not None:
                # Stop RTP and cleanup
                self.rtp_manager.stop_rtp_stream(internal_id)
                self.active_calls.pop(internal_id, None)
                print(f"📞 Incoming call {internal_id} ended")
                if self.on_call_state_changed:
                    self.on_call_state_changed(internal_id, 'TERMINATED', 'Call terminated')

        except Exception as e:
            print(f"❌ Incoming BYE handling error: {e}")
        
    def make_call(self, account_id: int, destination: str) -> Optional[int]:
        """Make an outgoing SIP call with media"""
        if account_id not in self.registered_accounts:
            print(f"Account {account_id} not registered, cannot make call")
            return None
            
        if account_id not in self.accounts:
            print(f"Account {account_id} not found")
            return None
            
        account = self.accounts[account_id]
        sock = self.sockets.get(account_id)
        if not sock:
            print(f"No socket for account {account_id}")
            return None
            
        # Generate call ID
        call_id = self.call_id_counter
        self.call_id_counter += 1
        
        # Start call in thread
        call_thread = threading.Thread(
            target=self._make_call_thread,
            args=(call_id, account_id, destination, account, sock),
            daemon=True
        )
        call_thread.start()
        
        return call_id
        
    def _make_call_thread(self, call_id: int, account_id: int, destination: str, 
                         account: dict, sock: socket.socket):
        """Thread for making a SIP call"""
        try:
            # Generate SIP call identifiers
            sip_call_id = f"{random.randint(1000000, 9999999)}@{self.local_ip}"
            from_tag = str(random.randint(1000000, 9999999))
            branch = f"z9hG4bK{random.randint(100000, 999999)}"
            local_port = sock.getsockname()[1]
            
            # Choose RTP port (even number, next odd for RTCP)
            rtp_port = 10000 + (call_id % 1000) * 2
            
            # Create INVITE message
            invite_msg = self._create_invite_message(
                account, destination, sip_call_id, from_tag, branch, 
                local_port, rtp_port
            )
            
            print(f"Sending INVITE to {destination}...")
            sock.sendto(invite_msg.encode('utf-8'), (account['domain'], account['port']))
            
            # Store call info
            self.active_calls[call_id] = {
                'account_id': account_id,
                'destination': destination,
                'sip_call_id': sip_call_id,
                'from_tag': from_tag,
                'to_tag': None,
                'state': 'CALLING',
                'invite_cseq': 1,
                'rtp_port': rtp_port,
                'remote_rtp_port': None,
                'remote_ip': None,
                'auth_attempts': 0  # Track authentication attempts
            }
            
            # Wait for response
            self._handle_call_responses(call_id, sock)
            
        except Exception as e:
            print(f"Error making call {call_id}: {e}")
            if call_id in self.active_calls:
                del self.active_calls[call_id]
                
    def _create_invite_message(self, account: dict, destination: str, sip_call_id: str, from_tag: str, branch: str, local_port: int, rtp_port: int) -> str:
            """Create SIP INVITE message with SDP"""
            username = account['username']
            domain = account['domain']

            # SDP (Session Description Protocol) for audio — offer PCMU(0) and PCMA(8)
            sdp = f"""v=0
o={username} {random.randint(1000000, 9999999)} {random.randint(1000000, 9999999)} IN IP4 {self.local_ip}
s=SIP Call
c=IN IP4 {self.local_ip}
t=0 0
m=audio {rtp_port} RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""

            content_length = len(sdp)

            message = f"""INVITE sip:{destination}@{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{local_port};branch={branch}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={from_tag}
To: <sip:{destination}@{domain}>
Call-ID: {sip_call_id}
CSeq: 1 INVITE
Contact: <sip:{username}@{self.local_ip}:{local_port}>
Content-Type: application/sdp
Content-Length: {content_length}
User-Agent: EnhancedSipDialer/1.0

{sdp}"""

            return message
        
    def _create_auth_invite_response(self, challenge_response: str, account: dict, call_info: dict) -> str:
        """Create authenticated INVITE message in response to 401"""
        try:
            # Parse challenge
            challenge_line = None
            for line in challenge_response.split('\n'):
                if 'WWW-Authenticate:' in line or 'Proxy-Authenticate:' in line:
                    challenge_line = line
                    break
                    
            if not challenge_line:
                return None
                
            # Extract nonce and realm
            import re
            nonce_match = re.search(r'nonce="([^"]*)"', challenge_line)
            realm_match = re.search(r'realm="([^"]*)"', challenge_line)
            
            if not nonce_match:
                return None
                
            nonce = nonce_match.group(1)
            realm = realm_match.group(1) if realm_match else account['domain']
            
            # Generate new identifiers for authenticated INVITE
            from_tag = str(random.randint(1000000, 9999999))
            branch = f"z9hG4bK{random.randint(100000, 999999)}"
            
            # Create auth header
            auth_header = self._create_auth_header(
                account['username'], account['password'],
                'INVITE', f"sip:{call_info['destination']}@{account['domain']}",
                realm, nonce
            )
            
            if not auth_header:
                return None
                
            # Create authenticated INVITE message
            username = account['username']
            domain = account['domain']
            destination = call_info['destination']
            sip_call_id = call_info['sip_call_id']
            local_port = call_info['rtp_port'] - 1000  # Estimate local port
            rtp_port = call_info['rtp_port']
            
            # SDP (Session Description Protocol) for audio - offer PCMU and PCMA
            sdp = f"""v=0
o={username} {random.randint(1000000, 9999999)} {random.randint(1000000, 9999999)} IN IP4 {self.local_ip}
s=SIP Call
c=IN IP4 {self.local_ip}
t=0 0
m=audio {rtp_port} RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""
            
            content_length = len(sdp)
            
            message = f"""INVITE sip:{destination}@{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{local_port};branch={branch}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={from_tag}
To: <sip:{destination}@{domain}>
Call-ID: {sip_call_id}
CSeq: {call_info['auth_attempts'] + 1} INVITE
Contact: <sip:{username}@{self.local_ip}:{local_port}>
Authorization: {auth_header}
Content-Type: application/sdp
Content-Length: {content_length}
User-Agent: EnhancedSipDialer/1.0

{sdp}"""
            
            return message
            
        except Exception as e:
            print(f"Error creating auth INVITE: {e}")
            return None
            
    def _create_auth_header(self, username: str, password: str, method: str, uri: str, realm: str, nonce: str) -> str:
        """Create digest authentication header"""
        try:
            # MD5 calculation for digest authentication
            ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
            response_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
            
            # Build Authorization header
            auth_header = f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{response_hash}"'
            
            return auth_header
            
        except Exception as e:
            print(f"Error creating auth header: {e}")
            return None
        
    def _handle_call_responses(self, call_id: int, sock: socket.socket):
        """Handle responses during call establishment"""
        if call_id not in self.active_calls:
            return
            
        call_info = self.active_calls[call_id]
        sock.settimeout(30.0)  # 30 second timeout
        
        try:
            while call_info['state'] in ['CALLING', 'RINGING']:
                response_data, addr = sock.recvfrom(4096)
                response = response_data.decode('utf-8')
                
                first_line = response.split('\n')[0] if '\n' in response else response
                print(f"Call {call_id} response: {first_line}")
                
                if "SIP/2.0 100 Trying" in first_line:
                    call_info['state'] = 'TRYING'
                    print(f"Call {call_id}: Trying")
                    
                elif "SIP/2.0 180 Ringing" in first_line or "SIP/2.0 183 Session Progress" in first_line:
                    call_info['state'] = 'RINGING'
                    print(f"Call {call_id}: Ringing")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(call_id, 'RINGING', 'Ringing')
                        
                elif "SIP/2.0 200 OK" in first_line:
                    call_info['state'] = 'ANSWERED'
                    print(f"Call {call_id}: Answered")
                    
                    # Fallback remote IP to responder address; SDP may override
                    call_info['remote_ip'] = addr[0]

                    # Parse SDP from response to get remote RTP info
                    self._parse_sdp_response(call_id, response)
                    
                    # Send ACK
                    ack_msg = self._create_ack_message(call_info)
                    sock.sendto(ack_msg.encode('utf-8'), addr)
                    
                    # Start RTP media with negotiated payload type/codec, only if not already active
                    if call_info['remote_rtp_port'] and call_info['remote_ip'] and not call_info.get('rtp_active'):
                        started = self.rtp_manager.start_rtp_stream(
                            call_id,
                            call_info['account_id'],
                            call_info['rtp_port'],
                            call_info['remote_ip'],
                            call_info['remote_rtp_port'],
                            call_info.get('remote_pt', 0),
                            call_info.get('remote_codec', 'PCMU')
                        )
                        call_info['rtp_active'] = bool(started)
                        if started:
                            # Ensure the main process audio session shows the SIP account name in Volume Mixer
                            try:
                                acct_id = call_info['account_id']
                                username = self.accounts.get(acct_id, {}).get('username', f'Account{acct_id+1}')
                                self.rtp_manager.set_main_process_mixer_name(f"SIP Account {acct_id + 1} ({username})")
                            except Exception:
                                pass
                        
                    call_info['state'] = 'ESTABLISHED'
                    print(f"Call {call_id}: Media established")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(call_id, 'ESTABLISHED', 'Call established')
                        time.sleep(0.1)
                    break
                    
                elif "SIP/2.0 401 Unauthorized" in first_line:
                    # Handle authentication challenge for INVITE
                    call_info['auth_attempts'] += 1
                    
                    if call_info['auth_attempts'] > 2:
                        call_info['state'] = 'FAILED'
                        print(f"Call {call_id}: Too many auth attempts ({call_info['auth_attempts']})")
                        if self.on_call_state_changed:
                            self.on_call_state_changed(call_id, 'FAILED', 'Authentication failed - too many attempts')
                        break
                    
                    print(f"Call {call_id}: Authentication required for INVITE (attempt {call_info['auth_attempts']})")
                    
                    account = self.accounts[call_info['account_id']]
                    auth_response = self._create_auth_invite_response(response, account, call_info)
                    
                    if auth_response:
                        print(f"Call {call_id}: Sending authenticated INVITE...")
                        sock.sendto(auth_response.encode('utf-8'), (account['domain'], account['port']))
                        # Continue waiting for response
                    else:
                        call_info['state'] = 'FAILED'
                        print(f"Call {call_id}: Failed to create auth INVITE")
                        if self.on_call_state_changed:
                            self.on_call_state_changed(call_id, 'FAILED', 'Authentication failed')
                        break
                    
                elif "SIP/2.0 486 Busy Here" in first_line or "SIP/2.0 603 Decline" in first_line:
                    call_info['state'] = 'BUSY'
                    print(f"Call {call_id}: Busy/Declined")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(call_id, 'BUSY', 'Busy')
                    break
                    
                elif "SIP/2.0 408 Request Timeout" in first_line:
                    call_info['state'] = 'TIMEOUT'
                    print(f"Call {call_id}: 408 Request Timeout - server didn't respond in time")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(call_id, 'TIMEOUT', '408 Request Timeout')
                    break
                    
                elif "SIP/2.0 404 Not Found" in first_line:
                    call_info['state'] = 'FAILED'
                    print(f"Call {call_id}: 404 Not Found - destination doesn't exist")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(call_id, 'FAILED', '404 Not Found')
                    break
                    
                elif first_line.startswith("SIP/2.0 4") or first_line.startswith("SIP/2.0 5") or first_line.startswith("SIP/2.0 6"):
                    call_info['state'] = 'FAILED'
                    print(f"Call {call_id}: Failed - {first_line}")
                    if self.on_call_state_changed:
                        self.on_call_state_changed(call_id, 'FAILED', f'Failed: {first_line}')
                    break
                    
        except socket.timeout:
            call_info['state'] = 'TIMEOUT'
            print(f"Call {call_id}: Timeout")
            if self.on_call_state_changed:
                self.on_call_state_changed(call_id, 'TIMEOUT', 'Call timeout')
                
        except Exception as e:
            call_info['state'] = 'ERROR'
            print(f"Call {call_id}: Error - {e}")
            if self.on_call_state_changed:
                self.on_call_state_changed(call_id, 'ERROR', f'Error: {e}')
                
    def _parse_sdp_response(self, call_id: int, response: str):
        """Parse SDP from 200 OK response to get remote media info and negotiated codec"""
        if call_id not in self.active_calls:
            return
            
        call_info = self.active_calls[call_id]
        # Parse To-tag and CSeq for ACK correctness
        try:
            for line in response.split('\n')[:40]:
                line = line.strip()
                if line.startswith('To:') and 'tag=' in line:
                    # extract tag= value
                    m = re.search(r'tag=([^;>\s]+)', line)
                    if m:
                        call_info['to_tag'] = m.group(1)
                elif line.startswith('CSeq:'):
                    # format: CSeq: <num> INVITE
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        call_info['invite_cseq'] = int(parts[1])
        except Exception:
            pass
        
        # Extract SDP section
        sdp_start = response.find('\r\n\r\n')
        if sdp_start == -1:
            return
            
        sdp = response[sdp_start + 4:]
        
        # Parse SDP lines
        pts = []
        rtpmap = {}
        for line in sdp.split('\n'):
            line = line.strip()
            if line.startswith('c=IN IP4 '):
                # Connection info; prefer public IP, otherwise keep existing (likely addr[0])
                ip = line.split()[-1]
                if self._is_public_ip(ip):
                    call_info['remote_ip'] = ip
            elif line.startswith('m=audio '):
                # Media line: m=audio port RTP/AVP ...
                parts = line.split()
                if len(parts) >= 2:
                    call_info['remote_rtp_port'] = int(parts[1])
                    if len(parts) > 3:
                        for tok in parts[3:]:
                            if tok.isdigit():
                                pts.append(int(tok))
            elif line.startswith('a=rtpmap:'):
                try:
                    after = line.split(':', 1)[1]
                    pt_str, rest = after.split(None, 1)
                    pt = int(pt_str)
                    codec = rest.split('/')[0].upper()
                    rtpmap[pt] = codec
                except Exception:
                    pass

        # Choose codec for outgoing media: prefer PCMU else PCMA if offered
        if pts:
            if 0 in pts:
                call_info['remote_pt'] = 0
                call_info['remote_codec'] = rtpmap.get(0, 'PCMU')
            elif 8 in pts:
                call_info['remote_pt'] = 8
                call_info['remote_codec'] = rtpmap.get(8, 'PCMA')

        print(f"Call {call_id}: Remote RTP {call_info.get('remote_ip')}:{call_info.get('remote_rtp_port')} PT={call_info.get('remote_pt','?')} Codec={call_info.get('remote_codec','?')}")
        
    def _create_ack_message(self, call_info: dict) -> str:
        """Create ACK message for established call"""
        account = self.accounts[call_info['account_id']]
        username = account['username']
        domain = account['domain']
        cseq_num = call_info.get('invite_cseq', 1)

        message = f"""ACK sip:{call_info['destination']}@{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:5060;branch=z9hG4bK{random.randint(100000, 999999)}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={call_info['from_tag']}
To: <sip:{call_info['destination']}@{domain}>;tag={call_info['to_tag']}
Call-ID: {call_info['sip_call_id']}
CSeq: {cseq_num} ACK
Content-Length: 0

"""
        return message
        
    def hangup_call(self, call_id: int) -> bool:
        """Hangup an active call"""
        if call_id not in self.active_calls:
            print(f"Call {call_id} not found")
            return False
            
        call_info = self.active_calls[call_id]
        
        # Stop RTP stream
        self.rtp_manager.stop_rtp_stream(call_id)
        
        # Send BYE message if call was established
        if call_info['state'] == 'ESTABLISHED':
            account_id = call_info['account_id']
            sock = self.sockets.get(account_id)
            if sock:
                bye_msg = self._create_bye_message(call_info)
                account = self.accounts[account_id]
                sock.sendto(bye_msg.encode('utf-8'), (account['domain'], account['port']))
                
        # Remove call
        del self.active_calls[call_id]
        print(f"Call {call_id} hung up")
        
        if self.on_call_state_changed:
            self.on_call_state_changed(call_id, 'TERMINATED', 'Call terminated')
            
        return True

    # -------- Deferred Answer Support --------
    def answer_incoming_call(self, internal_id: int) -> bool:
        """Send 200 OK for a deferred incoming call (if still ringing) and mark answered.
        Returns True if 200 OK sent.
        """
        call_info = self.active_calls.get(internal_id)
        if not call_info:
            print(f"Deferred answer: call {internal_id} not found")
            return False
        if call_info.get('state') not in ('RINGING', 'ANSWERING'):
            print(f"Deferred answer: call {internal_id} state {call_info.get('state')} not ringable")
            return False
        account_id = call_info['account_id']
        sock = self.sockets.get(account_id)
        if not sock:
            print(f"Deferred answer: no socket for account {account_id}")
            return False
        try:
            msg = call_info.get('raw_invite')
            if not msg:
                print(f"Deferred answer: missing raw INVITE for call {internal_id}")
                return False
            ok_msg = self._create_200ok_with_sdp(
                msg,
                call_info['rtp_port'],
                call_info.get('remote_pt', 0),
                call_info.get('remote_codec', 'PCMU')
            )
            # Use original source address (addr) instead of guessing port
            sip_addr = call_info.get('sip_addr')
            if not sip_addr:
                sip_addr = (call_info['remote_ip'], self.accounts[account_id]['port'])
            sock.sendto(ok_msg.encode('utf-8'), sip_addr)
            call_info['state'] = 'ANSWERED'
            call_info['answered_ts'] = time.time()
            print(f"\u2705 Deferred 200 OK sent for call {internal_id}; waiting for ACK")
            if self.on_call_state_changed:
                self.on_call_state_changed(internal_id, 'ANSWERED', 'Answered (deferred)')
            return True
        except Exception as e:
            print(f"Deferred answer error call {internal_id}: {e}")
            return False
        
    def _create_bye_message(self, call_info: dict) -> str:
        """Create BYE message to terminate call"""
        account = self.accounts[call_info['account_id']]
        username = account['username']
        domain = account['domain']
        
        message = f"""BYE sip:{call_info['destination']}@{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:5060;branch=z9hG4bK{random.randint(100000, 999999)}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={call_info['from_tag']}
To: <sip:{call_info['destination']}@{domain}>;tag={call_info['to_tag']}
Call-ID: {call_info['sip_call_id']}
CSeq: 2 BYE
Content-Length: 0

"""
        return message
        
    def get_active_calls(self) -> List[dict]:
        """Get list of active calls with detailed info"""
        calls = []
        for call_id, call_info in self.active_calls.items():
            calls.append({
                'id': call_id,
                'account_id': call_info['account_id'],
                'destination': call_info['destination'],
                'state': call_info['state'],
                'rtp_active': call_id in self.rtp_manager.active_streams
            })
        return calls

# Test the enhanced SIP manager
if __name__ == "__main__":
    def on_call_state(call_id, state, state_text):
        print(f"Call state changed: {call_id} -> {state}: {state_text}")
        
    def on_reg_changed(account_id, registered, status_code):
        print(f"Registration: Account {account_id}, Registered: {registered}")
        
    manager = EnhancedSipManager()
    manager.on_call_state_changed = on_call_state
    manager.on_registration_state_changed = on_reg_changed
    
    if manager.initialize():
        print("Enhanced SIP Manager initialized")
        
        # Test configuration
        config = {
            'username': 'JEFF01',
            'password': '112233',
            'domain': '52.64.207.38',
            'port': 5060
        }
        
        if manager.add_account(0, config):
            print("Account added")
            if manager.register_account(0):
                print("Registration initiated")
                
                # Wait for registration
                time.sleep(5)
                
                if 0 in manager.registered_accounts:
                    print("Account registered, ready for calls")
                    
                    # Test call (replace with actual destination)
                    # call_id = manager.make_call(0, "test_number")
                    # if call_id:
                    #     print(f"Call initiated: {call_id}")
                    #     time.sleep(10)
                    #     manager.hangup_call(call_id)
                    
                input("Press Enter to shutdown...")
                
        manager.shutdown()
    else:
        print("Failed to initialize Enhanced SIP Manager")
