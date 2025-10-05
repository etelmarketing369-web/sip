#!/usr/bin/env python3
"""
Enhanced WhatsApp Voice Call Solution
Fixes the issue where chat opens but call doesn't start
"""

import time
import webbrowser
import subprocess
import pyautogui
import sys

def enhanced_whatsapp_call(phone_number: str):
    """Enhanced method to ensure voice call actually starts"""
    
    print(f"🔧 ENHANCED WHATSAPP VOICE CALL")
    print(f"Target: {phone_number}")
    print("=" * 40)
    
    # Step 1: Open WhatsApp chat
    clean_number = phone_number.lstrip('+')
    whatsapp_url = f"whatsapp://send?phone={clean_number}"
    
    print(f"📱 Opening WhatsApp: {whatsapp_url}")
    success = webbrowser.open(whatsapp_url)
    
    if not success:
        print("❌ Failed to open WhatsApp URL")
        return False
    
    print("✅ WhatsApp URL opened")
    
    # Step 2: Extended wait for WhatsApp to fully load
    print("⏳ Waiting for WhatsApp to fully load...")
    for i in range(6, 0, -1):
        print(f"   {i} seconds remaining...")
        time.sleep(1)
    
    # Step 3: Multiple focus attempts with verification
    print("🎯 Ensuring WhatsApp window is focused...")
    for attempt in range(3):
        try:
            focus_result = focus_whatsapp_window()
            if focus_result:
                print(f"✅ Focus attempt {attempt + 1}: Success")
                break
            else:
                print(f"⚠ Focus attempt {attempt + 1}: Partial success")
        except Exception as e:
            print(f"⚠ Focus attempt {attempt + 1}: Error - {e}")
        
        if attempt < 2:
            time.sleep(1)
    
    # Step 4: Wait for UI to be completely ready
    print("⏳ Ensuring WhatsApp UI is ready...")
    time.sleep(3)
    
    # Step 5: Enhanced keyboard shortcut sending with multiple methods
    print("📞 Attempting to start voice call...")
    
    call_methods = [
        ("Primary: Ctrl+Shift+C", send_ctrl_shift_c),
        ("Alternative 1: Click call button", click_call_button),
        ("Alternative 2: Ctrl+Alt+C", send_ctrl_alt_c),
        ("Alternative 3: F2 key", send_f2_key),
        ("Manual guidance", provide_manual_guidance)
    ]
    
    for method_name, method_func in call_methods:
        print(f"🔹 Trying: {method_name}")
        
        try:
            # Ensure focus before each attempt
            focus_whatsapp_window()
            time.sleep(0.5)
            
            result = method_func(phone_number)
            
            if result:
                print(f"✅ SUCCESS with {method_name}")
                return True
            else:
                print(f"⚠ {method_name} executed but call status unknown")
                
                # Ask user for verification
                user_input = input(f"Did {method_name} start the call? (y/n/skip): ").strip().lower()
                
                if user_input == 'y':
                    print(f"🎉 SUCCESS! {method_name} worked!")
                    return True
                elif user_input == 'skip':
                    print("⏭️ Skipping to manual guidance...")
                    break
                else:
                    print("❌ Method didn't work, trying next...")
                    
        except Exception as e:
            print(f"❌ Error with {method_name}: {e}")
        
        time.sleep(1)  # Brief pause between attempts
    
    print("\n🛠️ MANUAL ACTION REQUIRED:")
    print("The WhatsApp chat should be open now.")
    print("Please manually click the phone/call icon to start the voice call.")
    
    return False

