#!/usr/bin/env python3
"""
Auto-map 8 SIP accounts to distinct Voicemeeter virtual devices (Point 1..8).
- Output:  Output (Voicemeeter Point N)
- Input:   Input  (Voicemeeter Point N)
If fewer than 8 pairs are found, maps what is available.
"""
from audio_device_manager import AudioDeviceManager
from config_manager import ConfigManager

PREFIX_OUT = "Output (Voicemeeter Point "
PREFIX_IN  = "Input (Voicemeeter Point "

def find_point_devices(adm: AudioDeviceManager):
    outs = {}
    ins = {}
    for d in adm.get_output_devices():
        name = d.get('name','')
        if name.startswith(PREFIX_OUT) and name.rstrip().endswith(')'):
            # Extract number
            try:
                num = int(name[len(PREFIX_OUT):-1].strip())
                outs[num] = d['id']
            except Exception:
                pass
    for d in adm.get_input_devices():
        name = d.get('name','')
        if name.startswith(PREFIX_IN) and name.rstrip().endswith(')'):
            try:
                num = int(name[len(PREFIX_IN):-1].strip())
                ins[num] = d['id']
            except Exception:
                pass
    # Build sorted lists by point number
    out_list = [outs[n] for n in sorted(outs.keys())]
    in_list  = [ins[n] for n in sorted(ins.keys())]
    return in_list, out_list


def main():
    adm = AudioDeviceManager()
    cfg = ConfigManager()
    try:
        in_list, out_list = find_point_devices(adm)
        pairs = min(8, len(in_list), len(out_list))
        if pairs == 0:
            print("No Voicemeeter Point devices found. Nothing changed.")
            return 1
        for i in range(pairs):
            acct = i  # accounts 0..7
            in_id = in_list[i]
            out_id = out_list[i]
            cfg.set_account_audio_devices(acct, in_id, out_id)
            print(f"Mapped Account {acct+1} -> Input id {in_id}, Output id {out_id}")
        print("Saved device mapping to config.json. New calls will use these devices.")
        return 0
    finally:
        adm.cleanup()

if __name__ == '__main__':
    raise SystemExit(main())
