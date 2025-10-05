"""
Direct Windows WhatsApp Voice Call Solution
This script provides a more reliable method for making voice calls through WhatsApp Desktop
"""

import subprocess
import time
import pyautogui
import webbrowser
from urllib.parse import quote
import psutil
import win32gui
import win32con

class WindowsWhatsAppCaller:
    def __init__(self):
        self.debug = True
        # Multiple keyboard shortcuts to try
        self.voice_shortcuts = [
            ['ctrl', 'shift', 'c'],  # Primary shortcut
            ['ctrl', 'alt', 'c'],    # Alternative 1
            ['f2'],                  # Alternative 2
            ['ctrl', 'shift', 'v']   # Alternative 3
        ]
        
    def log(self, message):
        if self.debug:
            print(f"[WhatsApp Caller] {message}")
            
    def is_whatsapp_running(self):
        """Check if WhatsApp Desktop is running"""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if 'whatsapp' in proc.info['name'].lower():
                    return True
            return False
        except Exception as e:
            self.log(f"Error checking WhatsApp process: {e}")
            return False
    
    def start_whatsapp(self):
        """Start WhatsApp Desktop if not running"""
        if self.is_whatsapp_running():
            self.log("WhatsApp already running")
            return True
            
        try:
            # Try to start WhatsApp Desktop
            subprocess.Popen([
                r"C:\Users\%USERNAME%\AppData\Local\WhatsApp\WhatsApp.exe"
            ], shell=True)
            self.log("Starting WhatsApp Desktop...")
            time.sleep(8)  # Wait for WhatsApp to fully load
            return True
        except Exception as e:
            self.log(f"Error starting WhatsApp: {e}")
            return False
    
    def focus_whatsapp_window(self):
        """Focus WhatsApp window using multiple methods"""
        try:
            # Method 1: Use PowerShell to focus
            ps_command = '''
            Add-Type -TypeDefinition @"
                using System;
                using System.Runtime.InteropServices;
                public class Win32 {
                    [DllImport("user32.dll")]
                    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
                    [DllImport("user32.dll")]
                    public static extern bool SetForegroundWindow(IntPtr hWnd);
                    [DllImport("user32.dll")]
                    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                    [DllImport("user32.dll")]
                    public static extern bool BringWindowToTop(IntPtr hWnd);
                }
"@
            $whatsappWindow = [Win32]::FindWindow($null, "*WhatsApp*")
            if ($whatsappWindow -ne [IntPtr]::Zero) {
                [Win32]::ShowWindow($whatsappWindow, 9)  # SW_RESTORE
                [Win32]::BringWindowToTop($whatsappWindow)
                [Win32]::SetForegroundWindow($whatsappWindow)
                Write-Output "SUCCESS"
            } else {
                Write-Output "NOTFOUND"
            }
            '''
            
            result = subprocess.run(['powershell', '-Command', ps_command], 
                                  capture_output=True, text=True, timeout=10)
            
            if "SUCCESS" in result.stdout:
                self.log("Successfully focused WhatsApp window")
                time.sleep(2)
                return True
                
            # Method 2: Use pyautogui to find and click WhatsApp
            try:
                pyautogui.hotkey('alt', 'tab')
                time.sleep(1)
                return True
            except:
                pass
                
            return False
            
        except Exception as e:
            self.log(f"Error focusing WhatsApp: {e}")
            return False
    
    def make_voice_call(self, phone_number):
        """Make a voice call to the specified number"""
        try:
            # Clean the phone number
            clean_number = phone_number.replace('+', '').replace('-', '').replace(' ', '')
            self.log(f"Making voice call to: {clean_number}")
            
            # Step 1: Ensure WhatsApp is running
            if not self.start_whatsapp():
                self.log("Failed to start WhatsApp")
                return False
            
            # Step 2: Open chat with the number
            whatsapp_url = f"whatsapp://send?phone={clean_number}"
            self.log(f"Opening WhatsApp URL: {whatsapp_url}")
            webbrowser.open(whatsapp_url)
            
            # Wait for chat to load
            time.sleep(6)
            
            # Step 3: Focus WhatsApp window
            if not self.focus_whatsapp_window():
                self.log("Warning: Could not focus WhatsApp window")
            
            # Step 4: Try multiple keyboard shortcuts for voice call
            success = False
            for i, shortcut in enumerate(self.voice_shortcuts, 1):
                try:
                    self.log(f"Trying voice call method {i}: {'+'.join(shortcut)}")
                    
                    # Ensure window is focused before each attempt
                    pyautogui.click(pyautogui.size().width // 2, pyautogui.size().height // 2)
                    time.sleep(0.5)
                    
                    # Try the keyboard shortcut
                    pyautogui.hotkey(*shortcut)
                    time.sleep(2)
                    
                    # Check if call started (simple heuristic)
                    self.log(f"Voice call shortcut {'+'.join(shortcut)} sent")
                    
                    # Ask user for confirmation
                    print(f"\n=== VOICE CALL TEST {i} ===")
                    print(f"Shortcut used: {'+'.join(shortcut)}")
                    print(f"Target number: {phone_number}")
                    confirm = input("Did the voice call start? (y/n): ").strip().lower()
                    
                    if confirm == 'y':
                        self.log(f"SUCCESS! Voice call started with method {i}")
                        success = True
                        break
                    else:
                        self.log(f"Method {i} failed, trying next...")
                        time.sleep(1)
                        
                except Exception as e:
                    self.log(f"Error with method {i}: {e}")
                    continue
            
            if not success:
                self.log("All voice call methods failed")
                print("\n=== MANUAL GUIDANCE ===")
                print(f"WhatsApp chat should be open for {phone_number}")
                print("Please try these manual steps:")
                print("1. Look for a phone/call icon in the chat")
                print("2. Click the phone icon to start voice call")
                print("3. Or try keyboard shortcuts: Ctrl+Shift+C or F2")
                return False
            
            return success
            
        except Exception as e:
            self.log(f"Error making voice call: {e}")
            return False
    
    def test_call(self, phone_number):
        """Test voice call functionality"""
        print(f"\n{'='*50}")
        print(f"TESTING WINDOWS WHATSAPP VOICE CALL")
        print(f"Target Number: {phone_number}")
        print(f"{'='*50}")
        
        result = self.make_voice_call(phone_number)
        
        if result:
            print(f"\n✅ SUCCESS: Voice call initiated to {phone_number}")
        else:
            print(f"\n❌ FAILED: Could not start voice call to {phone_number}")
        
        return result

def main():
    import sys
    
    if len(sys.argv) < 2:
        phone_number = "+94769804761"  # Default test number
    else:
        phone_number = sys.argv[1]
    
    caller = WindowsWhatsAppCaller()
    caller.test_call(phone_number)

if __name__ == "__main__":
    main()