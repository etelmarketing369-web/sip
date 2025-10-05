#!/usr/bin/env python3
"""
SIP Dialer Always Ringing with Voice Detection Auto Answer
Main integration script that combines your existing SIP system with voice detection
"""

import sys
import os
import time
import logging
import threading
from typing import Optional

# Import your existing SIP components
try:
    from working_sip_manager import WorkingSipManager
    from incoming_call_handler import IncomingCallHandler
    from simple_voice_detection import SimpleVoiceDetector, SimpleAlwaysRinging
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure all SIP components are in the same directory")
    sys.exit(1)


class SipDialerAutoAnswer:
    """
    Complete SIP Dialer system with:
    - Always ringing mode (stays ready for calls)  
    - Voice detection from microphone
    - Automatic call answering when voice detected
    """
    
    def __init__(self, config_path: str = None):
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.sip_manager = WorkingSipManager()
        self.call_handler = IncomingCallHandler(self.sip_manager) 
        self.voice_detector = SimpleVoiceDetector(self.sip_manager, self.call_handler)
        self.always_ringing = SimpleAlwaysRinging(self.sip_manager)
        
        # State
        self.is_running = False
        self.config_path = config_path
        
        # Setup callbacks
        self._setup_callbacks()
        
    def _setup_callbacks(self):
        """Setup all callback functions"""
        # SIP registration callbacks
        self.sip_manager.on_registration_state_changed = self._on_registration_changed
        
        # Voice detection callbacks
        self.voice_detector.on_voice_detected = self._on_voice_detected
        self.voice_detector.on_voice_stopped = self._on_voice_stopped
        
    def _on_registration_changed(self, account_id: int, is_registered: bool):
        """Handle SIP registration state changes"""
        status = "REGISTERED ✅" if is_registered else "UNREGISTERED ❌"
        self.logger.info(f"Account {account_id}: {status}")
        
        if is_registered:
            # Start listening for incoming calls on this account
            self.call_handler.start_listening(account_id)
            self.logger.info(f"📞 Now listening for calls on account {account_id}")
            
    def _on_voice_detected(self):
        """Handle voice detection"""
        self.logger.info("🗣️ VOICE DETECTED - Ready to auto-answer incoming calls!")
        
    def _on_voice_stopped(self):
        """Handle voice stopped"""
        self.logger.info("🤐 Voice stopped")
        
    def add_sip_account(self, account_id: int, username: str, password: str, 
                       server: str, port: int = 5060, local_port: int = None) -> bool:
        """
        Add and register a SIP account
        
        Args:
            account_id: Unique account ID (1, 2, 3, etc.)
            username: SIP username  
            password: SIP password
            server: SIP server hostname/IP
            port: SIP server port (default 5060)
            local_port: Local port to bind (default 5060 + account_id)
        """
        try:
            if local_port is None:
                local_port = 5060 + account_id
                
            success = self.sip_manager.add_account(
                account_id=account_id,
                username=username,
                password=password, 
                server=server,
                port=port,
                local_port=local_port
            )
            
            if success:
                self.logger.info(f"✅ Added account {account_id}: {username}@{server}:{port}")
                return True
            else:
                self.logger.error(f"❌ Failed to add account {account_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error adding account {account_id}: {e}")
            return False
            
    def start_system(self) -> bool:
        """Start the complete SIP dialer system"""
        if self.is_running:
            self.logger.warning("System already running")
            return True
            
        try:
            self.logger.info("🚀 STARTING SIP DIALER AUTO ANSWER SYSTEM")
            self.logger.info("=" * 60)
            
            # 1. Initialize SIP manager
            self.logger.info("📡 Initializing SIP manager...")
            if not self.sip_manager.initialize():
                raise Exception("Failed to initialize SIP manager")
                
            # 2. Start always ringing mode
            self.logger.info("📳 Starting always ringing mode...")
            self.always_ringing.start()
            
            # 3. Start voice detection
            self.logger.info("🎤 Starting voice detection...")
            self.voice_detector.start_voice_detection()
            
            self.is_running = True
            
            self.logger.info("✅ SYSTEM STARTED SUCCESSFULLY!")
            self.logger.info("📞 SIP Dialer is now:")
            self.logger.info("   📳 Always ringing (ready for incoming calls)")
            self.logger.info("   🎤 Listening for your voice")  
            self.logger.info("   🤖 Will auto-answer calls when you speak")
            self.logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start system: {e}")
            self.stop_system()
            return False
            
    def stop_system(self):
        """Stop the complete system"""
        if not self.is_running:
            return
            
        self.logger.info("🛑 STOPPING SIP DIALER SYSTEM...")
        
        try:
            # Stop voice detection
            self.voice_detector.stop_voice_detection()
            
            # Stop always ringing
            self.always_ringing.stop()
            
            # Shutdown SIP manager
            self.sip_manager.shutdown()
            
            self.is_running = False
            self.logger.info("✅ System stopped successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping system: {e}")
            
    def configure_voice_sensitivity(self, volume_threshold: int = 1000, 
                                  min_voice_duration: float = 0.5):
        """
        Configure voice detection sensitivity
        
        Args:
            volume_threshold: Higher = less sensitive (500-3000 typical range)
            min_voice_duration: Minimum voice duration to trigger auto-answer
        """
        self.voice_detector.set_sensitivity(volume_threshold, min_voice_duration)
        self.logger.info(f"🎤 Voice sensitivity configured: "
                        f"threshold={volume_threshold}, duration={min_voice_duration}s")
        
    def get_system_status(self) -> dict:
        """Get comprehensive system status"""
        voice_status = self.voice_detector.get_status()
        
        return {
            'system_running': self.is_running,
            'registered_accounts': list(self.sip_manager.registered_accounts),
            'always_ringing': self.always_ringing.is_running,
            'voice_detection': voice_status,
            'pending_calls': len(self.voice_detector.pending_calls)
        }
        
    def print_status(self):
        """Print detailed system status"""
        status = self.get_system_status()
        
        print("\n" + "=" * 70)
        print("📞 SIP DIALER AUTO ANSWER - SYSTEM STATUS")
        print("=" * 70)
        
        # System status
        running_status = "🟢 RUNNING" if status['system_running'] else "🔴 STOPPED"
        print(f"System Status: {running_status}")
        
        # Account status  
        if status['registered_accounts']:
            print(f"Registered Accounts: {status['registered_accounts']} ✅")
        else:
            print("Registered Accounts: None ❌")
            
        # Always ringing status
        ringing_status = "🟢 ACTIVE" if status['always_ringing'] else "🔴 INACTIVE" 
        print(f"Always Ringing: {ringing_status}")
        
        # Voice detection status
        voice_listening = "🟢 LISTENING" if status['voice_detection']['is_listening'] else "🔴 STOPPED"
        voice_detected = "🗣️ SPEAKING" if status['voice_detection']['is_voice_detected'] else "🤐 SILENT"
        print(f"Voice Detection: {voice_listening}")
        print(f"Current Voice State: {voice_detected}")
        print(f"Voice Threshold: {status['voice_detection']['volume_threshold']}")
        
        # Call status
        print(f"Pending Calls: {status['pending_calls']}")
        
        print("=" * 70)
        
    def run_interactive_mode(self):
        """Run in interactive mode with status updates"""
        if not self.is_running:
            self.logger.error("❌ System not running. Call start_system() first.")
            return
            
        try:
            self.logger.info("🎮 Entering interactive mode...")
            self.logger.info("Press Ctrl+C to stop")
            
            while True:
                # Print status every 10 seconds
                self.print_status()
                
                # Cleanup old calls
                self.voice_detector._cleanup_old_calls()
                
                # Wait 10 seconds
                time.sleep(10)
                
        except KeyboardInterrupt:
            self.logger.info("\n⏹️ Stopping system...")
            self.stop_system()


