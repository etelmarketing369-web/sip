#!/usr/bin/env python3
"""
Android SDK and Emulator Installer
Handles automated installation of Android SDK, emulator, and Android 14 system images
"""

import os
import sys
import subprocess
import threading
import time
import zipfile
import requests
from pathlib import Path
from typing import Callable, Optional, Dict, Any
import json
import tempfile
import shutil

from config_manager import ConfigManager

class AndroidInstaller:
    """Manages Android SDK and emulator installation workflow."""
    
    def __init__(self):
        self.android_home = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
        self.progress_callback: Optional[Callable[[str, int], None]] = None
        self.status_callback: Optional[Callable[[str], None]] = None
        
        # Android SDK URLs (latest command line tools)
        self.sdk_tools_url = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
        self.android_14_api_level = "34"
        
    def set_progress_callback(self, callback: Callable[[str, int], None]):
        """Set callback for progress updates (message, percentage)"""
        self.progress_callback = callback
        
    def set_status_callback(self, callback: Callable[[str], None]):
        """Set callback for status updates"""
        self.status_callback = callback
        
    def _update_progress(self, message: str, percentage: int):
        """Update progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(message, percentage)
            
    def _update_status(self, message: str):
        """Update status if callback is set"""
        if self.status_callback:
            self.status_callback(message)
            print(f"[AndroidInstaller] {message}")
            
    def is_sdk_installed(self) -> bool:
        """Check if Android SDK is already installed"""
        sdk_manager = os.path.join(self.android_home, "cmdline-tools", "latest", "bin", "sdkmanager.bat")
        return os.path.exists(sdk_manager)
        
    def is_emulator_installed(self) -> bool:
        """Check if Android emulator is installed"""
        emulator_exe = os.path.join(self.android_home, "emulator", "emulator.exe")
        return os.path.exists(emulator_exe)
        
    def is_android_14_installed(self) -> bool:
        """Check if Android 14 system image is installed"""
        system_image_path = os.path.join(
            self.android_home, "system-images", f"android-{self.android_14_api_level}", 
            "google_apis", "x86_64"
        )
        return os.path.exists(system_image_path)
        
    def get_avd_list(self) -> list:
        """Get list of existing Android Virtual Devices"""
        try:
            avd_manager = os.path.join(self.android_home, "cmdline-tools", "latest", "bin", "avdmanager.bat")
            if not os.path.exists(avd_manager):
                return []
                
            result = subprocess.run(
                [avd_manager, "list", "avd"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            avds = []
            for line in result.stdout.splitlines():
                if line.strip().startswith("Name:"):
                    avd_name = line.split(":", 1)[1].strip()
                    avds.append(avd_name)
            return avds
            
        except Exception as e:
            self._update_status(f"Error listing AVDs: {e}")
            return []
    
    def download_file(self, url: str, dest_path: str) -> bool:
        """Download file with progress tracking"""
        try:
            self._update_status(f"Downloading {os.path.basename(dest_path)}...")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            percentage = int((downloaded / total_size) * 100)
                            self._update_progress(f"Downloading {os.path.basename(dest_path)}", percentage)
                            
            self._update_status(f"Downloaded {os.path.basename(dest_path)} successfully")
            return True
            
        except Exception as e:
            self._update_status(f"Download failed: {e}")
            return False
            
    def install_sdk_tools(self) -> bool:
        """Download and install Android SDK command line tools"""
        try:
            self._update_status("Installing Android SDK Command Line Tools...")
            
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "commandlinetools.zip")
                
                # Download SDK tools
                if not self.download_file(self.sdk_tools_url, zip_path):
                    return False
                    
                self._update_progress("Extracting SDK tools", 0)
                
                # Extract to Android SDK directory
                os.makedirs(self.android_home, exist_ok=True)
                cmdline_tools_dir = os.path.join(self.android_home, "cmdline-tools")
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(cmdline_tools_dir)
                    
                # Move cmdline-tools/cmdline-tools to cmdline-tools/latest (required structure)
                old_path = os.path.join(cmdline_tools_dir, "cmdline-tools")
                new_path = os.path.join(cmdline_tools_dir, "latest")
                
                if os.path.exists(old_path):
                    if os.path.exists(new_path):
                        shutil.rmtree(new_path)
                    shutil.move(old_path, new_path)
                    
                self._update_progress("SDK tools installed", 100)
                return True
                
        except Exception as e:
            self._update_status(f"SDK tools installation failed: {e}")
            return False
            
    def run_sdk_command(self, args: list, timeout: int = 300) -> bool:
        """Run sdkmanager command with proper environment"""
        try:
            sdk_manager = os.path.join(self.android_home, "cmdline-tools", "latest", "bin", "sdkmanager.bat")
            if not os.path.exists(sdk_manager):
                self._update_status("SDK Manager not found")
                return False
                
            # Set environment variables
            env = os.environ.copy()
            env["ANDROID_HOME"] = self.android_home
            env["ANDROID_SDK_ROOT"] = self.android_home
            
            cmd = [sdk_manager] + args
            self._update_status(f"Running: {' '.join(args)}")
            
            # Run with automatic license acceptance
            process = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Send 'y' responses for license acceptance
            try:
                stdout, stderr = process.communicate(input="y\ny\ny\ny\ny\n", timeout=timeout)
                
                if process.returncode == 0:
                    self._update_status("Command completed successfully")
                    return True
                else:
                    self._update_status(f"Command failed with code {process.returncode}")
                    if stderr:
                        self._update_status(f"Error output: {stderr[:200]}...")
                    return False
                    
            except subprocess.TimeoutExpired:
                process.kill()
                self._update_status("Command timed out")
                return False
                
        except Exception as e:
            self._update_status(f"Command execution failed: {e}")
            return False
            
    def install_platform_tools(self) -> bool:
        """Install Android platform tools (adb, fastboot)"""
        self._update_status("Installing Android Platform Tools...")
        return self.run_sdk_command(["platform-tools"])
        
    def install_emulator(self) -> bool:
        """Install Android Emulator"""
        self._update_status("Installing Android Emulator...")
        return self.run_sdk_command(["emulator"])
        
    def install_android_14(self) -> bool:
        """Install Android 14 platform and system images"""
        self._update_status("Installing Android 14 platform...")
        
        # Install platform
        if not self.run_sdk_command([f"platforms;android-{self.android_14_api_level}"]):
            return False
            
        self._update_status("Installing Android 14 system image (x86_64)...")
        
        # Install system image
        system_image = f"system-images;android-{self.android_14_api_level};google_apis;x86_64"
        return self.run_sdk_command([system_image])
        
    def create_android_14_avd_with_display(self, avd_name: str = "SipDialer_Android14", resolution: str = "1080x2400") -> bool:
        """Create an Android 14 AVD with specific display resolution"""
        try:
            self._update_status(f"Creating Android 14 AVD with {resolution} display: {avd_name}")
            
            avd_manager = os.path.join(self.android_home, "cmdline-tools", "latest", "bin", "avdmanager.bat")
            if not os.path.exists(avd_manager):
                return False
                
            # Set environment variables
            env = os.environ.copy()
            env["ANDROID_HOME"] = self.android_home
            env["ANDROID_SDK_ROOT"] = self.android_home
            
            # Create AVD command with device specification
            system_image = f"system-images;android-{self.android_14_api_level};google_apis;x86_64"
            cmd = [
                avd_manager, "create", "avd",
                "--name", avd_name,
                "--package", system_image,
                "--device", "pixel_6",  # Use Pixel 6 as base (has 1080x2400 display)
                "--force"  # Overwrite if exists
            ]
            
            process = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Provide default responses
            input_text = "no\n"  # Custom hardware profile? no
            stdout, stderr = process.communicate(input=input_text, timeout=60)
            
            if process.returncode == 0:
                # Now customize the config.ini file to ensure exact resolution
                self._customize_avd_config(avd_name, resolution)
                self._update_status(f"AVD '{avd_name}' created successfully with {resolution} display")
                return True
            else:
                self._update_status(f"AVD creation failed: {stderr}")
                return False
                
        except Exception as e:
            self._update_status(f"Error creating AVD: {e}")
            return False

    def _customize_avd_config(self, avd_name: str, resolution: str):
        """Customize AVD config.ini for specific display settings"""
        try:
            avd_path = os.path.join(os.path.expanduser("~"), ".android", "avd", f"{avd_name}.avd")
            config_ini_path = os.path.join(avd_path, "config.ini")
            
            if not os.path.exists(config_ini_path):
                self._update_status(f"Warning: config.ini not found at {config_ini_path}")
                return
            
            # Parse resolution
            width, height = resolution.split('x')
            
            # Read existing config
            config_lines = []
            with open(config_ini_path, 'r', encoding='utf-8') as f:
                config_lines = f.readlines()
            
            # Update or add display settings
            updated_lines = []
            settings_to_set = {
                'hw.lcd.width': width,
                'hw.lcd.height': height,
                'hw.lcd.density': '440',  # Standard density for 1080p phones
                'skin.name': f'{width}x{height}',
                'skin.path': f'{width}x{height}',
                'hw.device.name': 'pixel_6',
                'hw.gpu.enabled': 'yes',
                'hw.gpu.mode': 'auto'
            }
            
            # Track which settings we've updated
            updated_keys = set()
            
            for line in config_lines:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    if key in settings_to_set:
                        updated_lines.append(f"{key}={settings_to_set[key]}\n")
                        updated_keys.add(key)
                    else:
                        updated_lines.append(line + '\n')
                else:
                    updated_lines.append(line + '\n')
            
            # Add any missing settings
            for key, value in settings_to_set.items():
                if key not in updated_keys:
                    updated_lines.append(f"{key}={value}\n")
            
            # Write updated config
            with open(config_ini_path, 'w', encoding='utf-8') as f:
                f.writelines(updated_lines)
            
            self._update_status(f"AVD config updated for {resolution} display")
            
        except Exception as e:
            self._update_status(f"Warning: Could not customize AVD config: {e}")

    def create_android_14_avd(self, avd_name: str = "SipDialer_Android14") -> bool:
        """Create an Android 14 AVD"""
        try:
            self._update_status(f"Creating Android 14 AVD: {avd_name}")
            
            avd_manager = os.path.join(self.android_home, "cmdline-tools", "latest", "bin", "avdmanager.bat")
            if not os.path.exists(avd_manager):
                return False
                
            # Set environment variables
            env = os.environ.copy()
            env["ANDROID_HOME"] = self.android_home
            env["ANDROID_SDK_ROOT"] = self.android_home
            
            # Create AVD command
            system_image = f"system-images;android-{self.android_14_api_level};google_apis;x86_64"
            cmd = [
                avd_manager, "create", "avd",
                "--name", avd_name,
                "--package", system_image,
                "--force"  # Overwrite if exists
            ]
            
            process = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Provide default responses
            input_text = "no\n"  # Custom hardware profile? no
            stdout, stderr = process.communicate(input=input_text, timeout=60)
            
            if process.returncode == 0:
                self._update_status(f"AVD '{avd_name}' created successfully")
                return True
            else:
                self._update_status(f"AVD creation failed: {stderr}")
                return False
                
        except Exception as e:
            self._update_status(f"AVD creation failed: {e}")
            return False
    
    def configure_accounts_with_avd(self, config_manager, avd_name: str = "SipDialer_Android14") -> bool:
        """Configure all SIP accounts to use the newly created AVD"""
        try:
            self._update_status(f"Configuring accounts to use AVD: {avd_name}")

            # Set the AVD for every configured account
            account_ids = config_manager.get_enabled_accounts()
            for account_id in account_ids:
                account_config = {
                    "emulator_avd": avd_name
                }
                if not config_manager.set_account_config(account_id, account_config):
                    self._update_status(f"Warning: Failed to configure AVD for account {account_id}")
            
            # Save configuration
            if config_manager.save_config():
                self._update_status("✅ All accounts configured with Android 14 AVD")
                return True
            else:
                self._update_status("❌ Failed to save account configuration")
                return False
                
        except Exception as e:
            self._update_status(f"Account configuration failed: {e}")
            return False
            
    def install_complete_setup(self, progress_callback: Optional[Callable] = None, config_manager = None) -> bool:
        """Install complete Android development setup with Android 14"""
        try:
            # Ensure we have a config manager for account lookups/updates
            active_config_manager = config_manager or ConfigManager()

            if progress_callback:
                progress_callback("Starting installation...", 0)
                
            # Step 1: Install SDK tools (20%)
            self._update_progress("Installing SDK tools", 5)
            if not self.is_sdk_installed():
                if not self.install_sdk_tools():
                    return False
            self._update_progress("SDK tools ready", 20)
            
            # Step 2: Install platform tools (40%)
            self._update_progress("Installing platform tools", 25)
            if not self.install_platform_tools():
                return False
            self._update_progress("Platform tools installed", 40)
            
            # Step 3: Install emulator (60%)
            self._update_progress("Installing emulator", 45)
            if not self.install_emulator():
                return False
            self._update_progress("Emulator installed", 60)
            
            # Step 4: Install Android 14 (80%)
            self._update_progress("Installing Android 14", 65)
            if not self.install_android_14():
                return False
            self._update_progress("Android 14 installed", 80)


            # Step 5: Create individual AVDs for each account (90%)
            # Get account count from config manager
            accounts = active_config_manager.config.get("accounts", {})
            account_ids = sorted([int(k) for k in accounts.keys() if k.isdigit()])
            if not account_ids:
                self._update_status("No SIP accounts found in configuration; skipping AVD creation")
                return True
            
            self._update_progress(f"Creating individual AVDs for {len(account_ids)} accounts", 85)
            avd_creation_success = True
            for account_id in account_ids:
                avd_name = f"SipDialer_Account_{account_id}"
                if not self.create_android_14_avd_with_display(avd_name, "1080x2400"):
                    self._update_status(f"Failed to create AVD for account {account_id}")
                    avd_creation_success = False
                    break
            
            if not avd_creation_success:
                return False
            
            self._update_progress(f"All {len(account_ids)} AVDs created successfully", 95)
            
            # Step 6: Configure accounts with individual AVDs (100%)
            self._update_progress("Configuring accounts with individual AVDs", 98)
            configured_count = 0
            for account_id in account_ids:
                avd_name = f"SipDialer_Account_{account_id}"
                account_config = {"emulator_avd": avd_name}
                if active_config_manager.set_account_config(account_id, account_config):
                    configured_count += 1

            if configured_count == len(account_ids) and active_config_manager.save_config():
                self._update_progress("All accounts configured with separate AVDs", 100)
            else:
                self._update_status(f"Warning: Only {configured_count}/{len(account_ids)} accounts configured")
                return False

            self._update_progress("Installation complete!", 100)
            self._update_status("✅ Android SDK and Android 14 emulator installed successfully!")
            return True
            
        except Exception as e:
            self._update_status(f"Installation failed: {e}")
            return False
            
    def get_installation_status(self) -> Dict[str, Any]:
        """Get current installation status"""
        return {
            "sdk_installed": self.is_sdk_installed(),
            "emulator_installed": self.is_emulator_installed(),
            "android_14_installed": self.is_android_14_installed(),
            "avd_list": self.get_avd_list(),
            "android_home": self.android_home
        }

def install_android_async(installer: AndroidInstaller, config_manager, callback: Callable[[bool, str], None]):
    """Run installation in background thread"""
    def worker():
        try:
            success = installer.install_complete_setup(config_manager=config_manager)
            message = "Installation completed successfully!" if success else "Installation failed"
            callback(success, message)
        except Exception as e:
            callback(False, f"Installation error: {e}")
            
    threading.Thread(target=worker, daemon=True).start()