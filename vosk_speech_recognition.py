#!/usr/bin/env python3
"""
Advanced Speech Recognition Auto Answer System using Vosk
Uses Vosk for real speech recognition instead of simple volume detection
"""

import json
import os
import queue
import sys
import threading
import time
import logging
from typing import Optional, Callable, List, Dict

try:
    import sounddevice as sd
    import vosk
    import numpy as np
except ImportError as e:
    print(f"❌ Missing required module: {e}")
    print("Install with: pip install vosk sounddevice numpy")
    sys.exit(1)

class VoskSpeechRecognizer:
    """
    Advanced speech recognition using Vosk for SIP auto-answer
    Detects actual speech content and can respond to specific phrases
    """
    
    def __init__(self, sip_manager, incoming_call_handler):
        self.sip_manager = sip_manager
        self.incoming_call_handler = incoming_call_handler
        
        # Audio parameters
        self.sample_rate = 16000  # Vosk works best with 16kHz
        self.channels = 1
        self.blocksize = 4000     # Larger block for better recognition
        
        # Speech recognition
        self.model = None
        self.recognizer = None
        self.audio_queue = queue.Queue()
        
        # Trigger phrases for auto-answer
        self.trigger_phrases = [
            "hello", "hi", "answer", "yes", "okay", "ok", 
            "pick up", "take it", "get it", "phone"
        ]
        
        # State management
        self.is_listening = False
        self.is_speech_detected = False
        self.pending_calls = {}
        self.recognition_thread = None
        self.audio_stream = None
        
        # Callbacks
        self.on_speech_detected = None
        self.on_speech_recognized = None
        self.on_trigger_phrase = None
        
        # Statistics
        self.total_recognitions = 0
        self.trigger_activations = 0
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Hook into incoming calls
        self._setup_call_hooks()
        
    def _setup_call_hooks(self):
        """Setup hooks to intercept incoming calls"""
        self.original_on_incoming_call = self.incoming_call_handler.on_incoming_call
        self.incoming_call_handler.on_incoming_call = self._on_incoming_call_with_speech
        
    def initialize_vosk(self, model_path: str = None) -> bool:
        """
        Initialize Vosk speech recognition model
        
        Args:
            model_path: Path to Vosk model directory, or None to download small model
        """
        try:
            if model_path and os.path.exists(model_path):
                self.logger.info(f"Loading Vosk model from: {model_path}")
                self.model = vosk.Model(model_path)
            else:
                self.logger.info("Downloading Vosk small model...")
                # Download small English model (~40MB)
                self.model = vosk.Model(lang="en-us")
                
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            self.logger.info("✅ Vosk speech recognition initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Vosk: {e}")
            return False
            
    def _on_incoming_call_with_speech(self, account_id: int, call_id: str, from_user: str, addr):
        """Handle incoming call with speech recognition"""
        self.logger.info(f"📞 Incoming call: {call_id} from {from_user}")
        
        # Add to pending calls
        self.pending_calls[call_id] = {
            'account_id': account_id,
            'from_user': from_user,
            'addr': addr,
            'timestamp': time.time()
        }
        
        # Start speech recognition if not running
        if not self.is_listening:
            self.start_speech_recognition()
            
        # Call original callback
        if self.original_on_incoming_call:
            self.original_on_incoming_call(account_id, call_id, from_user, addr)
            
    def start_speech_recognition(self) -> bool:
        """Start speech recognition system"""
        if self.is_listening:
            return True
            
        if not self.model:
            self.logger.error("❌ Vosk model not initialized. Call initialize_vosk() first.")
            return False
            
        try:
            self.is_listening = True
            self.logger.info("🎤 Starting speech recognition...")
            
            # Start audio stream
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=self.blocksize,
                callback=self._audio_callback
            )
            
            # Start recognition processing thread
            self.recognition_thread = threading.Thread(
                target=self._recognition_loop,
                daemon=True
            )
            self.recognition_thread.start()
            
            # Start audio stream
            self.audio_stream.start()
            
            self.logger.info("✅ Speech recognition started")
            self.logger.info(f"🎯 Listening for trigger phrases: {', '.join(self.trigger_phrases)}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start speech recognition: {e}")
            self.stop_speech_recognition()
            return False
            
    def stop_speech_recognition(self):
        """Stop speech recognition system"""
        self.is_listening = False
        self.logger.info("🛑 Stopping speech recognition...")
        
        try:
            if self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
                
        except Exception as e:
            self.logger.error(f"Error stopping speech recognition: {e}")
            
    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream"""
        if status:
            self.logger.warning(f"Audio status: {status}")
            
        if self.is_listening:
            # Convert to the format Vosk expects
            audio_data = indata.flatten().tobytes()
            try:
                self.audio_queue.put_nowait(audio_data)
            except queue.Full:
                # If queue is full, remove oldest and add new
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(audio_data)
                except:
                    pass
                    
    def _recognition_loop(self):
        """Main speech recognition processing loop"""
        self.logger.info("🔍 Speech recognition processing started")
        
        while self.is_listening:
            try:
                # Get audio data with timeout
                audio_data = self.audio_queue.get(timeout=0.1)
                
                # Process with Vosk
                if self.recognizer.AcceptWaveform(audio_data):
                    # Final recognition result
                    result = json.loads(self.recognizer.Result())
                    text = result.get('text', '').lower().strip()
                    
                    if text:
                        self._process_recognized_speech(text)
                        
                else:
                    # Partial recognition result
                    partial = json.loads(self.recognizer.PartialResult())
                    partial_text = partial.get('partial', '').lower().strip()
                    
                    if partial_text:
                        self._process_partial_speech(partial_text)
                        
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Recognition error: {e}")
                
    def _process_recognized_speech(self, text: str):
        """Process final recognized speech"""
        self.total_recognitions += 1
        self.logger.info(f"🗣️ Recognized: '{text}'")
        
        # Call user callback
        if self.on_speech_recognized:
            self.on_speech_recognized(text)
            
        # Check for trigger phrases
        self._check_trigger_phrases(text)
        
    def _process_partial_speech(self, text: str):
        """Process partial speech recognition"""
        # Only log if significant partial text
        if len(text) > 2:
            self.logger.debug(f"🎤 Partial: '{text}'")
            
        # Check partial text for immediate triggers
        if any(phrase in text for phrase in ['hello', 'hi', 'answer']):
            self._check_trigger_phrases(text)
            
    def _check_trigger_phrases(self, text: str):
        """Check if recognized text contains trigger phrases"""
        triggered_phrases = [phrase for phrase in self.trigger_phrases if phrase in text]
        
        if triggered_phrases:
            self.trigger_activations += 1
            self.logger.info(f"🎯 TRIGGER DETECTED: '{triggered_phrases[0]}' in '{text}'")
            
            # Mark speech as detected
            self.is_speech_detected = True
            
            # Auto-answer pending calls
            self._answer_pending_calls(triggered_phrase=triggered_phrases[0])
            
            # Call user callbacks
            if self.on_speech_detected:
                self.on_speech_detected()
                
            if self.on_trigger_phrase:
                self.on_trigger_phrase(triggered_phrases[0], text)
                
    def _answer_pending_calls(self, triggered_phrase: str = None):
        """Answer all pending calls when speech trigger detected"""
        answered_calls = []
        
        for call_id, call_info in self.pending_calls.items():
            try:
                success = self.incoming_call_handler.answer_call(call_id)
                if success:
                    trigger_info = f" (triggered by '{triggered_phrase}')" if triggered_phrase else ""
                    self.logger.info(f"✅ Auto-answered call {call_id} from {call_info['from_user']}{trigger_info}")
                    answered_calls.append(call_id)
                else:
                    self.logger.warning(f"⚠️ Failed to answer call {call_id}")
                    
            except Exception as e:
                self.logger.error(f"❌ Error answering call {call_id}: {e}")
                
        # Remove answered calls
        for call_id in answered_calls:
            del self.pending_calls[call_id]
            
        # Reset speech detection flag after short delay
        if answered_calls:
            threading.Timer(3.0, self._reset_speech_detection).start()
            
    def _reset_speech_detection(self):
        """Reset speech detection flag"""
        self.is_speech_detected = False
        
    def add_trigger_phrase(self, phrase: str):
        """Add a new trigger phrase for auto-answer"""
        if phrase.lower() not in self.trigger_phrases:
            self.trigger_phrases.append(phrase.lower())
            self.logger.info(f"➕ Added trigger phrase: '{phrase}'")
            
    def remove_trigger_phrase(self, phrase: str):
        """Remove a trigger phrase"""
        if phrase.lower() in self.trigger_phrases:
            self.trigger_phrases.remove(phrase.lower())
            self.logger.info(f"➖ Removed trigger phrase: '{phrase}'")
            
    def set_trigger_phrases(self, phrases: List[str]):
        """Set custom trigger phrases"""
        self.trigger_phrases = [phrase.lower() for phrase in phrases]
        self.logger.info(f"🎯 Set trigger phrases: {', '.join(self.trigger_phrases)}")
        
    def cleanup_old_calls(self, max_age_seconds: float = 30):
        """Remove old pending calls"""
        current_time = time.time()
        old_calls = [
            call_id for call_id, call_info in self.pending_calls.items()
            if (current_time - call_info['timestamp']) > max_age_seconds
        ]
        
        for call_id in old_calls:
            del self.pending_calls[call_id]
            if old_calls:
                self.logger.info(f"🗑️ Removed {len(old_calls)} old pending calls")
                
    def get_status(self) -> Dict:
        """Get current system status"""
        return {
            'is_listening': self.is_listening,
            'is_speech_detected': self.is_speech_detected,
            'pending_calls': len(self.pending_calls),
            'trigger_phrases': self.trigger_phrases,
            'total_recognitions': self.total_recognitions,
            'trigger_activations': self.trigger_activations,
            'model_loaded': self.model is not None,
            'audio_queue_size': self.audio_queue.qsize()
        }
        
    def get_statistics(self) -> Dict:
        """Get recognition statistics"""
        return {
            'total_recognitions': self.total_recognitions,
            'trigger_activations': self.trigger_activations,
            'success_rate': (self.trigger_activations / max(1, self.total_recognitions)) * 100
        }


class VoskAutoAnswerManager:
    """
    Complete auto-answer system using Vosk speech recognition
    """
    
    def __init__(self, sip_manager, incoming_call_handler):
        self.sip_manager = sip_manager
        self.incoming_call_handler = incoming_call_handler
        self.speech_recognizer = VoskSpeechRecognizer(sip_manager, incoming_call_handler)
        
        self.logger = logging.getLogger(__name__)
        
    def initialize(self, model_path: str = None, custom_phrases: List[str] = None) -> bool:
        """
        Initialize the Vosk auto-answer system
        
        Args:
            model_path: Path to Vosk model (None to download)
            custom_phrases: Custom trigger phrases for auto-answer
        """
        try:
            # Initialize Vosk
            if not self.speech_recognizer.initialize_vosk(model_path):
                return False
                
            # Set custom trigger phrases if provided
            if custom_phrases:
                self.speech_recognizer.set_trigger_phrases(custom_phrases)
                
            # Setup callbacks
            self.speech_recognizer.on_speech_detected = self._on_speech_detected
            self.speech_recognizer.on_speech_recognized = self._on_speech_recognized
            self.speech_recognizer.on_trigger_phrase = self._on_trigger_phrase
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Vosk auto-answer: {e}")
            return False
            
    def _on_speech_detected(self):
        """Callback when speech trigger is detected"""
        self.logger.info("🎯 Speech trigger detected - auto-answering calls!")
        
    def _on_speech_recognized(self, text: str):
        """Callback when speech is recognized"""
        self.logger.debug(f"📝 Speech: {text}")
        
    def _on_trigger_phrase(self, phrase: str, full_text: str):
        """Callback when specific trigger phrase detected"""
        self.logger.info(f"🔥 Trigger '{phrase}' detected in: '{full_text}'")
        
    def start(self) -> bool:
        """Start the complete auto-answer system"""
        return self.speech_recognizer.start_speech_recognition()
        
    def stop(self):
        """Stop the auto-answer system"""
        self.speech_recognizer.stop_speech_recognition()
        
    def get_status(self):
        """Get comprehensive status"""
        return self.speech_recognizer.get_status()


if __name__ == "__main__":
    print("🎤 Vosk Speech Recognition Module")
    print("This module provides advanced speech recognition for SIP auto-answer")
    print("Use intelligent_sip_dialer.py or run_vosk_dialer.py to start the system")