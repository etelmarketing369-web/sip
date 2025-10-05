#!/usr/bin/env python3
"""
WhatsApp Desktop Keyboard Shortcuts Finder
Tests various keyboard combinations to find the voice call shortcut
"""

import time
import pyautogui
import subprocess

def get_whatsapp_shortcuts():
    """Display known WhatsApp Desktop keyboard shortcuts"""
    shortcuts = {
        "General Navigation": {
            "Ctrl+N": "Start a new chat",
            "Ctrl+Shift+N": "Create a new group", 
            "Ctrl+P": "Open Profile and About",
            "Ctrl+Comma": "Open Settings",
            "Ctrl+F": "Search or start new chat",
            "Ctrl+Alt+Shift+U": "Mark as unread",
            "Ctrl+Shift+M": "Mute a chat",
            "Ctrl+Backspace": "Delete chat",
            "Ctrl+Shift+A": "Archive chat",
            "Ctrl+E": "Archive all chats"
        },
        "Call Functions": {
            "Ctrl+Shift+C": "Start voice call (commonly reported)",
            "Ctrl+Alt+C": "Alternative voice call shortcut",
            "Ctrl+Shift+V": "Start video call",
            "F2": "Alternative call shortcut",
            "Ctrl+Shift+U": "Unmute/mute during call"
        },
        "Message Functions": {
            "Enter": "Send message",
            "Shift+Enter": "New line",
            "Ctrl+A": "Select all",
            "Ctrl+C": "Copy",
            "Ctrl+V": "Paste",
            "Ctrl+Z": "Undo",
            "Ctrl+Y": "Redo"
        }
    }
    
    print("📋 WHATSAPP DESKTOP KEYBOARD SHORTCUTS")
    print("=" * 50)
    
    for category, shortcut_dict in shortcuts.items():
        print(f"\n🔹 {category}:")
        for shortcut, description in shortcut_dict.items():
            print(f"   {shortcut:<20} - {description}")

def test_whatsapp_shortcuts():
    """Test various keyboard shortcuts for voice calls"""
    print("\n🧪 TESTING WHATSAPP VOICE CALL SHORTCUTS")
    print("=" * 50)
    
    # List of shortcuts to test for voice calls
    voice_call_shortcuts = [
        ("Ctrl+Shift+C", lambda: pyautogui.hotkey('ctrl', 'shift', 'c')),
        ("Ctrl+Alt+C", lambda: pyautogui.hotkey('ctrl', 'alt', 'c')),
        ("Ctrl+C", lambda: pyautogui.hotkey('ctrl', 'c')),  # Sometimes just Ctrl+C
        ("F2", lambda: pyautogui.press('f2')),
        ("Ctrl+Shift+V", lambda: pyautogui.hotkey('ctrl', 'shift', 'v')),  # Video call, but might work
        ("Ctrl+Enter", lambda: pyautogui.hotkey('ctrl', 'enter')),
        ("Alt+C", lambda: pyautogui.hotkey('alt', 'c')),
        ("Shift+C", lambda: pyautogui.hotkey('shift', 'c')),
    ]
    
    print("⚠️  IMPORTANT: Make sure WhatsApp Desktop is open with a chat selected!")
    print("This test will send various keyboard shortcuts to find the voice call key.\n")
    
    input("Press Enter when WhatsApp is ready and you're in a chat window...")
    
    for i, (shortcut_name, shortcut_func) in enumerate(voice_call_shortcuts, 1):
        print(f"\n🔹 Test {i}: Trying {shortcut_name}")
        print("   Sending shortcut in 3 seconds...")
        
        # Countdown
        for countdown in range(3, 0, -1):
            print(f"   {countdown}...")
            time.sleep(1)
        
        try:
            # Focus WhatsApp first
            focus_whatsapp()
            time.sleep(0.5)
            
            # Send the shortcut
            shortcut_func()
            print(f"   ✅ Sent {shortcut_name}")
            
            # Ask user for feedback
            print("   Did this start a voice call? (y/n/s to skip remaining tests): ", end="")
            response = input().strip().lower()
            
            if response == 'y':
                print(f"   🎉 SUCCESS! {shortcut_name} starts a voice call!")
                return shortcut_name
            elif response == 's':
                print("   ⏭️  Skipping remaining tests...")
                break
            else:
                print("   ❌ Did not work, trying next...")
                
        except Exception as e:
            print(f"   ❌ Error with {shortcut_name}: {e}")
            
        # Wait between tests
        time.sleep(2)
    
    print("\n🔍 Testing completed. If none worked, the shortcut might be different")
    print("   or require specific WhatsApp Desktop version/settings.")

