"""
Enhanced Windows Volume Mixer Integration using Windows Core Audio APIs
Properly sets application names in Windows Volume Mixer for each SIP account
"""

import ctypes
from ctypes import wintypes, POINTER, Structure, c_void_p, c_int, c_uint, c_wchar_p
import comtypes
from comtypes import GUID, CoClass, Interface, COMMETHOD, COMError
import threading
import time
import sys
import os

# Windows Core Audio API constants
CLSCTX_ALL = 23
STGM_READ = 0x00000000
AUDCLNT_SHAREMODE_SHARED = 0x00000000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000

# Audio format constants
WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3

class WAVEFORMATEX(Structure):
    _fields_ = [
        ('wFormatTag', wintypes.WORD),
        ('nChannels', wintypes.WORD),
        ('nSamplesPerSec', wintypes.DWORD),
        ('nAvgBytesPerSec', wintypes.DWORD),
        ('nBlockAlign', wintypes.WORD),
        ('wBitsPerSample', wintypes.WORD),
        ('cbSize', wintypes.WORD),
    ]

# Windows Audio Session API interfaces
class IUnknown(Interface):
    _iid_ = GUID('{00000000-0000-0000-C000-000000000046}')
    _methods_ = [
        COMMETHOD([], wintypes.HRESULT, 'QueryInterface'),
        COMMETHOD([], wintypes.ULONG, 'AddRef'),
        COMMETHOD([], wintypes.ULONG, 'Release'),
    ]

class IAudioSessionControl(Interface):
    _iid_ = GUID('{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}')
    _methods_ = [
        COMMETHOD([], wintypes.HRESULT, 'GetState'),
        COMMETHOD([], wintypes.HRESULT, 'GetDisplayName', (['out'], POINTER(wintypes.LPWSTR), 'pRetVal')),
        COMMETHOD([], wintypes.HRESULT, 'SetDisplayName', (['in'], wintypes.LPCWSTR, 'Value'), (['in'], POINTER(GUID), 'EventContext')),
        COMMETHOD([], wintypes.HRESULT, 'GetIconPath'),
        COMMETHOD([], wintypes.HRESULT, 'SetIconPath'),
        COMMETHOD([], wintypes.HRESULT, 'GetGroupingParam'),
        COMMETHOD([], wintypes.HRESULT, 'SetGroupingParam'),
        COMMETHOD([], wintypes.HRESULT, 'RegisterAudioSessionNotification'),
        COMMETHOD([], wintypes.HRESULT, 'UnregisterAudioSessionNotification'),
    ]

class IAudioClient(Interface):
    _iid_ = GUID('{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}')
    _methods_ = [
        COMMETHOD([], wintypes.HRESULT, 'Initialize'),
        COMMETHOD([], wintypes.HRESULT, 'GetBufferSize'),
        COMMETHOD([], wintypes.HRESULT, 'GetStreamLatency'),
        COMMETHOD([], wintypes.HRESULT, 'GetCurrentPadding'),
        COMMETHOD([], wintypes.HRESULT, 'IsFormatSupported'),
        COMMETHOD([], wintypes.HRESULT, 'GetMixFormat'),
        COMMETHOD([], wintypes.HRESULT, 'GetDevicePeriod'),
        COMMETHOD([], wintypes.HRESULT, 'Start'),
        COMMETHOD([], wintypes.HRESULT, 'Stop'),
        COMMETHOD([], wintypes.HRESULT, 'Reset'),
        COMMETHOD([], wintypes.HRESULT, 'SetEventHandle'),
        COMMETHOD([], wintypes.HRESULT, 'GetService', (['in'], POINTER(GUID), 'riid'), (['out'], POINTER(c_void_p), 'ppv')),
    ]

class IMMDevice(Interface):
    _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
    _methods_ = [
        COMMETHOD([], wintypes.HRESULT, 'Activate', 
                 (['in'], POINTER(GUID), 'iid'),
                 (['in'], wintypes.DWORD, 'dwClsCtx'), 
                 (['in'], c_void_p, 'pActivationParams'),
                 (['out'], POINTER(c_void_p), 'ppInterface')),
        COMMETHOD([], wintypes.HRESULT, 'OpenPropertyStore'),
        COMMETHOD([], wintypes.HRESULT, 'GetId'),
        COMMETHOD([], wintypes.HRESULT, 'GetState'),
    ]

