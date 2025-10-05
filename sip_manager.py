#!/usr/bin/env python3
"""
SIP Manager Module
Handles all SIP functionality using PJSIP library
"""

import pjsua2 as pj
import threading
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable

class SipAccount(pj.Account):
    """Custom SIP Account class"""
    
    def __init__(self, manager, account_id: int):
        super().__init__()
        self.manager = manager
        self.account_id = account_id
        self.is_registered = False
        
    def onRegState(self, prm):
        """Called when registration state changes"""
        info = self.getInfo()
        if info.regStatus == 200:
            self.is_registered = True
            print(f"Account {self.account_id} registered successfully")
        else:
            self.is_registered = False
            print(f"Account {self.account_id} registration failed: {info.regStatus}")
        
        # Notify the manager about registration state change
        if self.manager.on_registration_state_changed:
            self.manager.on_registration_state_changed(self.account_id, self.is_registered, info.regStatus)
    
    def onIncomingCall(self, prm):
        """Called when there's an incoming call"""
        call = SipCall(self.manager, account=self)
        call_info = prm.callId
        
        # Store the call
        self.manager.active_calls[call_info] = call
        
        # Answer the call automatically or notify GUI
        if self.manager.on_incoming_call:
            self.manager.on_incoming_call(self.account_id, call_info, prm.rdata.info)

class SipCall(pj.Call):
    """Custom SIP Call class"""
    
    def __init__(self, manager, account=None):
        super().__init__(account)
        self.manager = manager
        
    def onCallState(self, prm):
        """Called when call state changes"""
        info = self.getInfo()
        call_id = info.id
        
        print(f"Call {call_id} state: {info.stateText}")
        
        # Notify the manager about call state change
        if self.manager.on_call_state_changed:
            self.manager.on_call_state_changed(call_id, info.state, info.stateText)
    
    def onCallMediaState(self, prm):
        """Called when call media state changes"""
        info = self.getInfo()
        
        # Check if media is active
        for mi in info.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                # Connect call media to sound device
                call_media = self.getMedia(mi.index)
                if call_media:
                    aud_media = pj.AudioMedia.typecastFromMedia(call_media)
                    # Connect to speaker and microphone
                    aud_media.startTransmit(self.manager.endpoint.audDevManager().getPlaybackDevMedia())
                    self.manager.endpoint.audDevManager().getCaptureDevMedia().startTransmit(aud_media)