def focus_whatsapp():
    """Focus WhatsApp Desktop window"""
    try:
        focus_cmd = '''
        $whatsappProcess = Get-Process | Where-Object {$_.MainWindowTitle -like "*WhatsApp*"} | Select-Object -First 1
        if ($whatsappProcess) {
            Add-Type -AssemblyName Microsoft.VisualBasic
            [Microsoft.VisualBasic.Interaction]::AppActivate($whatsappProcess.Id)
        }
        '''
        subprocess.run(['powershell', '-Command', focus_cmd], 
                      capture_output=True, timeout=3)
    except:
        pass

def check_whatsapp_help():
    """Try to open WhatsApp help menu to see shortcuts"""
    print("\n📚 CHECKING WHATSAPP HELP MENU")
    print("=" * 30)
    
    print("Attempting to open WhatsApp keyboard shortcuts help...")
    print("This will try common help shortcuts in WhatsApp:")
    
    help_shortcuts = [
        ("Ctrl+/", lambda: pyautogui.hotkey('ctrl', '/')),
        ("Ctrl+?", lambda: pyautogui.hotkey('ctrl', 'shift', '/')),
        ("F1", lambda: pyautogui.press('f1')),
        ("Ctrl+H", lambda: pyautogui.hotkey('ctrl', 'h')),
        ("Alt+H", lambda: pyautogui.hotkey('alt', 'h')),
    ]
    
    input("Press Enter when WhatsApp Desktop is focused...")
    
    for shortcut_name, shortcut_func in help_shortcuts:
        try:
            print(f"Trying {shortcut_name}...")
            focus_whatsapp()
            time.sleep(0.5)
            shortcut_func()
            time.sleep(1)
            
            response = input(f"Did {shortcut_name} open help/shortcuts? (y/n): ").strip().lower()
            if response == 'y':
                print(f"✅ {shortcut_name} opens help! Check for keyboard shortcuts there.")
                break
        except Exception as e:
            print(f"Error with {shortcut_name}: {e}")

def manual_investigation():
    """Guide user through manual investigation"""
    print("\n🔍 MANUAL INVESTIGATION GUIDE")
    print("=" * 35)
    
    print("If the automatic tests didn't work, try these manual steps:")
    print()
    print("1. 📱 Open WhatsApp Desktop")
    print("2. 🗨️  Open a chat with someone you can safely test call")
    print("3. 🔍 Look for menu options:")
    print("   • Right-click in the chat area")
    print("   • Check the top menu bar (File, Edit, View, etc.)")
    print("   • Look for 'Call' or phone icon buttons")
    print("4. 📝 Check WhatsApp settings:")
    print("   • Go to Settings (Ctrl+Comma)")
    print("   • Look for 'Keyboard shortcuts' section")
    print("   • Check 'Help' or 'About' sections")
    print()
    print("5. 🌐 Alternative methods:")
    print("   • Click the phone icon next to contact name")
    print("   • Right-click contact name → Call")
    print("   • Use WhatsApp Web (web.whatsapp.com) and check shortcuts there")

if __name__ == "__main__":
    print("WHATSAPP VOICE CALL SHORTCUT FINDER")
    print("=" * 50)
    
    while True:
        print("\nChoose an option:")
        print("1. Show known WhatsApp keyboard shortcuts")
        print("2. Test voice call shortcuts automatically") 
        print("3. Try to open WhatsApp help menu")
        print("4. Manual investigation guide")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            get_whatsapp_shortcuts()
            
        elif choice == "2":
            try:
                result = test_whatsapp_shortcuts()
                if result:
                    print(f"\n🎉 Found working shortcut: {result}")
            except KeyboardInterrupt:
                print("\n⏸️  Testing cancelled by user")
                
        elif choice == "3":
            check_whatsapp_help()
            
        elif choice == "4":
            manual_investigation()
            
        elif choice == "5":
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice")