#!/usr/bin/env python3
"""
SIMPLE VOICE CALL MAKER
Quick solution for making WhatsApp voice calls
"""

import sys
import os

def make_quick_call(phone_number: str):
    """Make a quick voice call using the comprehensive solution"""
    try:
        # Import our voice call solution
        from voice_call_solution import WhatsAppVoiceCaller
        
        caller = WhatsAppVoiceCaller()
        success = caller.make_voice_call(phone_number)
        
        if success:
            print(f"\n✅ Voice call process completed for {phone_number}")
            print("🎉 Check WhatsApp Desktop - the call should have started!")
            return True
        else:
            print(f"\n❌ Voice call failed for {phone_number}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("📞 QUICK VOICE CALL MAKER")
    print("=" * 30)
    
    if len(sys.argv) > 1:
        # Phone number provided as command line argument
        phone_number = sys.argv[1]
        print(f"Calling {phone_number}...")
        make_quick_call(phone_number)
    else:
        # Interactive mode
        print("Enter phone number to call (with country code)")
        print()
        
        while True:
            phone = input("Phone number (or 'quit' to exit): ").strip()
            
            if phone.lower() in ['quit', 'q', 'exit']:
                print("👋 Goodbye!")
                break
            elif phone:
                print(f"\n🔄 Calling {phone}...")
                make_quick_call(phone)
                print("\n" + "-" * 40)
            else:
                print("❌ Please enter a phone number")