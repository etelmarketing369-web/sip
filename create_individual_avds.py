#!/usr/bin/env python3

import os
import subprocess
import time
from pathlib import Path

def find_android_sdk():
    """Find Android SDK path"""
    possible_paths = [
        r"C:\Users\Roshan\AppData\Local\Android\Sdk",
        os.path.expanduser("~/AppData/Local/Android/Sdk"),
        os.path.expanduser("~/Android/Sdk"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def create_avd(avd_name: str, account_id: int):
    """Create a new AVD for a specific account"""
    sdk_path = find_android_sdk()
    if not sdk_path:
        print("❌ Android SDK not found")
        return False
    
    avdmanager = os.path.join(sdk_path, "cmdline-tools", "latest", "bin", "avdmanager.bat")
    if not os.path.exists(avdmanager):
        avdmanager = os.path.join(sdk_path, "tools", "bin", "avdmanager.bat")
    
    if not os.path.exists(avdmanager):
        print(f"❌ avdmanager not found for account {account_id}")
        return False
    
    print(f"🚀 Creating AVD: {avd_name} for Account {account_id}...")
    
    # Create AVD command with Android 14 system image
    cmd = [
        avdmanager,
        "create", "avd",
        "--name", avd_name,
        "--package", "system-images;android-34;google_apis;x86_64",
        "--device", "pixel_6",
        "--force"  # Overwrite if exists
    ]
    
    try:
        # Run with 'no' input to accept defaults
        result = subprocess.run(
            cmd,
            input="no\n",  # Decline hardware profile customization
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"✅ Account {account_id}: AVD {avd_name} created successfully")
            
            # Configure the AVD for optimal performance
            configure_avd(avd_name, account_id)
            return True
        else:
            print(f"❌ Account {account_id}: Failed to create AVD")
            print(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Account {account_id}: Exception creating AVD: {e}")
        return False

def configure_avd(avd_name: str, account_id: int):
    """Configure AVD settings for better performance and proper display"""
    avd_path = Path.home() / ".android" / "avd" / f"{avd_name}.avd" / "config.ini"
    
    if not avd_path.exists():
        print(f"⚠️  Account {account_id}: Config file not found at {avd_path}")
        return
    
    # Read current config
    with open(avd_path, 'r', encoding='utf-8') as f:
        config_lines = f.readlines()
    
    # Update specific settings
    new_config = []
    settings_updated = set()
    
    optimized_settings = {
        'hw.lcd.width': '1080',
        'hw.lcd.height': '2400', 
        'hw.lcd.density': '420',
        'hw.ramSize': '2048',
        'vm.heapSize': '256',
        'hw.gpu.enabled': 'yes',
        'hw.gpu.mode': 'host',
        'hw.keyboard': 'yes',
        'hw.sensors.orientation': 'yes',
        'hw.sensors.proximity': 'yes',
        'hw.dPad': 'no',
        'hw.gsmModem': 'yes',
        'hw.gps': 'yes',
        'hw.camera.back': 'emulated',
        'hw.camera.front': 'emulated',
        'hw.audioInput': 'yes',
        'hw.audioOutput': 'yes',
        'runtime.network.latency': 'none',
        'runtime.network.speed': 'full',
        'hw.device.name': f'SipDialer_Account_{account_id}'
    }
    
    # Update existing lines or mark for addition
    for line in config_lines:
        line = line.strip()
        if '=' in line:
            key = line.split('=')[0].strip()
            if key in optimized_settings:
                new_config.append(f"{key} = {optimized_settings[key]}\n")
                settings_updated.add(key)
            else:
                new_config.append(line + "\n")
        else:
            new_config.append(line + "\n")
    
    # Add missing settings
    for key, value in optimized_settings.items():
        if key not in settings_updated:
            new_config.append(f"{key} = {value}\n")
    
    # Write updated config
    try:
        with open(avd_path, 'w', encoding='utf-8') as f:
            f.writelines(new_config)
        print(f"✅ Account {account_id}: AVD configured with 1080x2400 display and optimizations")
    except Exception as e:
        print(f"❌ Account {account_id}: Failed to update config: {e}")

def main():
    print("🏗️  Creating Individual AVDs for Each Account")
    print("=" * 50)
    
    # Get account count from config manager
    try:
        from config_manager import ConfigManager
        config_manager = ConfigManager()
        accounts = config_manager.config.get("accounts", {})
        account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
    except:
        # Fallback to 2 accounts if config manager fails
        account_ids = [1, 2]
    
    # Create individual AVDs for configured accounts
    avd_names = []
    for account_id in account_ids:
        avd_name = f"SipDialer_Account_{account_id}"
        avd_names.append(avd_name)
        
        success = create_avd(avd_name, account_id)
        if not success:
            print(f"⚠️  Failed to create AVD for Account {account_id}, continuing with others...")
        
        # Small delay between creations
        time.sleep(1)
    
    print("\n📋 Summary of Created AVDs:")
    print("-" * 30)
    
    # List all AVDs to verify
    sdk_path = find_android_sdk()
    if sdk_path:
        emulator_exe = os.path.join(sdk_path, "emulator", "emulator.exe")
        try:
            result = subprocess.run([emulator_exe, "-list-avds"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                existing_avds = result.stdout.strip().split('\n')
                for i, avd_name in enumerate(avd_names, 1):
                    if avd_name in existing_avds:
                        print(f"✅ Account {i}: {avd_name}")
                    else:
                        print(f"❌ Account {i}: {avd_name} (creation failed)")
            else:
                print("⚠️  Could not list AVDs to verify")
        except Exception as e:
            print(f"⚠️  Error listing AVDs: {e}")
    
    print("\n🎯 Next Steps:")
    print("1. Update config.json to assign each account its unique AVD")
    print("2. Test launching multiple emulators with separate data")
    print("3. Each emulator will now have independent app data and settings")

if __name__ == "__main__":
    main()