def main():
    """Main function with example configuration"""
    print("🚀 SIP DIALER AUTO ANSWER SYSTEM")
    print("=" * 50)
    
    # Create the system
    dialer = SipDialerAutoAnswer()
    
    try:
        # Example SIP account configuration
        # MODIFY THESE VALUES FOR YOUR SIP ACCOUNTS:
        
        print("📋 Example SIP Account Configuration:")
        print("   (Modify these values in main() function)")
        print()
        
        # Uncomment and modify these lines for your accounts:
        
        # dialer.add_sip_account(
        #     account_id=1,
        #     username="1001",           # Your SIP username
        #     password="your_password",  # Your SIP password  
        #     server="your.sip.server.com", # Your SIP server
        #     port=5060                  # SIP server port
        # )
        
        # dialer.add_sip_account(
        #     account_id=2, 
        #     username="1002",
        #     password="your_password2",
        #     server="your.sip.server.com",
        #     port=5060
        # )
        
        # Configure voice detection sensitivity
        print("🎤 Configuring voice detection...")
        dialer.configure_voice_sensitivity(
            volume_threshold=1000,  # Adjust based on your microphone (500-3000)
            min_voice_duration=0.5  # Minimum 0.5 seconds of voice to trigger
        )
        
        print("\n⚠️  TO USE THIS SYSTEM:")
        print("1. Uncomment the dialer.add_sip_account() lines above")
        print("2. Replace with your actual SIP account details")
        print("3. Uncomment the dialer.start_system() and dialer.run_interactive_mode() lines below")
        print("4. Run this script")
        print("\n🎯 The system will then:")
        print("   📳 Keep your SIP accounts always registered and ready")
        print("   🎤 Listen for your voice through the microphone")
        print("   📞 Automatically answer incoming calls when you speak")
        
        # Uncomment these lines after configuring your accounts:
        
        # # Start the system
        # print("\\n🚀 Starting system...")
        # if dialer.start_system():
        #     print("✅ System started successfully!")
        #     
        #     # Run in interactive mode
        #     dialer.run_interactive_mode()
        # else:
        #     print("❌ Failed to start system")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        dialer.stop_system()
        
    print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()