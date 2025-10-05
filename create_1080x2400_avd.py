#!/usr/bin/env python3
"""
Create Android 14 AVD with 1080x2400 Display Resolution
For SIP Dialer project - ensures proper WhatsApp automation scaling
"""

import os
import sys
import subprocess
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from android_installer import AndroidInstaller

def create_1080x2400_avd():
    """Create a new Android 14 AVD with 1080x2400 display resolution"""
    print("📱 Creating Android 14 AVD with 1080x2400 Display")
    print("=" * 50)
    
    # Initialize installer
    installer = AndroidInstaller()
    
    # Check prerequisites
    print("\n1️⃣ CHECKING PREREQUISITES:")
    print("-" * 30)
    
    status = installer.get_installation_status()
    print(f"   📦 SDK Installed: {'✅' if status['sdk_installed'] else '❌'}")
    print(f"   🔧 Emulator Installed: {'✅' if status['emulator_installed'] else '❌'}")
    print(f"   🚀 Android 14 Installed: {'✅' if status['android_14_installed'] else '❌'}")
    
    if not all([status['sdk_installed'], status['emulator_installed'], status['android_14_installed']]):
        print("\n❌ Missing prerequisites! Please run the full Android installation first.")
        print("💡 Use the SIP Dialer GUI: Settings > Install Android SDK")
        return False
    
    # Show current AVDs
    print(f"\n📱 Current AVDs: {status['avd_list'] if status['avd_list'] else 'None'}")
    
    # Create new AVD with specific resolution
    print("\n2️⃣ CREATING AVD WITH 1080x2400 DISPLAY:")
    print("-" * 30)
    
    avd_name = "SipDialer_Android14_1080x2400"
    print(f"   Creating AVD: {avd_name}")
    print(f"   Resolution: 1080x2400 pixels")
    print(f"   Device Profile: Pixel 6")
    print(f"   Android Version: 14 (API 34)")
    
    success = installer.create_android_14_avd_with_display(avd_name, "1080x2400")
    
    if success:
        print(f"\n✅ SUCCESS! AVD '{avd_name}' created successfully!")
        
        # Update configuration to use new AVD
        print("\n3️⃣ UPDATING ACCOUNT CONFIGURATION:")
        print("-" * 30)
        
        try:
            from config_manager import ConfigManager
            config_manager = ConfigManager()

            account_ids = config_manager.get_enabled_accounts()

            # Update all accounts to use the new AVD
            for account_id in account_ids:
                account_config = {
                    "emulator_avd": avd_name
                }
                if config_manager.set_account_config(account_id, account_config):
                    print(f"   ✅ Account {account_id} configured to use {avd_name}")
                else:
                    print(f"   ⚠️  Warning: Failed to configure Account {account_id}")
            
            if config_manager.save_config():
                print(f"\n✅ Configuration saved successfully!")
            else:
                print(f"\n⚠️  Warning: Failed to save configuration")
                
        except Exception as e:
            print(f"\n⚠️  Warning: Could not update configuration: {e}")
        
        # Show next steps
        print(f"\n🎯 NEXT STEPS:")
        print("-" * 30)
        print(f"   1. Launch SIP Dialer GUI")
        print(f"   2. Test emulator launch with Account 1")
        print(f"   3. Configure WhatsApp tap coordinates for 1080x2400 resolution")
        print(f"   4. The display should now properly support WhatsApp automation")
        
        print(f"\n💡 TECHNICAL DETAILS:")
        print(f"   📐 Resolution: 1080x2400 pixels")
        print(f"   🔍 Density: 440 DPI (standard for 1080p phones)")
        print(f"   📱 Device: Pixel 6 profile")
        print(f"   🎮 GPU: Hardware acceleration enabled")
        
        return True
        
    else:
        print(f"\n❌ FAILED to create AVD!")
        print(f"💡 Try running as administrator or check Android SDK installation")
        return False

def test_emulator_launch():
    """Test launching the new AVD"""
    print(f"\n4️⃣ TESTING EMULATOR LAUNCH:")
    print("-" * 30)
    
    emulator_exe = r"C:\Users\Roshan\AppData\Local\Android\Sdk\emulator\emulator.exe"
    if not os.path.exists(emulator_exe):
        print(f"❌ Emulator executable not found: {emulator_exe}")
        return False
    
    avd_name = "SipDialer_Android14_1080x2400"
    port = 5554
    
    print(f"   Launching: {avd_name}")
    print(f"   Port: {port}")
    print(f"   Resolution: 1080x2400")
    
    # Set environment
    env = os.environ.copy()
    android_sdk_path = os.path.dirname(os.path.dirname(emulator_exe))
    env['ANDROID_SDK_ROOT'] = android_sdk_path
    env['ANDROID_HOME'] = android_sdk_path
    env['ANDROID_AVD_HOME'] = os.path.join(os.path.expanduser("~"), ".android", "avd")
    
    # Launch command
    args = [
        emulator_exe, "-avd", avd_name, 
        "-port", str(port),
        "-no-snapshot", "-netdelay", "none", "-netspeed", "full", "-no-boot-anim"
    ]
    
    try:
        print(f"   Starting emulator...")
        process = subprocess.Popen(
            args,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0,
            env=env
        )
        
        print(f"   ✅ Emulator launched! PID: {process.pid}")
        print(f"   📱 AVD should appear with 1080x2400 display")
        print(f"   ⏰ Wait for Android to fully boot before testing")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Launch failed: {e}")
        return False

if __name__ == "__main__":
    try:
        if create_1080x2400_avd():
            print(f"\n🎉 AVD CREATION COMPLETED SUCCESSFULLY!")
            
            # Ask if user wants to test launch
            print(f"\n❓ Would you like to test launch the emulator? (y/n): ", end="")
            response = input().strip().lower()
            
            if response == 'y' or response == 'yes':
                test_emulator_launch()
            else:
                print(f"\n💡 You can test the emulator later using the SIP Dialer GUI")
        else:
            print(f"\n❌ AVD CREATION FAILED!")
            
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")