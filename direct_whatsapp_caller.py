"""
Direct WhatsApp Call Button Clicker
Finds and clicks the voice call button directly
"""

import subprocess
import time
import pyautogui
import webbrowser
from PIL import Image
import psutil

class DirectWhatsAppCaller:
    def __init__(self):
        self.debug = True
        
    def log(self, message):
        if self.debug:
            print(f"[Direct Caller] {message}")
    
    def find_whatsapp_call_button(self, phone_number):
        """Find and click WhatsApp call button"""
        try:
            clean_number = phone_number.replace('+', '').replace('-', '').replace(' ', '')
            
            # Step 1: Open WhatsApp chat
            whatsapp_url = f"whatsapp://send?phone={clean_number}"
            self.log(f"Opening WhatsApp chat for {clean_number}")
            webbrowser.open(whatsapp_url)
            time.sleep(6)
            
            # Step 2: Take screenshot for debugging
            try:
                screenshot = pyautogui.screenshot()
                screenshot.save("whatsapp_interface.png")
                self.log("Screenshot saved: whatsapp_interface.png")
            except:
                pass
            
            # Step 3: Get screen dimensions
            screen_width, screen_height = pyautogui.size()
            self.log(f"Screen size: {screen_width}x{screen_height}")
            
            # Step 4: Common call button positions for different screen sizes
            if screen_width <= 1366:  # Smaller screens
                call_positions = [
                    (screen_width - 80, 60),   # Top right
                    (screen_width - 100, 80),  # Slightly down
                    (screen_width - 60, 70),   # Further right
                ]
            elif screen_width <= 1920:  # Standard HD
                call_positions = [
                    (screen_width - 120, 80),  # Top right
                    (screen_width - 150, 100), # Slightly down-left
                    (screen_width - 90, 90),   # Further right
                    (screen_width - 180, 120), # More left
                ]
            else:  # Larger screens
                call_positions = [
                    (screen_width - 150, 100), # Top right
                    (screen_width - 200, 120), # Slightly down-left
                    (screen_width - 120, 110), # Further right
                    (screen_width - 250, 140), # More left
                ]
            
            # Step 5: Try clicking each position
            for i, (x, y) in enumerate(call_positions, 1):
                try:
                    self.log(f"Testing position {i}: ({x}, {y})")
                    
                    # Ensure window focus
                    pyautogui.click(screen_width // 2, screen_height // 2)
                    time.sleep(0.5)
                    
                    # Click potential call button position
                    pyautogui.click(x, y)
                    time.sleep(2)
                    
                    # Interactive check
                    print(f"\n=== POSITION TEST {i} ===")
                    print(f"Clicked at: ({x}, {y})")
                    print(f"Target: {phone_number}")
                    result = input("Voice call started? (y/n/q): ").strip().lower()
                    
                    if result == 'y':
                        self.log(f"SUCCESS! Call button at ({x}, {y})")
                        return True, (x, y)
                    elif result == 'q':
                        return False, None
                    else:
                        self.log(f"Position ({x}, {y}) failed, trying next...")
                        
                except Exception as e:
                    self.log(f"Error with position {i}: {e}")
                    continue
            
            # Step 6: Manual position input
            print(f"\n=== MANUAL POSITION INPUT ===")
            print("All automatic positions failed.")
            print("Please look at the WhatsApp window and find the voice call button.")
            print("It's usually a phone icon in the top-right area.")
            
            try:
                manual_x = input(f"Enter X coordinate (0-{screen_width}): ").strip()
                manual_y = input(f"Enter Y coordinate (0-{screen_height}): ").strip()
                
                if manual_x.isdigit() and manual_y.isdigit():
                    x, y = int(manual_x), int(manual_y)
                    self.log(f"Trying manual position: ({x}, {y})")
                    
                    pyautogui.click(x, y)
                    time.sleep(2)
                    
                    if input("Did manual click work? (y/n): ").strip().lower() == 'y':
                        self.log(f"SUCCESS! Manual position ({x}, {y}) works!")
                        return True, (x, y)
            except:
                pass
            
            return False, None
            
        except Exception as e:
            self.log(f"Error finding call button: {e}")
            return False, None
    
    def save_working_position(self, position, phone_number):
        """Save the working position for future use"""
        try:
            config_data = f"""
# WhatsApp Call Button Position
# Found for phone: {phone_number}
# Screen position: {position}
CALL_BUTTON_X = {position[0]}
CALL_BUTTON_Y = {position[1]}
"""
            with open("whatsapp_call_position.py", "w") as f:
                f.write(config_data)
            self.log(f"Saved working position to whatsapp_call_position.py")
        except Exception as e:
            self.log(f"Error saving position: {e}")

def main():
    import sys
    
    phone_number = sys.argv[1] if len(sys.argv) > 1 else "+94769804761"
    
    print(f"\n{'='*70}")
    print(f"WHATSAPP DIRECT CALL BUTTON FINDER")
    print(f"Target: {phone_number}")
    print(f"{'='*70}")
    
    caller = DirectWhatsAppCaller()
    success, position = caller.find_whatsapp_call_button(phone_number)
    
    if success:
        print(f"\n🎯 SUCCESS! Call button found at: {position}")
        caller.save_working_position(position, phone_number)
        print("Position saved for future automatic calling!")
    else:
        print(f"\n❌ Could not find call button automatically")
        print("You may need to:")
        print("1. Adjust WhatsApp window size/position")
        print("2. Try different screen resolution")
        print("3. Use manual coordinates")

if __name__ == "__main__":
    main()