class IMMDeviceEnumerator(Interface):
    _iid_ = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
    _methods_ = [
        COMMETHOD([], wintypes.HRESULT, 'EnumAudioEndpoints'),
        COMMETHOD([], wintypes.HRESULT, 'GetDefaultAudioEndpoint',
                 (['in'], wintypes.DWORD, 'dataFlow'),
                 (['in'], wintypes.DWORD, 'role'),
                 (['out'], POINTER(POINTER(IMMDevice)), 'ppEndpoint')),
        COMMETHOD([], wintypes.HRESULT, 'GetDevice'),
        COMMETHOD([], wintypes.HRESULT, 'RegisterEndpointNotificationCallback'),
        COMMETHOD([], wintypes.HRESULT, 'UnregisterEndpointNotificationCallback'),
    ]

class MMDeviceEnumerator(CoClass):
    _reg_clsid_ = GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
    _idlflags_ = []
    _typelib_ = None
    _reg_typelib_ = None

class WindowsAudioSessionManager:
    """Manages individual Windows Audio Sessions for SIP accounts"""
    
    def __init__(self):
        self.sessions = {}
        self.audio_clients = {}
        self.session_controls = {}
        
        # Initialize COM
        try:
            comtypes.CoInitialize()
            print("🔊 Windows Audio Session Manager initialized")
        except Exception as e:
            print(f"❌ Failed to initialize COM: {e}")
    
    def create_audio_session(self, account_id: int, account_name: str) -> bool:
        """Create a Windows Audio Session with custom display name"""
        try:
            # Get the default audio endpoint
            enumerator = comtypes.client.CreateObject(MMDeviceEnumerator)
            device = enumerator.GetDefaultAudioEndpoint(0, 0)  # eRender, eConsole
            
            # Activate the audio client
            audio_client_guid = GUID('{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}')
            audio_client_ptr = c_void_p()
            
            hr = device.Activate(
                ctypes.byref(audio_client_guid),
                CLSCTX_ALL,
                None,
                ctypes.byref(audio_client_ptr)
            )
            
            if hr != 0:
                print(f"❌ Failed to activate audio client for account {account_id}: {hex(hr)}")
                return False
            
            # Cast to IAudioClient interface
            audio_client = ctypes.cast(audio_client_ptr, POINTER(IAudioClient))
            
            # Get the mix format
            mix_format_ptr = ctypes.POINTER(WAVEFORMATEX)()
            hr = audio_client.GetMixFormat(ctypes.byref(mix_format_ptr))
            
            if hr != 0:
                print(f"❌ Failed to get mix format for account {account_id}: {hex(hr)}")
                return False
                
            # Initialize the audio client
            hr = audio_client.Initialize(
                AUDCLNT_SHAREMODE_SHARED,
                AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                0,  # hnsBufferDuration
                0,  # hnsPeriodicity 
                mix_format_ptr,
                None  # AudioSessionGuid
            )
            
            if hr != 0:
                print(f"❌ Failed to initialize audio client for account {account_id}: {hex(hr)}")
                return False
            
            # Get the audio session control
            session_control_guid = GUID('{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}')
            session_control_ptr = c_void_p()
            
            hr = audio_client.GetService(
                ctypes.byref(session_control_guid),
                ctypes.byref(session_control_ptr)
            )
            
            if hr != 0:
                print(f"❌ Failed to get session control for account {account_id}: {hex(hr)}")
                return False
                
            # Cast to IAudioSessionControl
            session_control = ctypes.cast(session_control_ptr, POINTER(IAudioSessionControl))
            
            # Set the display name for Volume Mixer
            display_name = f"SIP Account {account_id + 1} ({account_name})"
            event_context = GUID()
            
            hr = session_control.SetDisplayName(display_name, ctypes.byref(event_context))
            
            if hr != 0:
                print(f"❌ Failed to set display name for account {account_id}: {hex(hr)}")
                return False
            
            # Start the audio client to make it visible in Volume Mixer
            hr = audio_client.Start()
            
            if hr != 0:
                print(f"❌ Failed to start audio client for account {account_id}: {hex(hr)}")
                return False
            
            # Store references
            self.audio_clients[account_id] = audio_client
            self.session_controls[account_id] = session_control
            self.sessions[account_id] = {
                'account_name': account_name,
                'display_name': display_name,
                'active': True
            }
            
            print(f"✅ Created Windows Audio Session: '{display_name}'")
            return True
            
        except Exception as e:
            print(f"❌ Error creating audio session for account {account_id}: {e}")
            return False
    
    def remove_audio_session(self, account_id: int) -> bool:
        """Remove audio session for account"""
        try:
            if account_id in self.audio_clients:
                # Stop the audio client
                audio_client = self.audio_clients[account_id]
                audio_client.Stop()
                
                # Clean up references
                del self.audio_clients[account_id]
                del self.session_controls[account_id]
                del self.sessions[account_id]
                
                print(f"🗑️ Removed audio session for Account {account_id + 1}")
                return True
            else:
                print(f"⚠️ No audio session found for Account {account_id + 1}")
                return False
                
        except Exception as e:
            print(f"❌ Error removing audio session for account {account_id}: {e}")
            return False
    
    def get_active_sessions(self) -> dict:
        """Get list of active audio sessions"""
        return self.sessions.copy()
    
    def cleanup_all_sessions(self):
        """Clean up all audio sessions"""
        try:
            account_ids = list(self.sessions.keys())
            for account_id in account_ids:
                self.remove_audio_session(account_id)
            
            # Uninitialize COM
            comtypes.CoUninitialize()
            print("🧹 All Windows Audio Sessions cleaned up")
            
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

