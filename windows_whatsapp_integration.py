"""
Windows WhatsApp Integration for SIP Dialer
Uses whatsapp://call?phone= for direct voice calls
"""

import webbrowser
import time
import subprocess
import psutil
import logging

class WindowsWhatsAppIntegration:
    def __init__(self):
        self.logger = self.setup_logging()
        
    def setup_logging(self):
        """Setup logging for WhatsApp integration"""
        logger = logging.getLogger('WhatsAppIntegration')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(name)s] %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def is_whatsapp_running(self):
        """Check if WhatsApp Desktop is running"""
        try:
            for proc in psutil.process_iter(['name']):
                if 'whatsapp' in proc.info['name'].lower():
                    return True
            return False
        except Exception as e:
            self.logger.error(f"Error checking WhatsApp process: {e}")
            return False
    
    def ensure_whatsapp_running(self):
        """Ensure WhatsApp Desktop is running"""
        if self.is_whatsapp_running():
            self.logger.info("WhatsApp Desktop is running")
            return True
        
        self.logger.info("Starting WhatsApp Desktop...")
        try:
            # Try common WhatsApp Desktop paths
            whatsapp_paths = [
                r"C:\Users\{}\AppData\Local\WhatsApp\WhatsApp.exe".format(os.environ.get('USERNAME', '')),
                r"C:\Program Files\WindowsApps\5319275A.WhatsAppDesktop_*\WhatsApp.exe",
                r"C:\Users\{}\AppData\Local\Microsoft\WindowsApps\WhatsApp.exe".format(os.environ.get('USERNAME', ''))
            ]
            
            for path in whatsapp_paths:
                try:
                    subprocess.Popen([path], shell=True)
                    time.sleep(5)  # Wait for startup
                    if self.is_whatsapp_running():
                        self.logger.info("WhatsApp Desktop started successfully")
                        return True
                except:
                    continue
            
            self.logger.warning("Could not start WhatsApp Desktop automatically")
            return False
            
        except Exception as e:
            self.logger.error(f"Error starting WhatsApp: {e}")
            return False
    
    def make_voice_call(self, phone_number):
        """
        Make a voice call using Windows WhatsApp Desktop
        
        Args:
            phone_number (str): Phone number to call (with or without +)
            
        Returns:
            bool: True if call was initiated successfully
        """
        try:
            # Clean and format phone number
            clean_number = phone_number.strip().replace(' ', '').replace('-', '')
            if not clean_number.startswith('+'):
                clean_number = '+' + clean_number
            
            self.logger.info(f"Initiating WhatsApp call to: {clean_number}")
            
            # Ensure WhatsApp is running
            if not self.ensure_whatsapp_running():
                self.logger.error("WhatsApp Desktop is not available")
                return False
            
            # Use the direct call URL scheme
            call_url = f"whatsapp://call?phone={clean_number}"
            self.logger.info(f"Opening call URL: {call_url}")
            
            # Open the URL to initiate call
            webbrowser.open(call_url)
            
            # Give WhatsApp time to process the call
            time.sleep(2)
            
            self.logger.info("WhatsApp call initiated successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error making WhatsApp call: {e}")
            return False
    
    def test_call(self, phone_number="+94769804761"):
        """Test the WhatsApp calling functionality"""
        print(f"\n{'='*50}")
        print(f"Windows WhatsApp Integration Test")
        print(f"Target: {phone_number}")
        print(f"{'='*50}")
        
        success = self.make_voice_call(phone_number)
        
        if success:
            print("✅ WhatsApp call initiated!")
            print("Check WhatsApp Desktop for the call")
            return True
        else:
            print("❌ Failed to initiate WhatsApp call")
            return False

# Import this in your main SIP dialer
def create_whatsapp_caller():
    """Factory function to create WhatsApp caller instance"""
    return WindowsWhatsAppIntegration()

def main():
    """Test the integration"""
    import sys
    import os
    
    phone_number = sys.argv[1] if len(sys.argv) > 1 else "+94769804761"
    
    whatsapp = WindowsWhatsAppIntegration()
    success = whatsapp.test_call(phone_number)
    
    if success:
        print(f"\n🎉 Windows WhatsApp integration is working!")
        print("This can now be integrated into your SIP dialer")
    else:
        print(f"\n🔧 Integration needs troubleshooting")

if __name__ == "__main__":
    import os
    main()