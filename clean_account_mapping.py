#!/usr/bin/env python3

import json
import sys

def clean_account_mapping():
    """Reduce SIP account mapping to the supported two-account layout."""
    print("🔧 Cleaning SIP Account Mapping")
    print("=" * 50)

    TARGET_ACCOUNTS = {
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
    }

    try:
        with open('config.json', 'r') as f:
            config = json.load(f)

        old_accounts = config.get('accounts', {})
        new_accounts = {}

        for account_id, defaults in TARGET_ACCOUNTS.items():
            merged = defaults.copy()
            existing = old_accounts.get(account_id, {})

            # Preserve any overriding values present in existing config
            for key, value in existing.items():
                if key in merged:
                    merged[key] = value

            new_accounts[account_id] = merged
            print(f"✅ Account {account_id}: {merged['username']} -> Port {merged['emulator_port']}")

        removed = set(old_accounts.keys()) - set(TARGET_ACCOUNTS.keys())
        if removed:
            print(f"⚠️  Removing legacy accounts: {', '.join(sorted(removed))}")

        config['accounts'] = new_accounts

        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)

        print(f"\n🎯 Clean account mapping completed!")
        print(f"✅ Accounts 1-2 retained; higher-numbered accounts removed")

        return True

    except Exception as e:
        print(f"❌ Error cleaning account mapping: {e}")
        return False

if __name__ == "__main__":
    success = clean_account_mapping()
    sys.exit(0 if success else 1)