def test_windows_audio_sessions():
    """Test the Windows Audio Session integration"""
    print("🎬 Testing Windows Audio Session Integration")
    print("=" * 60)
    
    manager = WindowsAudioSessionManager()
    
    # Test creating sessions for configured SIP accounts
    test_accounts = [
        (0, "JEFF01"),
        (1, "JEFF0")
    ]
    
    print("📋 Creating Windows Audio Sessions...")
    print("💡 Open Windows Volume Mixer to see individual entries")
    print()
    
    created_sessions = []
    
    for account_id, username in test_accounts:
        print(f"🔄 Creating session for Account {account_id + 1}: {username}")
        
        if manager.create_audio_session(account_id, username):
            created_sessions.append((account_id, username))
            print(f"   ✅ Success: Check Volume Mixer for 'SIP Account {account_id + 1} ({username})'")
        else:
            print(f"   ❌ Failed to create session for {username}")
        
        time.sleep(1)
    
    if created_sessions:
        print()
        print("🎯 WINDOWS VOLUME MIXER CHECK:")
        print("   📍 Right-click volume icon → Open Volume Mixer")
        print("   📍 You should see these individual entries:")
        
        for account_id, username in created_sessions:
            print(f"      • SIP Account {account_id + 1} ({username})")
        
        print()
        print("🎛️ VOLUME MIXER FEATURES:")
        print("   • Individual volume sliders for each SIP account")
        print("   • Separate mute buttons per account")
        print("   • Real-time audio activity indicators")
        print("   • Independent audio level control")
        
        # Show active sessions
        sessions = manager.get_active_sessions()
        print(f"\n📊 Active Windows Audio Sessions:")
        for account_id, info in sessions.items():
            print(f"   Account {account_id + 1}: {info['display_name']} - Active: {info['active']}")
        
        print(f"\n⏱️ Keeping sessions active for demonstration...")
        print(f"   💡 Try adjusting volume for individual accounts in Volume Mixer")
        print(f"   💡 Each account can be controlled independently")
        
        # Keep sessions active for 30 seconds
        for i in range(30, 0, -5):
            print(f"   ⏰ {i} seconds remaining...")
            time.sleep(5)
    
    print("\n🧹 Cleaning up sessions...")
    manager.cleanup_all_sessions()
    print("✅ Test completed!")

if __name__ == "__main__":
    try:
        test_windows_audio_sessions()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
