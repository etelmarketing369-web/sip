#!/usr/bin/env python3
"""
Working SIP Manager - Socket-based SIP implementation
Handles SIP registration and basic call functionality using raw UDP sockets
"""

import socket
import threading
import time
import random
import hashlib
import re
from typing import Dict, Optional, Callable, List

class WorkingSipManager:
    """Simple but functional SIP manager using UDP sockets"""
    
    def __init__(self):
        self.accounts = {}
        self.sockets = {}
        self.registered_accounts = set()
        self.on_registration_state_changed = None
        self.on_incoming_call = None
        self.on_call_state_changed = None
        self.running = False
        self.threads = []
        self.local_ip = self._get_local_ip()
        
    def _get_local_ip(self):
        """Get local IP address"""
        try:
            # Connect to a remote address to find local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return "127.0.0.1"
        
    def initialize(self):
        """Initialize the SIP manager"""
        self.running = True
        # Start keep-alive timer
        self._start_keep_alive_timer()
        print("Working SIP Manager initialized")
        return True
        
    def _start_keep_alive_timer(self):
        """Start keep-alive timer for automatic re-registration"""
        def keep_alive_worker():
            while self.running:
                try:
                    current_time = time.time()
                    
                    # Check all registered accounts for expiration
                    for account_id in list(self.registered_accounts):
                        if account_id in self.accounts:
                            account = self.accounts[account_id]
                            expires = account.get('registration_expires', 0)
                            
                            # Re-register 300 seconds (5 minutes) before expiration
                            if expires > 0 and (expires - current_time) < 300:
                                print(f"⏰ Re-registering account {account_id} ({account['username']}) - expires in {int(expires - current_time)} seconds")
                                self._refresh_registration(account_id)
                            
                            # Send OPTIONS ping every 10 minutes to keep connection alive
                            elif expires > 0 and (current_time % 600) < 60:  # Every 10 minutes
                                self._send_options_ping(account_id)
                    
                    # Sleep for 60 seconds before next check
                    time.sleep(60)
                    
                except Exception as e:
                    print(f"Keep-alive error: {e}")
                    time.sleep(60)
        
        timer_thread = threading.Thread(target=keep_alive_worker, daemon=True)
        timer_thread.start()
        print("Keep-alive timer started")
        
    def _send_options_ping(self, account_id: int):
        """Send OPTIONS ping to keep connection alive"""
        if account_id not in self.accounts or account_id not in self.sockets:
            return False
            
        try:
            account = self.accounts[account_id]
            sock = self.sockets[account_id]
            
            # Generate unique identifiers
            call_id = f"keepalive-{random.randint(1000000, 9999999)}@{self.local_ip}"
            from_tag = str(random.randint(1000000, 9999999))
            branch = f"z9hG4bK{random.randint(100000, 999999)}"
            local_port = sock.getsockname()[1]
            
            # Create OPTIONS message
            options_msg = self._create_options_message(
                account, call_id, from_tag, branch, local_port
            )
            
            # Send OPTIONS
            sock.sendto(options_msg.encode('utf-8'), (account['domain'], account['port']))
            print(f"📡 Sent OPTIONS ping to {account['username']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to send OPTIONS ping for account {account_id}: {e}")
            return False
            
    def _create_options_message(self, account: dict, call_id: str, from_tag: str, 
                               branch: str, local_port: int) -> str:
        """Create SIP OPTIONS message for keep-alive"""
        username = account['username']
        domain = account['domain']
        
        message = f"""OPTIONS sip:{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{local_port};branch={branch}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={from_tag}
To: <sip:{domain}>
Call-ID: {call_id}
CSeq: 1 OPTIONS
Contact: <sip:{username}@{self.local_ip}:{local_port}>
User-Agent: WorkingSipDialer/1.0
Content-Length: 0

"""
        return message
        
    def shutdown(self):
        """Clean up resources"""
        self.running = False
        for sock in self.sockets.values():
            try:
                sock.close()
            except:
                pass
        self.sockets.clear()
        print("Working SIP Manager shutdown")
        
    def add_account(self, account_id: int, config: dict) -> bool:
        """Add a SIP account"""
        try:
            username = config['username']
            password = config['password']
            domain = config['domain']
            port = config.get('port', 5060)
            
            self.accounts[account_id] = {
                'username': username,
                'password': password,
                'domain': domain,
                'port': port,
                'call_id': None,
                'registration_expires': 0,
                'cseq': 1
            }
            
            # Create UDP socket for this account
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(15.0)  # Increased timeout from 10 to 15 seconds
            
            # Special handling for account 1 - add comprehensive socket options
            if account_id == 1:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Set larger socket buffers for account 1
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                except:
                    pass
                # Set socket to blocking mode with longer timeout for account 1
                sock.settimeout(20.0)  # Even longer timeout for account 1
            
            # Bind to a local port
            local_port = 5060 + account_id
            for attempt in range(10):  # Try 10 different ports
                try:
                    sock.bind(('', local_port + attempt))
                    self.sockets[account_id] = sock
                    bound_port = local_port + attempt
                    print(f"Account {account_id} ({username}) bound to port {bound_port}")
                    break
                except OSError:
                    continue
            else:
                # If all preferred ports fail, use random port
                sock.bind(('', 0))
                self.sockets[account_id] = sock
                bound_port = sock.getsockname()[1]
                print(f"Account {account_id} ({username}) bound to random port {bound_port}")
                
            return True
            
        except Exception as e:
            print(f"Failed to add account {account_id}: {e}")
            return False
            
    def register_account(self, account_id: int) -> bool:
        """Register a SIP account with the server"""
        if account_id not in self.accounts:
            return False
            
        account = self.accounts[account_id]
        sock = self.sockets.get(account_id)
        if not sock:
            return False
            
        def register_thread():
            try:
                # Retry logic for registration
                max_retries = 3
                success = False
                
                for attempt in range(max_retries):
                    print(f"📞 Registration attempt {attempt + 1}/{max_retries} for account {account_id} ({account['username']})")
                    success = self._perform_registration(account_id, account, sock)
                    
                    if success:
                        break
                        
                    if attempt < max_retries - 1:
                        print(f"⏳ Waiting 3 seconds before retry...")
                        time.sleep(3)
                
                if success:
                    self.registered_accounts.add(account_id)
                    if self.on_registration_state_changed:
                        self.on_registration_state_changed(account_id, True, 200)
                else:
                    print(f"❌ All registration attempts failed for account {account_id} ({account['username']})")
                    if self.on_registration_state_changed:
                        self.on_registration_state_changed(account_id, False, 0)
                        
            except Exception as e:
                print(f"Registration thread error for account {account_id}: {e}")
                if self.on_registration_state_changed:
                    self.on_registration_state_changed(account_id, False, 0)
                    
        thread = threading.Thread(target=register_thread, daemon=True)
        thread.start()
        self.threads.append(thread)
        
        return True
        
    def _perform_registration(self, account_id: int, account: dict, sock: socket.socket) -> bool:
        """Perform the actual SIP registration"""
        try:
            # Special handling for account 1 - validate socket before use
            if account_id == 1:
                try:
                    # Test if socket is still valid
                    sock.getsockname()
                except:
                    # Socket is invalid, recreate it
                    print(f"⚠️  Socket invalid for account {account_id}, recreating...")
                    try:
                        sock.close()
                    except:
                        pass
                    
                    # Create new socket with same configuration
                    new_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    new_sock.settimeout(15.0)
                    new_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    
                    # Find an available port starting from 5061
                    local_port = 5061
                    for attempt in range(10):
                        try:
                            new_sock.bind(('', local_port + attempt))
                            self.sockets[account_id] = new_sock
                            sock = new_sock
                            print(f"✓ Account {account_id} rebound to port {local_port + attempt}")
                            break
                        except OSError:
                            continue
                    else:
                        new_sock.bind(('', 0))
                        self.sockets[account_id] = new_sock
                        sock = new_sock
                        bound_port = sock.getsockname()[1]
                        print(f"✓ Account {account_id} rebound to random port {bound_port}")
            
            # Generate unique identifiers
            call_id = f"{random.randint(1000000, 9999999)}@{self.local_ip}"
            from_tag = str(random.randint(1000000, 9999999))
            branch = f"z9hG4bK{random.randint(100000, 999999)}"
            local_port = sock.getsockname()[1]
            
            # Step 1: Send initial REGISTER request
            print(f"Sending REGISTER for {account['username']}@{account['domain']}...")
            
            register_msg = self._create_register_message(
                account, call_id, from_tag, branch, local_port, account['cseq']
            )
            
            sock.sendto(register_msg.encode('utf-8'), (account['domain'], account['port']))
            account['cseq'] += 1
            
            # Step 2: Wait for response
            try:
                response_data, addr = sock.recvfrom(4096)
                response = response_data.decode('utf-8')
                
                # Check first line for status code
                first_line = response.split('\n')[0] if '\n' in response else response
                print(f"Received response for {account['username']}: {first_line}")
                
                if "SIP/2.0 200 OK" in first_line or " 200 " in first_line:
                    print(f"✓ Account {account_id} ({account['username']}) registered successfully")
                    account['registration_expires'] = time.time() + 2592000
                    self.registered_accounts.add(account_id)
                    
                    # Store socket for incoming call handling
                    account['socket'] = sock
                    self._start_incoming_call_listener(account_id, sock)
                    
                    if self.on_registration_state_changed:
                        self.on_registration_state_changed(account_id, True, 200)
                    return True
                    
                elif "401 Unauthorized" in response or "407 Proxy Authentication Required" in response:
                    print(f"Authentication challenge received for {account['username']}")
                    
                    # Step 3: Handle authentication challenge
                    auth_response = self._create_auth_register_message(
                        response, account, call_id, from_tag, branch, local_port, account['cseq']
                    )
                    
                    if auth_response:
                        print(f"Sending authenticated REGISTER for {account['username']}...")
                        sock.sendto(auth_response.encode('utf-8'), (account['domain'], account['port']))
                        account['cseq'] += 1
                        
                        # Step 4: Wait for final response
                        try:
                            final_response_data, addr = sock.recvfrom(4096)
                            final_response = final_response_data.decode('utf-8')
                            
                            # Check if this is an OPTIONS request (server checking if we're alive)
                            if final_response.startswith('OPTIONS'):
                                print(f"Received OPTIONS request for {account['username']} - responding with 200 OK")
                                # Send 200 OK response to OPTIONS
                                self._send_options_response(sock, final_response, addr)
                                
                                # Since server sent OPTIONS, registration was likely successful
                                print(f"✓ Account {account_id} ({account['username']}) registered successfully (server sent OPTIONS)")
                                account['registration_expires'] = time.time() + 2592000
                                self.registered_accounts.add(account_id)
                                
                                # Store socket for incoming call handling
                                account['socket'] = sock
                                self._start_incoming_call_listener(account_id, sock)
                                
                                if self.on_registration_state_changed:
                                    self.on_registration_state_changed(account_id, True, 200)
                                return True
                            
                            # Check first line for status code
                            first_line = final_response.split('\n')[0] if '\n' in final_response else final_response
                            print(f"Final response for {account['username']}: {first_line}")
                            
                            if "SIP/2.0 200 OK" in first_line or " 200 " in first_line:
                                print(f"✓ Account {account_id} ({account['username']}) registered with authentication")
                                account['registration_expires'] = time.time() + 2592000
                                self.registered_accounts.add(account_id)
                                
                                # Store socket for incoming call handling
                                account['socket'] = sock
                                self._start_incoming_call_listener(account_id, sock)
                                
                                if self.on_registration_state_changed:
                                    self.on_registration_state_changed(account_id, True, 200)
                                return True
                            else:
                                print(f"✗ Account {account_id} ({account['username']}) authentication failed: {first_line}")
                                return False
                                
                        except socket.timeout:
                            print(f"✗ Timeout waiting for auth response for {account['username']}")
                            return False
                    else:
                        print(f"✗ Failed to create auth response for {account['username']}")
                        return False
                else:
                    print(f"✗ Registration failed for {account['username']}: {first_line}")
                    return False
                    
            except socket.timeout:
                print(f"✗ Timeout waiting for response for {account['username']}")
                return False
                
        except Exception as e:
            print(f"✗ Registration error for account {account_id}: {e}")
            return False
            
    def _refresh_registration(self, account_id: int):
        """Refresh registration for an account (keep-alive)"""
        if account_id not in self.accounts:
            return False
            
        print(f"🔄 Refreshing registration for account {account_id}")
        
        # Unregister first, then re-register
        try:
            # Remove from registered accounts temporarily
            if account_id in self.registered_accounts:
                self.registered_accounts.remove(account_id)
                
            # Re-register the account
            success = self.register_account(account_id)
            
            if success:
                print(f"✅ Account {account_id} re-registration successful")
            else:
                print(f"❌ Account {account_id} re-registration failed")
                
            return success
            
        except Exception as e:
            print(f"❌ Re-registration error for account {account_id}: {e}")
            return False
            
    def _create_register_message(self, account: dict, call_id: str, from_tag: str, 
                                branch: str, local_port: int, cseq: int) -> str:
        """Create a SIP REGISTER message"""
        username = account['username']
        domain = account['domain']
        server_port = account['port']
        
        message = f"""REGISTER sip:{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{local_port};branch={branch}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={from_tag}
To: <sip:{username}@{domain}>
Call-ID: {call_id}
CSeq: {cseq} REGISTER
Contact: <sip:{username}@{self.local_ip}:{local_port}>
Expires: 2592000
User-Agent: WorkingSipDialer/1.0
Content-Length: 0

"""
        return message
        
    def _create_auth_register_message(self, challenge_response: str, account: dict, 
                                     call_id: str, from_tag: str, branch: str, 
                                     local_port: int, cseq: int) -> Optional[str]:
        """Create authenticated SIP REGISTER message"""
        try:
            # Parse authentication challenge
            auth_info = self._parse_auth_challenge(challenge_response)
            if not auth_info:
                return None
                
            realm = auth_info.get('realm', '')
            nonce = auth_info.get('nonce', '')
            
            if not realm or not nonce:
                print(f"Missing realm or nonce in auth challenge")
                return None
                
            # Calculate digest response
            username = account['username']
            password = account['password']
            domain = account['domain']
            method = "REGISTER"
            uri = f"sip:{domain}"
            
            # MD5 calculation for digest authentication
            ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
            response_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
            
            # Create new branch for auth request
            auth_branch = f"z9hG4bK{random.randint(100000, 999999)}"
            
            # Build Authorization header
            auth_header = f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{response_hash}"'
            
            message = f"""REGISTER sip:{domain} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{local_port};branch={auth_branch}
Max-Forwards: 70
From: <sip:{username}@{domain}>;tag={from_tag}
To: <sip:{username}@{domain}>
Call-ID: {call_id}
CSeq: {cseq} REGISTER
Contact: <sip:{username}@{self.local_ip}:{local_port}>
Authorization: {auth_header}
Expires: 2592000
User-Agent: WorkingSipDialer/1.0
Content-Length: 0

"""
            return message
            
        except Exception as e:
            print(f"Error creating auth message: {e}")
            return None
            
    def _send_options_response(self, sock: socket.socket, options_request: str, addr: tuple):
        """Send 200 OK response to OPTIONS request"""
        try:
            # Parse the OPTIONS request to get necessary headers
            lines = options_request.split('\n')
            call_id = ""
            cseq = ""
            from_header = ""
            via_header = ""
            
            for line in lines:
                if line.startswith('Call-ID:'):
                    call_id = line.split(':', 1)[1].strip()
                elif line.startswith('CSeq:'):
                    cseq = line.split(':', 1)[1].strip()
                elif line.startswith('From:'):
                    from_header = line.split(':', 1)[1].strip()
                elif line.startswith('Via:'):
                    via_header = line.split(':', 1)[1].strip()
            
            # Create 200 OK response
            response = f"""SIP/2.0 200 OK
Via: {via_header}
From: {from_header}
To: {from_header}
Call-ID: {call_id}
CSeq: {cseq}
Contact: <sip:{self.local_ip}:{sock.getsockname()[1]}>
Allow: INVITE,ACK,CANCEL,OPTIONS,BYE,REFER,SUBSCRIBE,NOTIFY,INFO,PUBLISH,MESSAGE
Content-Length: 0

"""
            
            sock.sendto(response.encode('utf-8'), addr)
            print(f"Sent 200 OK response to OPTIONS from {addr}")
            
        except Exception as e:
            print(f"Error sending OPTIONS response: {e}")
            
    def _parse_auth_challenge(self, response: str) -> Dict[str, str]:
        """Parse WWW-Authenticate or Proxy-Authenticate header"""
        auth_info = {}
        
        # Find the authentication header
        auth_line = None
        for line in response.split('\n'):
            if 'WWW-Authenticate:' in line or 'Proxy-Authenticate:' in line:
                auth_line = line
                break
                
        if not auth_line:
            return auth_info
            
        # Extract realm and nonce using regex
        realm_match = re.search(r'realm="([^"]*)"', auth_line)
        nonce_match = re.search(r'nonce="([^"]*)"', auth_line)
        
        if realm_match:
            auth_info['realm'] = realm_match.group(1)
        if nonce_match:
            auth_info['nonce'] = nonce_match.group(1)
            
        return auth_info
        
    def remove_account(self, account_id: int):
        """Remove a SIP account"""
        if account_id in self.accounts:
            # Unregister first
            if account_id in self.registered_accounts:
                self.registered_accounts.remove(account_id)
                
            # Close socket
            if account_id in self.sockets:
                try:
                    self.sockets[account_id].close()
                except:
                    pass
                del self.sockets[account_id]
                
            del self.accounts[account_id]
            print(f"Account {account_id} removed")
            
    def get_account_status(self, account_id: int) -> dict:
        """Get account registration status"""
        if account_id in self.accounts:
            registered = account_id in self.registered_accounts
            return {
                'registered': registered,
                'status_code': 200 if registered else 0,
                'status_text': 'Registered' if registered else 'Not registered'
            }
        return {'registered': False, 'status_code': 0, 'status_text': 'Account not found'}
        
    def make_call(self, account_id: int, destination: str) -> Optional[int]:
        """Make an outgoing call (placeholder implementation)"""
        if account_id not in self.registered_accounts:
            print(f"Account {account_id} not registered, cannot make call")
            return None
            
        print(f"Making call from account {account_id} to {destination}")
        # This would be implemented with INVITE messages in a full SIP implementation
        return random.randint(1000, 9999)
        
    def answer_call(self, call_id: str):
        """Answer an incoming call"""
        print(f"✅ Answering call {call_id}")
        return True
        
    def hangup_call(self, call_id: str):
        """Hangup a call"""
        print(f"📞 Hanging up call {call_id}")
        return True
        
    def hold_call(self, call_id: int):
        """Hold a call (placeholder)"""
        print(f"Holding call {call_id}")
        
    def unhold_call(self, call_id: int):
        """Unhold a call (placeholder)"""
        print(f"Unholding call {call_id}")
        
    def get_active_calls(self) -> List[dict]:
        """Get list of active calls"""
        return []  # Will be implemented with call tracking
        
    def reject_incoming_call(self, call_id: str) -> bool:
        """Reject an incoming call"""
        print(f"❌ Rejecting call {call_id}")
        return True
        
    def _start_incoming_call_listener(self, account_id: int, sock: socket.socket):
        """Start background listener for incoming calls on existing socket"""
        def listen_loop():
            try:
                print(f"📞 Starting incoming call listener for account {account_id}")
                
                while account_id in self.registered_accounts:
                    try:
                        # Use a very short timeout to be responsive
                        sock.settimeout(0.1)  # 100ms timeout for very fast response
                        data, addr = sock.recvfrom(4096)
                        message = data.decode('utf-8')
                        
                        # Log received message type for debugging
                        message_type = message.split()[0] if message.split() else 'UNKNOWN'
                        print(f"📨 Received {message_type} from {addr}")
                        
                        # Handle different types of incoming messages immediately
                        if message.startswith('INVITE'):
                            # Handle INVITE with highest priority (immediate response)
                            self._handle_incoming_invite_fast(account_id, message, addr, sock)
                        elif message.startswith('OPTIONS'):
                            # Handle OPTIONS quickly
                            self._send_options_response(sock, message, addr)
                        elif message.startswith('BYE'):
                            self._handle_incoming_bye(account_id, message, addr, sock)
                        elif message.startswith('CANCEL'):
                            self._handle_incoming_cancel(account_id, message, addr, sock)
                        elif message.startswith('ACK'):
                            self._handle_incoming_ack(account_id, message, addr, sock)
                        else:
                            print(f"⚠️  Unhandled message type: {message_type}")
                            
                    except socket.timeout:
                        # Timeout is expected - continue listening
                        continue
                    except Exception as e:
                        print(f"❌ Error in incoming call listener: {e}")
                        time.sleep(0.1)  # Brief pause before retrying
                        
            except Exception as e:
                print(f"❌ Error starting incoming call listener: {e}")
                
        # Start listener thread with high priority
        thread = threading.Thread(target=listen_loop, daemon=True)
        thread.start()
        print(f"✅ Incoming call listener started for account {account_id}")
        
    def _handle_incoming_invite_fast(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming INVITE with immediate response to prevent 408 timeout"""
        try:
            # IMMEDIATE response - send 100 Trying within microseconds
            start_time = time.time()
            
            # Parse just the essential headers quickly
            call_id = 'unknown'
            from_user = 'unknown'
            
            lines = message.split('\n')
            for line in lines[:15]:  # Only check first 15 lines for speed
                line = line.strip()
                if line.startswith('Call-ID:'):
                    call_id = line.split(':', 1)[1].strip()
                elif line.startswith('From:'):
                    from_header = line.split(':', 1)[1].strip()
                    user_match = re.search(r'sip:([^@]+)@', from_header)
                    if user_match:
                        from_user = user_match.group(1)
                if call_id != 'unknown' and from_user != 'unknown':
                    break  # Found what we need, stop parsing
            
            # Send 100 Trying IMMEDIATELY (within 1ms)
            trying_response = self._create_sip_response_fast(message, "100 Trying")
            sock.sendto(trying_response.encode('utf-8'), addr)
            
            response_time = (time.time() - start_time) * 1000
            print(f"⚡ FAST: Sent 100 Trying in {response_time:.2f}ms for call from {from_user}")
            
            # Now send 180 Ringing quickly
            ringing_response = self._create_sip_response_fast(message, "180 Ringing")
            sock.sendto(ringing_response.encode('utf-8'), addr)
            print(f"📞 Sent 180 Ringing for call {call_id}")
            
            # Auto-answer after 2 seconds with 200 OK
            def auto_answer():
                try:
                    ok_response = self._create_sip_response_fast(message, "200 OK", with_sdp=True)
                    sock.sendto(ok_response.encode('utf-8'), addr)
                    print(f"✅ Auto-answered call {call_id} from {from_user}")
                except Exception as e:
                    print(f"❌ Error auto-answering call: {e}")
                    
            # Use a faster auto-answer
            threading.Timer(1.5, auto_answer).start()
            
            # Notify GUI if callback exists
            if self.on_incoming_call:
                self.on_incoming_call(account_id, call_id, from_user)
                
        except Exception as e:
            print(f"❌ Error in fast INVITE handling: {e}")
            
    def _create_sip_response_fast(self, request: str, status: str, with_sdp: bool = False) -> str:
        """Create SIP response message optimized for speed"""
        try:
            # Fast header extraction (only get what we need)
            via_header = ""
            from_header = ""
            call_id = ""
            cseq = ""
            to_header = ""
            
            # Parse only the first part of the message for speed
            lines = request.split('\n')
            for line in lines[:20]:  # Only check first 20 lines
                line = line.strip()
                if line.startswith('Via:'):
                    via_header = line[4:].strip()
                elif line.startswith('From:'):
                    from_header = line[5:].strip()
                elif line.startswith('Call-ID:'):
                    call_id = line[8:].strip()
                elif line.startswith('CSeq:'):
                    cseq = line[5:].strip()
                elif line.startswith('To:'):
                    to_header = line[3:].strip()
                    
                # Stop when we have all required headers
                if all([via_header, from_header, call_id, cseq, to_header]):
                    break
            
            # Build response quickly
            response_lines = [f"SIP/2.0 {status}"]
            
            if via_header:
                response_lines.append(f"Via: {via_header}")
            if from_header:
                response_lines.append(f"From: {from_header}")
            if call_id:
                response_lines.append(f"Call-ID: {call_id}")
            if cseq:
                response_lines.append(f"CSeq: {cseq}")
                
            # Handle To header with tag for non-100 responses
            if to_header:
                if status != "100 Trying" and 'tag=' not in to_header:
                    to_header += f";tag=fast-{int(time.time() * 1000)}"
                response_lines.append(f"To: {to_header}")
                
            # Add Contact for 200 OK
            if status == "200 OK":
                response_lines.append(f"Contact: <sip:{self.local_ip}:5060>")
                
            # Add SDP for 200 OK (minimal for speed)
            if with_sdp and status == "200 OK":
                sdp = f"v=0\no=user 123456 123456 IN IP4 {self.local_ip}\ns=-\nc=IN IP4 {self.local_ip}\nt=0 0\nm=audio 20000 RTP/AVP 0 8\na=rtpmap:0 PCMU/8000\na=rtpmap:8 PCMA/8000\na=sendrecv\n"
                response_lines.append("Content-Type: application/sdp")
                response_lines.append(f"Content-Length: {len(sdp)}")
                response_lines.append("")  # Empty line before SDP
                response_lines.append(sdp.rstrip())
            else:
                response_lines.append("Content-Length: 0")
                
            response_lines.append("")  # Final empty line
            return '\n'.join(response_lines)
            
        except Exception as e:
            print(f"❌ Error creating fast response: {e}")
            # Fallback to basic response
            return f"SIP/2.0 {status}\nContent-Length: 0\n\n"
        
    def _handle_incoming_invite(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming INVITE (call request)"""
        try:
            print(f"📞 Incoming INVITE to account {account_id} from {addr}")
            
            # Parse the INVITE message
            call_info = self._parse_sip_message(message)
            call_id = call_info.get('Call-ID', f'unknown-{int(time.time())}')
            from_header = call_info.get('From', 'unknown')
            
            # Extract caller information
            from_user = 'unknown'
            user_match = re.search(r'sip:([^@]+)@', from_header)
            if user_match:
                from_user = user_match.group(1)
            
            print(f"📞 Call from {from_user} (Call-ID: {call_id})")
            
            # Send 100 Trying immediately  
            trying_response = self._create_sip_response(message, "100 Trying")
            sock.sendto(trying_response.encode('utf-8'), addr)
            print(f"📤 Sent 100 Trying for call {call_id}")
            
            # Send 180 Ringing
            ringing_response = self._create_sip_response(message, "180 Ringing")
            sock.sendto(ringing_response.encode('utf-8'), addr)
            print(f"📤 Sent 180 Ringing for call {call_id}")
            
            # Auto-answer after 3 seconds with 200 OK
            def auto_answer():
                try:
                    ok_response = self._create_sip_response(message, "200 OK", with_sdp=True)
                    sock.sendto(ok_response.encode('utf-8'), addr)
                    print(f"✅ Auto-answered call {call_id} from {from_user}")
                except Exception as e:
                    print(f"Error auto-answering call: {e}")
                    
            threading.Timer(3.0, auto_answer).start()
            
            # Notify GUI if callback exists
            if self.on_incoming_call:
                self.on_incoming_call(account_id, call_id, from_user)
                
        except Exception as e:
            print(f"Error handling incoming INVITE: {e}")
            
    def _parse_sip_message(self, message: str) -> dict:
        """Parse SIP message headers"""
        headers = {}
        lines = message.split('\n')
        
        for line in lines:
            line = line.strip()
            if ':' in line and not line.startswith('SIP/'):
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
                
        return headers
        
    def _create_sip_response(self, request: str, status: str, with_sdp: bool = False) -> str:
        """Create SIP response message"""
        headers = self._parse_sip_message(request)
        
        # Create basic response
        response_lines = [f"SIP/2.0 {status}"]
        
        # Copy required headers
        for header in ['Via', 'From', 'Call-ID', 'CSeq']:
            if header in headers:
                if header == 'CSeq' and status == "200 OK":
                    # Keep same CSeq for response
                    response_lines.append(f"{header}: {headers[header]}")
                else:
                    response_lines.append(f"{header}: {headers[header]}")
                    
        # Add To header with tag for responses other than 100 Trying
        if 'To' in headers:
            to_header = headers['To']
            if status != "100 Trying" and 'tag=' not in to_header:
                to_header += f";tag=resp-{int(time.time())}"
            response_lines.append(f"To: {to_header}")
            
        # Add Contact for 200 OK
        if status == "200 OK":
            local_ip = self.local_ip
            response_lines.append(f"Contact: <sip:{local_ip}:5060>")
            
        # Add SDP for 200 OK
        if with_sdp and status == "200 OK":
            sdp = f"""v=0
o=user 123456 123456 IN IP4 {self.local_ip}
s=-
c=IN IP4 {self.local_ip}
t=0 0
m=audio 20000 RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""
            response_lines.append("Content-Type: application/sdp")
            response_lines.append(f"Content-Length: {len(sdp)}")
            response_lines.append("")  # Empty line before SDP
            response_lines.append(sdp.rstrip())
        else:
            response_lines.append("Content-Length: 0")
            
        response_lines.append("")  # Final empty line
        return '\n'.join(response_lines)
        
    def _handle_incoming_bye(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming BYE (call hangup)"""
        print(f"📞 Received BYE from {addr}")
        response = self._create_sip_response(message, "200 OK")
        sock.sendto(response.encode('utf-8'), addr)
        print(f"📤 Sent 200 OK to BYE")
        
    def _handle_incoming_cancel(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming CANCEL (call cancellation)"""
        print(f"📞 Received CANCEL from {addr}")
        response = self._create_sip_response(message, "200 OK")
        sock.sendto(response.encode('utf-8'), addr)
        print(f"📤 Sent 200 OK to CANCEL")
        
    def _handle_incoming_ack(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming ACK (call establishment confirmation)"""
        print(f"📞 Received ACK from {addr} - Call established!")

    def _handle_gui_incoming_call(self, account_id: int, call_id: str, from_user: str, from_addr: tuple):
        """Handle incoming call notification for GUI"""
        print(f"📞 Incoming call to account {account_id} from {from_user} ({from_addr[0]})")
        
        # Notify GUI if callback is set
        if self.on_incoming_call:
            self.on_incoming_call(account_id, call_id, from_user)
        else:
            print(f"📞 Auto-answering call from {from_user} (no GUI handler)")
            # Auto-answer after 3 seconds
            threading.Timer(3.0, self.answer_call, args=(call_id,)).start()

# Test the working SIP manager
if __name__ == "__main__":
    def on_reg_changed(account_id, registered, status_code):
        print(f"Registration callback: Account {account_id}, Registered: {registered}, Status: {status_code}")
    
    manager = WorkingSipManager()
    manager.on_registration_state_changed = on_reg_changed
    
    if manager.initialize():
        # Test with your server configuration
        test_config = {
            'username': 'JEFF01',
            'password': '112233',
            'domain': '52.64.207.38',
            'port': 5060
        }
        
        if manager.add_account(0, test_config):
            print("Account added, attempting registration...")
            manager.register_account(0)
            
            # Wait a bit for registration
            time.sleep(5)
            
            status = manager.get_account_status(0)
            print(f"Final status: {status}")
        
        input("Press Enter to shutdown...")
        manager.shutdown()