class SipManager:
    """Main SIP Manager class"""
    
    def __init__(self):
        self.endpoint = None
        self.accounts: Dict[int, SipAccount] = {}
        self.active_calls: Dict[int, SipCall] = {}
        self.is_initialized = False
        
        # Callback functions
        self.on_registration_state_changed: Optional[Callable] = None
        self.on_incoming_call: Optional[Callable] = None
        self.on_call_state_changed: Optional[Callable] = None
        
        # Threading
        self.worker_thread = None
        self.should_stop = False
        
    def initialize(self):
        """Initialize PJSIP endpoint"""
        try:
            self.endpoint = pj.Endpoint()
            self.endpoint.libCreate()
            
            # Configure endpoint
            ep_cfg = pj.EpConfig()
            ep_cfg.logConfig.level = 3
            ep_cfg.logConfig.consoleLevel = 3
            
            # Media configuration
            ep_cfg.medConfig.hasIoqueue = True
            ep_cfg.medConfig.clockRate = 8000
            ep_cfg.medConfig.audioFramePtime = 20
            ep_cfg.medConfig.maxMediaPorts = 32
            
            self.endpoint.libInit(ep_cfg)
            
            # Configure transport
            self._configure_transport()
            
            # Start the endpoint
            self.endpoint.libStart()
            
            self.is_initialized = True
            print("PJSIP initialized successfully")
            
            # Start worker thread
            self._start_worker_thread()
            
            return True
            
        except Exception as e:
            print(f"Failed to initialize PJSIP: {e}")
            return False
    
    def _configure_transport(self):
        """Configure SIP transport"""
        try:
            # UDP transport
            udp_cfg = pj.TransportConfig()
            udp_cfg.port = 5060
            self.endpoint.transportCreate(pj.PJSIP_TRANSPORT_UDP, udp_cfg)
            
            # TCP transport
            tcp_cfg = pj.TransportConfig()
            tcp_cfg.port = 5060
            self.endpoint.transportCreate(pj.PJSIP_TRANSPORT_TCP, tcp_cfg)
            
        except Exception as e:
            print(f"Transport configuration error: {e}")
    
    def _start_worker_thread(self):
        """Start worker thread for handling PJSIP events"""
        self.worker_thread = threading.Thread(target=self._worker_thread_func, daemon=True)
        self.worker_thread.start()
    
    def _worker_thread_func(self):
        """Worker thread function"""
        while not self.should_stop:
            try:
                self.endpoint.libHandleEvents(10)
                time.sleep(0.01)
            except Exception as e:
                print(f"Worker thread error: {e}")
                break
    
    def add_account(self, account_id: int, config: dict) -> bool:
        """Add a SIP account"""
        try:
            if not self.is_initialized:
                print("SIP manager not initialized")
                return False
            
            # Remove existing account if present
            if account_id in self.accounts:
                self.remove_account(account_id)
            
            # Create account configuration
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{config['username']}@{config['domain']}"
            acc_cfg.regConfig.registrarUri = f"sip:{config['domain']}"
            
            # Authentication
            cred = pj.AuthCredInfo()
            cred.scheme = "digest"
            cred.realm = "*"
            cred.username = config['username']
            cred.data = config['password']
            cred.dataType = pj.PJSIP_CRED_DATA_PLAIN_PASSWD
            acc_cfg.sipConfig.authCreds.append(cred)
            
            # Proxy settings
            if 'proxy' in config and config['proxy']:
                acc_cfg.sipConfig.proxies.append(config['proxy'])
            
            # Create and add account
            account = SipAccount(self, account_id)
            account.create(acc_cfg)
            
            self.accounts[account_id] = account
            print(f"Account {account_id} added successfully")
            return True
            
        except Exception as e:
            print(f"Failed to add account {account_id}: {e}")
            return False
    
    def remove_account(self, account_id: int):
        """Remove a SIP account"""
        if account_id in self.accounts:
            try:
                self.accounts[account_id].delete()
                del self.accounts[account_id]
                print(f"Account {account_id} removed")
            except Exception as e:
                print(f"Error removing account {account_id}: {e}")
    
    def make_call(self, account_id: int, destination: str) -> Optional[int]:
        """Make an outgoing call"""
        try:
            if account_id not in self.accounts:
                print(f"Account {account_id} not found")
                return None
            
            account = self.accounts[account_id]
            if not account.is_registered:
                print(f"Account {account_id} not registered")
                return None
            
            # Create call
            call = SipCall(self, account)
            
            # Make the call
            call_prm = pj.CallOpParam()
            call_prm.opt.audioCount = 1
            call_prm.opt.videoCount = 0
            
            call.makeCall(f"sip:{destination}", call_prm)
            call_info = call.getInfo()
            
            # Store the call
            self.active_calls[call_info.id] = call
            
            print(f"Making call to {destination} from account {account_id}")
            return call_info.id
            
        except Exception as e:
            print(f"Failed to make call: {e}")
            return None
    
    def answer_call(self, call_id: int):
        """Answer an incoming call"""
        try:
            if call_id in self.active_calls:
                call = self.active_calls[call_id]
                call_prm = pj.CallOpParam()
                call_prm.statusCode = 200
                call.answer(call_prm)
                print(f"Answered call {call_id}")
            else:
                print(f"Call {call_id} not found")
        except Exception as e:
            print(f"Failed to answer call {call_id}: {e}")
    
    def hangup_call(self, call_id: int):
        """Hangup a call"""
        try:
            if call_id in self.active_calls:
                call = self.active_calls[call_id]
                call_prm = pj.CallOpParam()
                call_prm.statusCode = 603
                call.hangup(call_prm)
                del self.active_calls[call_id]
                print(f"Hung up call {call_id}")
            else:
                print(f"Call {call_id} not found")
        except Exception as e:
            print(f"Failed to hangup call {call_id}: {e}")
    
    def hold_call(self, call_id: int):
        """Hold a call"""
        try:
            if call_id in self.active_calls:
                call = self.active_calls[call_id]
                call_prm = pj.CallOpParam()
                call.setHold(call_prm)
                print(f"Call {call_id} on hold")
        except Exception as e:
            print(f"Failed to hold call {call_id}: {e}")
    
    def unhold_call(self, call_id: int):
        """Unhold a call"""
        try:
            if call_id in self.active_calls:
                call = self.active_calls[call_id]
                call_prm = pj.CallOpParam()
                call.reinvite(call_prm)
                print(f"Call {call_id} unheld")
        except Exception as e:
            print(f"Failed to unhold call {call_id}: {e}")
    
    def get_account_status(self, account_id: int) -> dict:
        """Get account registration status"""
        if account_id in self.accounts:
            account = self.accounts[account_id]
            info = account.getInfo()
            return {
                'registered': account.is_registered,
                'status_code': info.regStatus,
                'status_text': info.regStatusText
            }
        return {'registered': False, 'status_code': 0, 'status_text': 'Account not found'}
    
    def get_active_calls(self) -> List[dict]:
        """Get list of active calls"""
        calls = []
        for call_id, call in self.active_calls.items():
            try:
                info = call.getInfo()
                calls.append({
                    'id': call_id,
                    'state': info.state,
                    'state_text': info.stateText,
                    'remote_uri': info.remoteUri,
                    'local_uri': info.localUri,
                    'duration': info.connectDuration.sec if info.connectDuration else 0
                })
            except:
                pass
        return calls
    
    def shutdown(self):
        """Shutdown the SIP manager"""
        try:
            self.should_stop = True
            
            # Hangup all active calls
            for call_id in list(self.active_calls.keys()):
                self.hangup_call(call_id)
            
            # Remove all accounts
            for account_id in list(self.accounts.keys()):
                self.remove_account(account_id)
            
            # Wait for worker thread
            if self.worker_thread and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=2)
            
            # Shutdown endpoint
            if self.endpoint:
                self.endpoint.libDestroy()
            
            print("SIP manager shutdown complete")
            
        except Exception as e:
            print(f"Error during shutdown: {e}")

# Example usage and testing
if __name__ == "__main__":
    manager = SipManager()
    
    # Test callbacks
    def on_reg_state_changed(account_id, registered, status_code):
        print(f"Account {account_id} registration: {registered} (status: {status_code})")
    
    def on_incoming_call(account_id, call_id, call_info):
        print(f"Incoming call on account {account_id}: {call_info}")
    
    def on_call_state_changed(call_id, state, state_text):
        print(f"Call {call_id} state changed: {state_text}")
    
    manager.on_registration_state_changed = on_reg_state_changed
    manager.on_incoming_call = on_incoming_call
    manager.on_call_state_changed = on_call_state_changed
    
    # Initialize
    if manager.initialize():
        print("SIP Manager initialized successfully")
        
        # Keep running for testing
        try:
            input("Press Enter to shutdown...")
        except KeyboardInterrupt:
            pass
        
        manager.shutdown()
    else:
        print("Failed to initialize SIP Manager")
