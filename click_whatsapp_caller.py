"""
WhatsApp Voice Call with GUI Click Method
This version clicks the actual call button instead of using keyboard shortcuts
"""

import subprocess
import time
import pyautogui
import webbrowser
import cv2
import numpy as np
from PIL import Image
import psutil

class ClickBasedWhatsAppCaller:
    def __init__(self):
        self.debug = True
        
    def log(self, message):
        if self.debug:
            print(f"[WhatsApp Clicker] {message}")
    
    def take_screenshot(self, filename="whatsapp_screenshot.png"):
        """Take a screenshot for debugging"""
        try:
            screenshot = pyautogui.screenshot()
            screenshot.save(filename)
            self.log(f"Screenshot saved: {filename}")
            return filename
        except Exception as e:
            self.log(f"Error taking screenshot: {e}")
            return None
    
    def find_call_button(self):
        """Try to find the voice call button on screen"""
        try:
            # Take screenshot first
            screenshot_file = self.take_screenshot()
            
            # Common locations for WhatsApp call button (top right area)
            # These are typical positions - may need adjustment
            potential_positions = [
                # Top right area where call buttons usually are
                (pyautogui.size().width - 150, 100),  # Top right
                (pyautogui.size().width - 100, 80),   # Further right
                (pyautogui.size().width - 200, 120),  # Left of top right
                (pyautogui.size().width - 120, 60),   # Higher up
                
                # Alternative positions
                (pyautogui.size().width - 80, 50),    # Far top right
                (pyautogui.size().width - 250, 100),  # More left
            ]
            
            return potential_positions
            
        except Exception as e:
            self.log(f"Error finding call button: {e}")
            return []
    
    def click_call_positions(self, phone_number):
        """Try clicking various positions where call button might be"""
        try:
            clean_number = phone_number.replace('+', '').replace('-', '').replace(' ', '')
            
            # Step 1: Open WhatsApp chat
            whatsapp_url = f"whatsapp://send?phone={clean_number}"
            self.log(f"Opening chat for {clean_number}")
            webbrowser.open(whatsapp_url)
            time.sleep(6)  # Wait for load
            
            # Step 2: Take screenshot for reference
            self.take_screenshot("whatsapp_before_click.png")
            
            # Step 3: Get potential button positions
            positions = self.find_call_button()
            
            # Step 4: Try clicking each position
            for i, (x, y) in enumerate(positions, 1):
                try:
                    self.log(f"Trying click position {i}: ({x}, {y})")
                    
                    # Click the position
                    pyautogui.click(x, y)
                    time.sleep(2)
                    
                    # Check with user
                    print(f"\n--- Click Test {i} ---")
                    print(f"Clicked at: ({x}, {y})")
                    print(f"Number: {phone_number}")
                    result = input("Did voice call start? (y/n/s=skip/q=quit): ").strip().lower()
                    
                    if result == 'y':
                        self.log(f"SUCCESS! Position ({x}, {y}) works!")
                        return True, (x, y)
                    elif result == 'q':
                        self.log("User quit testing")
                        return False, None
                    elif result == 's':
                        continue
                    else:
                        self.log(f"Position ({x}, {y}) didn't work")
                        
                except Exception as e:
                    self.log(f"Error clicking position {i}: {e}")
                    continue
            
            # Step 5: Manual guidance
            print(f"\n=== MANUAL CLICK GUIDANCE ===")
            print("Screenshot saved as 'whatsapp_before_click.png'")
            print("Please look for:")
            print("1. Phone icon (voice call)")
            print("2. Video icon (next to phone)")
            print("3. Usually in top-right area of chat")
            
            # Ask user to identify position
            try:
                print(f"\nCurrent screen resolution: {pyautogui.size().width}x{pyautogui.size().height}")
                manual_x = input("Enter X coordinate of call button (or 'n' to skip): ").strip()
                if manual_x.lower() != 'n':
                    manual_y = input("Enter Y coordinate of call button: ").strip()
                    try:
                        x, y = int(manual_x), int(manual_y)
                        self.log(f"Trying user-specified position: ({x}, {y})")
                        pyautogui.click(x, y)
                        time.sleep(2)
                        
                        if input("Did that work? (y/n): ").strip().lower() == 'y':
                            return True, (x, y)
                    except ValueError:
                        self.log("Invalid coordinates entered")
            except:
                pass
            
            return False, None
            
        except Exception as e:
            self.log(f"Error in click method: {e}")
            return False, None
    
    def test_click_method(self, phone_number):
        """Test the click-based call method"""
        print(f"\n{'='*60}")
        print(f"WHATSAPP VOICE CALL - CLICK METHOD TEST")
        print(f"Number: {phone_number}")
        print(f"{'='*60}")
        
        success, position = self.click_call_positions(phone_number)
        
        if success:
            print(f"\n✅ SUCCESS! Voice call button found at: {position}")
            print("This position can be used for future calls")
        else:
            print(f"\n❌ Click method failed")
            print("Try the keyboard shortcut method instead")
        
        return success, position

def main():
    import sys
    
    phone_number = sys.argv[1] if len(sys.argv) > 1 else "+94769804761"
    
    caller = ClickBasedWhatsAppCaller()
    success, position = caller.test_click_method(phone_number)
    
    if success:
        print(f"\n🎯 Call button position: {position}")
        print("This can be saved for automatic calling!")

if __name__ == "__main__":
    main()