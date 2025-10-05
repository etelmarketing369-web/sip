"""
Automated WhatsApp Voice Caller
Uses the discovered call button position for reliable voice calls
"""

import time
import pyautogui
import webbrowser
import subprocess
import psutil

# Import the discovered call button position
try:
    from whatsapp_call_position import CALL_BUTTON_X, CALL_BUTTON_Y
    CALL_POSITION_FOUND = True
except ImportError:
    CALL_BUTTON_X, CALL_BUTTON_Y = 1800, 80  # Default fallback
    CALL_POSITION_FOUND = False

class AutomatedWhatsAppCaller:
    def __init__(self):
        self.debug = True
        self.call_button_x = CALL_BUTTON_X
        self.call_button_y = CALL_BUTTON_Y
        
    def log(self, message):
        if self.debug:
            print(f"[Auto Caller] {message}")
    
    def is_whatsapp_running(self):
        """Check if WhatsApp is running"""
        try:
            for proc in psutil.process_iter(['name']):
                if 'whatsapp' in proc.info['name'].lower():
                    return True
            return False
        except:
            return False
    
    def ensure_whatsapp_running(self):
        """Make sure WhatsApp is running"""
        if not self.is_whatsapp_running():
            self.log("Starting WhatsApp...")
            try:
                # Try to start WhatsApp
                subprocess.Popen([r"C:\Users\%USERNAME%\AppData\Local\WhatsApp\WhatsApp.exe"], shell=True)
                time.sleep(8)
            except:
                self.log("Could not auto-start WhatsApp")
        else:
            self.log("WhatsApp already running")
    
    def make_voice_call(self, phone_number):
        """Make an automated voice call"""
        try:
            clean_number = phone_number.replace('+', '').replace('-', '').replace(' ', '')
            self.log(f"Making automated call to: {clean_number}")
            
            # Step 1: Ensure WhatsApp is running
            self.ensure_whatsapp_running()
            
            # Step 2: Open chat
            whatsapp_url = f"whatsapp://send?phone={clean_number}"
            self.log("Opening WhatsApp chat...")
            webbrowser.open(whatsapp_url)
            time.sleep(6)  # Wait for chat to load
            
            # Step 3: Focus WhatsApp window (click center first)
            screen_width, screen_height = pyautogui.size()
            pyautogui.click(screen_width // 2, screen_height // 2)
            time.sleep(1)
            
            # Step 4: Click the call button at discovered position
            self.log(f"Clicking call button at ({self.call_button_x}, {self.call_button_y})")
            pyautogui.click(self.call_button_x, self.call_button_y)
            time.sleep(2)
            
            self.log("Voice call command sent!")
            return True
            
        except Exception as e:
            self.log(f"Error making automated call: {e}")
            return False
    
    def test_automated_call(self, phone_number):
        """Test the automated calling system"""
        print(f"\n{'='*60}")
        print(f"AUTOMATED WHATSAPP VOICE CALL")
        print(f"Number: {phone_number}")
        print(f"Button Position: ({self.call_button_x}, {self.call_button_y})")
        print(f"{'='*60}")
        
        success = self.make_voice_call(phone_number)
        
        if success:
            # Wait a moment then ask for confirmation
            time.sleep(3)
            confirm = input("\nDid the voice call start successfully? (y/n): ").strip().lower()
            
            if confirm == 'y':
                print("✅ AUTOMATED CALLING SUCCESS!")
                return True
            else:
                print("❌ Automated calling needs adjustment")
                return False
        else:
            print("❌ Error in automated calling process")
            return False

def main():
    import sys
    
    phone_number = sys.argv[1] if len(sys.argv) > 1 else "+94769804761"
    
    caller = AutomatedWhatsAppCaller()
    
    if not CALL_POSITION_FOUND:
        print("⚠️  Warning: Using default call button position")
        print("Run 'direct_whatsapp_caller.py' first to find exact position")
    
    success = caller.test_automated_call(phone_number)
    
    if success:
        print(f"\n🎉 Automated WhatsApp calling is now working!")
        print("This can be integrated into your SIP dialer system")
    else:
        print(f"\n🔧 Needs troubleshooting - try running direct_whatsapp_caller.py again")

if __name__ == "__main__":
    main()