#!/usr/bin/env python3
"""
Configuration Manager
Handles loading and saving application configuration
"""

import json
import os
from typing import Dict, List, Optional

class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self._load_default_config()
        self.load_config()
    
    def _load_default_config(self) -> dict:
        """Load default configuration"""
        return {
            "accounts": {
                "1": {
                    "enabled": True,
                    "username": "JEFF01",
                    "password": "112233",
                    "domain": "52.64.207.38",
                    "port": 5060,
                    "transport": "UDP",
                    "proxy": "",
                    "display_name": "Account 1",
                    "auto_register": True,
                    "audio_input_device_id": -1,
                    "audio_output_device_id": -1,
                    "emulator_port": 5554,
                    "emulator_avd": "SipDialer_Account_1",
                    "whatsapp_tap_x": 230,
                    "whatsapp_tap_y": 130,
                    "whatsapp_tap_delay_ms": 1200,
                    "whatsapp_step1_x": 230,
                    "whatsapp_step1_y": 130,
                    "whatsapp_step_delay_ms": 800,
                    "whatsapp_step2_x": 130,
                    "whatsapp_step2_y": 800,
                    "whatsapp_step3_x": 590,
                    "whatsapp_step3_y": 980,
                    "whatsapp_step3_delay_ms": 1500
                },
                "2": {
                    "enabled": True,
                    "username": "JEFF0",
                    "password": "112233",
                    "domain": "52.64.207.38",
                    "port": 5060,
                    "transport": "UDP",
                    "proxy": "",
                    "display_name": "Account 2",
                    "auto_register": True,
                    "audio_input_device_id": -1,
                    "audio_output_device_id": -1,
                    "emulator_port": 5556,
                    "emulator_avd": "SipDialer_Account_2",
                    "whatsapp_tap_x": 230,
                    "whatsapp_tap_y": 130,
                    "whatsapp_tap_delay_ms": 1200,
                    "whatsapp_step1_x": 230,
                    "whatsapp_step1_y": 130,
                    "whatsapp_step_delay_ms": 800,
                    "whatsapp_step2_x": 130,
                    "whatsapp_step2_y": 800,
                    "whatsapp_step3_x": 590,
                    "whatsapp_step3_y": 980,
                    "whatsapp_step3_delay_ms": 1500
                }
            },
            "audio": {
                "input_device": -1,
                "output_device": -1,
                "echo_cancellation": True,
                "noise_suppression": True,
                "auto_gain": True,
                "input_volume": 80,
                "output_volume": 80
            },
            "general": {
                "auto_answer": False,
                "auto_answer_delay": 3,
                "call_recording": False,
                "recording_path": "recordings",
                "log_level": "INFO",
                "startup_minimize": False,
                "system_tray": True
            },
            "codecs": {
                "priority": ["PCMU", "PCMA", "G722", "G729", "GSM", "SPEEX"],
                "bandwidth": "normal"
            },
            "gui": {
                "theme": "default",
                "window_size": "1200x800",
                "always_on_top": False,
                "show_call_duration": True,
                "show_account_status": True
            }
        }
    
    def load_config(self) -> bool:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # Merge with default config to ensure all keys exist
                self._merge_config(self.config, loaded_config)
                print(f"Configuration loaded from {self.config_file}")
                return True
            else:
                print(f"Configuration file {self.config_file} not found, using defaults")
                self.save_config()
                return True
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return False
    
    def save_config(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            print(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def _merge_config(self, default: dict, loaded: dict):
        """Recursively merge loaded config with default config"""
        for key, value in loaded.items():
            if key in default:
                if isinstance(value, dict) and isinstance(default[key], dict):
                    self._merge_config(default[key], value)
                else:
                    default[key] = value
    
    def get_account_config(self, account_id: int) -> Optional[dict]:
        """Get configuration for a specific account with enforced SIP settings"""
        account_key = str(account_id)
        if account_key in self.config["accounts"]:
            config = self.config["accounts"][account_key].copy()

            default_usernames = {
                1: "JEFF01",
                2: "JEFF0"
            }
            if account_id in default_usernames:
                default_username = default_usernames[account_id]
                current_username = config.get("username", "")
                if (not current_username
                        or current_username.startswith("VAPO")
                        or current_username == f"1{account_id:03d}"):
                    config["username"] = default_username
            # Enforce fixed SIP settings
            config["password"] = "112233"
            config["domain"] = "52.64.207.38"
            config["port"] = 5060
            config["transport"] = "UDP"
            config["enabled"] = True
            config["auto_register"] = True
            # Ensure audio device keys exist
            if "audio_input_device_id" not in config:
                config["audio_input_device_id"] = -1
            if "audio_output_device_id" not in config:
                config["audio_output_device_id"] = -1
            # Ensure emulator_port exists
            if "emulator_port" not in config:
                # Default mapping: 5554 + 2*(account_index-1)
                config["emulator_port"] = 5554 + ((account_id - 1) * 2)
            return config
        return None
    
    def set_account_config(self, account_id: int, config: dict) -> bool:
        """Set configuration for a specific account (only username can be changed)"""
        try:
            account_key = str(account_id)
            if account_key in self.config["accounts"]:
                # Only allow username to be changed, other settings remain fixed
                if "username" in config:
                    self.config["accounts"][account_key]["username"] = config["username"]
                # Allow setting per-account audio device IDs
                if "audio_input_device_id" in config:
                    self.config["accounts"][account_key]["audio_input_device_id"] = int(config["audio_input_device_id"])
                if "audio_output_device_id" in config:
                    self.config["accounts"][account_key]["audio_output_device_id"] = int(config["audio_output_device_id"])
                # Allow setting emulator_port
                if "emulator_port" in config:
                    self.config["accounts"][account_key]["emulator_port"] = int(config["emulator_port"])
                # Allow setting preferred AVD name
                if "emulator_avd" in config:
                    self.config["accounts"][account_key]["emulator_avd"] = str(config["emulator_avd"])
                # Allow setting WhatsApp tap coordinates and delay
                if "whatsapp_tap_x" in config:
                    self.config["accounts"][account_key]["whatsapp_tap_x"] = int(config["whatsapp_tap_x"])
                if "whatsapp_tap_y" in config:
                    self.config["accounts"][account_key]["whatsapp_tap_y"] = int(config["whatsapp_tap_y"])
                if "whatsapp_tap_delay_ms" in config:
                    self.config["accounts"][account_key]["whatsapp_tap_delay_ms"] = int(config["whatsapp_tap_delay_ms"])
                # Two-step fields
                if "whatsapp_step1_x" in config:
                    self.config["accounts"][account_key]["whatsapp_step1_x"] = int(config["whatsapp_step1_x"])
                if "whatsapp_step1_y" in config:
                    self.config["accounts"][account_key]["whatsapp_step1_y"] = int(config["whatsapp_step1_y"])
                if "whatsapp_step_delay_ms" in config:
                    self.config["accounts"][account_key]["whatsapp_step_delay_ms"] = int(config["whatsapp_step_delay_ms"])
                if "whatsapp_step2_x" in config:
                    # Allow blank to clear
                    val = config["whatsapp_step2_x"]
                    self.config["accounts"][account_key]["whatsapp_step2_x"] = ("" if str(val).strip() == "" else int(val))
                if "whatsapp_step2_y" in config:
                    val = config["whatsapp_step2_y"]
                    self.config["accounts"][account_key]["whatsapp_step2_y"] = ("" if str(val).strip() == "" else int(val))
                # Step 3 optional
                if "whatsapp_step3_x" in config:
                    val = config["whatsapp_step3_x"]
                    self.config["accounts"][account_key]["whatsapp_step3_x"] = ("" if str(val).strip() == "" else int(val))
                if "whatsapp_step3_y" in config:
                    val = config["whatsapp_step3_y"]
                    self.config["accounts"][account_key]["whatsapp_step3_y"] = ("" if str(val).strip() == "" else int(val))
                if "whatsapp_step3_delay_ms" in config:
                    val = config["whatsapp_step3_delay_ms"]
                    self.config["accounts"][account_key]["whatsapp_step3_delay_ms"] = ("" if str(val).strip() == "" else int(val))
                return True
            return False
        except Exception as e:
            print(f"Error setting account config: {e}")
            return False

    def get_account_audio_devices(self, account_id: int) -> tuple[int, int]:
        """Get per-account audio device IDs (input_id, output_id); -1 means default"""
        cfg = self.get_account_config(account_id) or {}
        return int(cfg.get("audio_input_device_id", -1)), int(cfg.get("audio_output_device_id", -1))

    def set_account_audio_devices(self, account_id: int, input_device_id: int | None, output_device_id: int | None) -> bool:
        """Set per-account audio device IDs (-1 or None means default)"""
        update = {}
        if input_device_id is not None:
            update["audio_input_device_id"] = int(input_device_id)
        if output_device_id is not None:
            update["audio_output_device_id"] = int(output_device_id)
        ok = self.set_account_config(account_id, update)
        if ok:
            self.save_config()
        return ok

    def get_account_emulator_port(self, account_id: int) -> int:
        """Return the emulator port mapped to this account (e.g., 5554, 5556, ...)."""
        cfg = self.get_account_config(account_id) or {}
        return int(cfg.get("emulator_port", 5554 + account_id * 2))

    def set_account_emulator_port(self, account_id: int, port: int) -> bool:
        """Set the emulator port for this account and persist it."""
        ok = self.set_account_config(account_id, {"emulator_port": int(port)})
        if ok:
            self.save_config()
        return ok
    
    def get_enabled_accounts(self) -> List[int]:
        """Get list of enabled account IDs - dynamically read from config"""
        accounts = self.config.get("accounts", {})
        return sorted([int(k) for k in accounts.keys() if k.isdigit()])
    
    def get_audio_config(self) -> dict:
        """Get audio configuration"""
        return self.config["audio"].copy()
    
    def set_audio_config(self, config: dict) -> bool:
        """Set audio configuration"""
        try:
            self.config["audio"].update(config)
            return True
        except Exception as e:
            print(f"Error setting audio config: {e}")
            return False
    
    def get_general_config(self) -> dict:
        """Get general configuration"""
        return self.config["general"].copy()
    
    def set_general_config(self, config: dict) -> bool:
        """Set general configuration"""
        try:
            self.config["general"].update(config)
            return True
        except Exception as e:
            print(f"Error setting general config: {e}")
            return False
    
    def get_codec_config(self) -> dict:
        """Get codec configuration"""
        return self.config["codecs"].copy()
    
    def set_codec_config(self, config: dict) -> bool:
        """Set codec configuration"""
        try:
            self.config["codecs"].update(config)
            return True
        except Exception as e:
            print(f"Error setting codec config: {e}")
            return False
    
    def get_gui_config(self) -> dict:
        """Get GUI configuration"""
        return self.config["gui"].copy()
    
    def set_gui_config(self, config: dict) -> bool:
        """Set GUI configuration"""
        try:
            self.config["gui"].update(config)
            return True
        except Exception as e:
            print(f"Error setting GUI config: {e}")
            return False
    
    def validate_account_config(self, config: dict) -> tuple[bool, str]:
        """Validate account configuration"""
        required_fields = ["username", "domain"]
        
        for field in required_fields:
            if not config.get(field, "").strip():
                return False, f"Required field '{field}' is empty"
        
        # Validate port
        try:
            port = int(config.get("port", 5060))
            if port < 1 or port > 65535:
                return False, "Port must be between 1 and 65535"
        except ValueError:
            return False, "Port must be a valid number"
        
        # Validate transport
        valid_transports = ["UDP", "TCP", "TLS"]
        if config.get("transport", "UDP") not in valid_transports:
            return False, f"Transport must be one of: {', '.join(valid_transports)}"
        
        return True, "Configuration is valid"
    
    def export_config(self, filename: str) -> bool:
        """Export configuration to a file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error exporting configuration: {e}")
            return False
    
    def import_config(self, filename: str) -> bool:
        """Import configuration from a file"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # Validate imported config structure
            if self._validate_config_structure(imported_config):
                self.config = self._load_default_config()
                self._merge_config(self.config, imported_config)
                self.save_config()
                return True
            else:
                print("Invalid configuration structure")
                return False
        except Exception as e:
            print(f"Error importing configuration: {e}")
            return False
    
    def _validate_config_structure(self, config: dict) -> bool:
        """Validate the structure of imported configuration"""
        required_sections = ["accounts", "audio", "general", "codecs", "gui"]
        
        for section in required_sections:
            if section not in config:
                return False
        
        # Validate accounts section
        if not isinstance(config["accounts"], dict):
            return False
        
        return True
    
    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = self._load_default_config()
        self.save_config()
    
    def get_all_config(self) -> dict:
        """Get complete configuration"""
        return self.config.copy()

# Example usage
if __name__ == "__main__":
    config_manager = ConfigManager()
    
    # Test account configuration
    account_config = {
        "enabled": True,
        "username": "testuser",
        "password": "testpass",
        "domain": "sip.example.com",
        "port": 5060,
        "transport": "UDP",
        "display_name": "Test User"
    }
    
    # Validate and set account config
    valid, message = config_manager.validate_account_config(account_config)
    if valid:
        config_manager.set_account_config(0, account_config)
        config_manager.save_config()
        print("Account configuration saved successfully")
    else:
        print(f"Invalid configuration: {message}")
    
    # Get enabled accounts
    enabled_accounts = config_manager.get_enabled_accounts()
    print(f"Enabled accounts: {enabled_accounts}")
    
    # Test audio configuration
    audio_config = config_manager.get_audio_config()
    print(f"Audio configuration: {audio_config}")
