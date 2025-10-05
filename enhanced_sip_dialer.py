#!/usr/bin/env python3
"""
Enhanced SIP Dialer with Voice Detection Auto Answer
Integrates voice detection with existing SIP components for automatic call answering
"""

import sys
import os
import time
import logging
from typing import Optional

# Import existing SIP components
try:
    from working_sip_manager import WorkingSipManager
    from incoming_call_handler import IncomingCallHandler  
    from voice_detection_auto_answer import VoiceDetectionAutoAnswer, AlwaysRingingManager
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure all required modules are available")
    sys.exit(1)

class EnhancedSipDialer:
    """
    Enhanced SIP Dialer with voice detection and auto-answer capabilities
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Initialize SIP components
        self.sip_manager = WorkingSipManager()
        self.incoming_call_handler = IncomingCallHandler(self.sip_manager)
        
        # Initialize voice detection and always ringing
        self.voice_detector = VoiceDetectionAutoAnswer(
            self.sip_manager, 
            self.incoming_call_handler
        )
        self.always_ringing = AlwaysRingingManager(self.sip_manager)
        
        # Status tracking
        self.is_running = False
        self.accounts_configured = False
        
        # Setup callbacks
        self._setup_callbacks()
        
    def _setup_callbacks(self):
        """Setup callbacks for voice detection events"""
        self.voice_detector.on_voice_detected = self._on_voice_detected
        self.voice_detector.on_voice_stopped = self._on_voice_stopped
        
        # Setup SIP callbacks
        self.sip_manager.on_registration_state_changed = self._on_registration_changed
        
    def _on_voice_detected(self):
        """Callback when human voice is detected"""
        self.logger.info("🗣️ Voice detected - ready to auto-answer calls!")
        
    def _on_voice_stopped(self):
        """Callback when voice stops"""
        self.logger.info("🤐 Voice stopped")
        
    def _on_registration_changed(self, account_id: int, is_registered: bool):
        """Callback when SIP registration state changes"""
        status = "✅ REGISTERED" if is_registered else "❌ UNREGISTERED"
        self.logger.info(f"Account {account_id}: {status}")
        
        if is_registered:
            # Start listening for incoming calls on this account
            self.incoming_call_handler.start_listening(account_id)
            
    def add_sip_account(self, account_id: int, username: str, password: str, 
                       server: str, port: int = 5060) -> bool:
        """Add and register a SIP account"""
        try:
            # Add account to SIP manager
            success = self.sip_manager.add_account(
                account_id=account_id,
                username=username, 
                password=password,
                server=server,
                port=port
            )
            
            if success:
                self.logger.info(f"✅ Added SIP account {account_id} ({username}@{server})")
                self.accounts_configured = True
                return True
            else:
                self.logger.error(f"❌ Failed to add SIP account {account_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error adding account {account_id}: {e}")
            return False
            
    def start_enhanced_dialer(self):
        """Start the enhanced SIP dialer with voice detection"""
        if self.is_running:
            self.logger.warning("Enhanced SIP dialer is already running")
            return False
            
        if not self.accounts_configured:
            self.logger.error("❌ No SIP accounts configured. Please add accounts first.")
            return False
            
        try:
            self.logger.info("🚀 Starting Enhanced SIP Dialer...")
            
            # 1. Initialize SIP manager
            if not self.sip_manager.initialize():
                raise Exception("Failed to initialize SIP manager")
                
            # 2. Start always ringing mode
            self.always_ringing.start_always_ringing()
            
            # 3. Start voice detection system
            self.voice_detector.start_voice_detection()
            
            self.is_running = True
            self.logger.info("✅ Enhanced SIP Dialer started successfully!")
            self.logger.info("📞 System is ready to auto-answer calls when voice is detected")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start enhanced dialer: {e}")
            self.stop_enhanced_dialer()
            return False
            
    def stop_enhanced_dialer(self):
        """Stop the enhanced SIP dialer"""
        if not self.is_running:
            return
            
        self.logger.info("🛑 Stopping Enhanced SIP Dialer...")
        
        try:
            # Stop voice detection
            self.voice_detector.stop_voice_detection()
            
            # Stop always ringing
            self.always_ringing.stop_always_ringing()
            
            # Stop SIP manager  
            self.sip_manager.shutdown()
            
            self.is_running = False
            self.logger.info("✅ Enhanced SIP Dialer stopped")
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping dialer: {e}")
            
    def configure_voice_sensitivity(self, threshold_db: float = -30, 
                                  min_duration: float = 0.5):
        """
        Configure voice detection sensitivity
        
        Args:
            threshold_db: Voice detection threshold (-40 = more sensitive, -20 = less sensitive)
            min_duration: Minimum voice duration before triggering auto-answer
        """
        self.voice_detector.set_voice_detection_sensitivity(threshold_db, min_duration)
        self.logger.info(f"Voice sensitivity configured: {threshold_db}dB, {min_duration}s")
        
    def get_system_status(self) -> dict:
        """Get comprehensive system status"""
        voice_status = self.voice_detector.get_status()
        
        return {
            'is_running': self.is_running,
            'accounts_configured': self.accounts_configured,
            'registered_accounts': list(self.sip_manager.registered_accounts),
            'voice_detection': voice_status,
            'always_ringing_active': self.always_ringing.is_running,
            'pending_calls': len(self.voice_detector.pending_calls)
        }
        
    def print_status(self):
        """Print current system status"""
        status = self.get_system_status()
        
        print("\n" + "="*60)
        print("📞 ENHANCED SIP DIALER STATUS")
        print("="*60)
        print(f"🚀 System Running: {'✅ YES' if status['is_running'] else '❌ NO'}")
        print(f"📋 Accounts Configured: {'✅ YES' if status['accounts_configured'] else '❌ NO'}")
        print(f"📡 Registered Accounts: {status['registered_accounts']}")
        print(f"📳 Always Ringing: {'✅ ACTIVE' if status['always_ringing_active'] else '❌ INACTIVE'}")
        print(f"🎤 Voice Detection: {'✅ LISTENING' if status['voice_detection']['is_listening'] else '❌ STOPPED'}")
        print(f"🗣️ Voice Detected: {'✅ YES' if status['voice_detection']['is_voice_detected'] else '❌ NO'}")
        print(f"📞 Pending Calls: {status['pending_calls']}")
        print(f"🔊 Voice Threshold: {status['voice_detection']['threshold_db']}dB")
        print("="*60)


def main():
    """Main function to demonstrate the enhanced SIP dialer"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create enhanced dialer
    dialer = EnhancedSipDialer()
    
    print("🚀 ENHANCED SIP DIALER WITH VOICE DETECTION")
    print("=" * 50)
    
    try:
        # Example configuration - modify these for your SIP accounts
        print("\n📋 Configuring SIP accounts...")
        
        # Add your SIP accounts here
        # Example:
        # dialer.add_sip_account(
        #     account_id=1,
        #     username="1001", 
        #     password="your_password",
        #     server="your_sip_server.com"
        # )
        
        print("⚠️  Please configure your SIP accounts in the main() function")
        print("    Example:")
        print("    dialer.add_sip_account(1, '1001', 'password', 'server.com')")
        
        # Configure voice detection sensitivity  
        print("\n🎤 Configuring voice detection...")
        dialer.configure_voice_sensitivity(threshold_db=-30, min_duration=0.5)
        
        # Uncomment the following lines after configuring accounts:
        
        # # Start the enhanced dialer
        # print("\\n🚀 Starting enhanced dialer...")
        # if dialer.start_enhanced_dialer():
        #     print("\\n✅ System ready! The SIP dialer will:")
        #     print("   📳 Stay always ringing (ready for calls)")  
        #     print("   🎤 Listen for your voice")
        #     print("   📞 Auto-answer calls when you speak")
        #     
        #     # Keep running and show status
        #     while True:
        #         time.sleep(10)
        #         dialer.print_status()
        #         
        #         # Clean up old pending calls
        #         dialer.voice_detector.cleanup_old_pending_calls()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        dialer.stop_enhanced_dialer()
        print("👋 Goodbye!")


if __name__ == "__main__":
    main()