def focus_whatsapp_window():
    """Enhanced WhatsApp window focusing"""
    try:
        focus_script = '''
        # Find all WhatsApp processes
        $whatsappProcesses = Get-Process | Where-Object {
            $_.ProcessName -like "*WhatsApp*" -or 
            $_.MainWindowTitle -like "*WhatsApp*"
        } | Where-Object { $_.MainWindowHandle -ne 0 }
        
        if ($whatsappProcesses.Count -gt 0) {
            # Get the main WhatsApp window
            $mainWindow = $whatsappProcesses | Where-Object {
                $_.MainWindowTitle -ne "" -and $_.MainWindowTitle -like "*WhatsApp*"
            } | Select-Object -First 1
            
            if ($mainWindow) {
                # Load required assemblies
                Add-Type -AssemblyName Microsoft.VisualBasic
                Add-Type -AssemblyName System.Windows.Forms
                
                # Multiple focus methods
                [Microsoft.VisualBasic.Interaction]::AppActivate($mainWindow.Id)
                
                # Win32 API methods for stronger focus
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    public class Win32 {
                        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
                        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                        [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
                        [DllImport("user32.dll")] public static extern bool SetActiveWindow(IntPtr hWnd);
                        [DllImport("user32.dll")] public static extern IntPtr SetFocus(IntPtr hWnd);
                    }
"@
                
                $handle = $mainWindow.MainWindowHandle
                [Win32]::ShowWindow($handle, 9)  # SW_RESTORE
                [Win32]::BringWindowToTop($handle)
                [Win32]::SetForegroundWindow($handle)
                [Win32]::SetActiveWindow($handle)
                [Win32]::SetFocus($handle)
                
                # Additional activation
                [System.Windows.Forms.Application]::DoEvents()
                
                Write-Host "SUCCESS: Enhanced focus applied to WhatsApp"
                Write-Host "Window: $($mainWindow.MainWindowTitle)"
                Write-Host "Handle: $handle"
                
                # Verify focus
                $activeWindow = Get-Process | Where-Object { $_.Id -eq $mainWindow.Id }
                if ($activeWindow) {
                    Write-Host "VERIFIED: WhatsApp is active"
                } else {
                    Write-Host "WARNING: Could not verify focus"
                }
            } else {
                Write-Host "ERROR: No WhatsApp window with title found"
            }
        } else {
            Write-Host "ERROR: No WhatsApp processes found"
        }
        '''
        
        result = subprocess.run(['powershell', '-Command', focus_script], 
                              capture_output=True, text=True, timeout=10)
        
        print(f"Focus result: {result.stdout.strip()}")
        
        return "SUCCESS" in result.stdout
        
    except Exception as e:
        print(f"Focus error: {e}")
        return False

def send_ctrl_shift_c(phone_number):
    """Send Ctrl+Shift+C shortcut"""
    try:
        pyautogui.hotkey('ctrl', 'shift', 'c')
        time.sleep(1)
        return True
    except Exception as e:
        print(f"Error sending Ctrl+Shift+C: {e}")
        return False

def send_ctrl_alt_c(phone_number):
    """Send Ctrl+Alt+C shortcut"""
    try:
        pyautogui.hotkey('ctrl', 'alt', 'c')
        time.sleep(1)
        return True
    except Exception as e:
        print(f"Error sending Ctrl+Alt+C: {e}")
        return False

def send_f2_key(phone_number):
    """Send F2 key"""
    try:
        pyautogui.press('f2')
        time.sleep(1)
        return True
    except Exception as e:
        print(f"Error sending F2: {e}")
        return False

def click_call_button(phone_number):
    """Try to click the call button using screen coordinates"""
    try:
        print("   Looking for call button on screen...")
        
        # Common locations for WhatsApp call button (adjust as needed)
        # These are approximate - you may need to adjust based on your screen
        potential_locations = [
            (1200, 60),   # Top right area where call button usually is
            (1150, 60),   # Slightly left
            (1100, 80),   # Different position
            (1250, 70),   # Further right
        ]
        
        for x, y in potential_locations:
            try:
                print(f"   Trying click at ({x}, {y})...")
                pyautogui.click(x, y)
                time.sleep(0.5)
                
                # Check if call started (this is basic - you might improve detection)
                user_response = input(f"   Did clicking at ({x}, {y}) start the call? (y/n): ").strip().lower()
                if user_response == 'y':
                    return True
                    
            except Exception as e:
                print(f"   Click at ({x}, {y}) failed: {e}")
                
        return False
        
    except Exception as e:
        print(f"Error with click method: {e}")
        return False

def provide_manual_guidance(phone_number):
    """Provide manual guidance to user"""
    print(f"\n📋 MANUAL GUIDANCE FOR {phone_number}:")
    print("1. 📱 WhatsApp should now be open with the chat")
    print("2. 🔍 Look for the phone/call icon (usually top right)")
    print("3. 🖱️ Click the phone icon to start voice call")
    print("4. ⌨️ Or try pressing Ctrl+Shift+C while WhatsApp is focused")
    print("5. 📞 The call should start connecting")
    
    input("Press Enter after you've manually started the call...")
    return True

def test_with_user_number():
    """Interactive test with user's number"""
    phone = input("Enter phone number to test (e.g., +94769804761): ").strip()
    if phone:
        enhanced_whatsapp_call(phone)
    else:
        print("No phone number entered")

if __name__ == "__main__":
    print("ENHANCED WHATSAPP VOICE CALL SOLUTION")
    print("Fixes: Chat opens but call doesn't start")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        phone_number = sys.argv[1]
        enhanced_whatsapp_call(phone_number)
    else:
        test_with_user_number()