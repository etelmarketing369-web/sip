"""
Enhanced incoming call handler for SIP dialer
Handles incoming INVITE requests properly
"""

import socket
import threading
import time
import re
from typing import Dict, Optional, Callable

class IncomingCallHandler:
    def __init__(self, working_sip_manager):
        self.sip_manager = working_sip_manager
        self.listening_threads = {}
        self.active_calls = {}
        self.on_incoming_call = None  # Callback for GUI notification
        
    def start_listening(self, account_id: int):
        """Start listening for incoming calls on account's port"""
        if account_id not in self.sip_manager.accounts:
            return False
            
        account = self.sip_manager.accounts[account_id]
        port = account.get('local_port', 5060 + account_id)
        
        # Stop existing listener if any
        self.stop_listening(account_id)
        
        # Start new listener thread
        thread = threading.Thread(
            target=self._listen_for_incoming_calls,
            args=(account_id, port),
            daemon=True
        )
        thread.start()
        self.listening_threads[account_id] = thread
        
        print(f"📞 Started listening for incoming calls on account {account_id} (port {port})")
        return True
        
    def stop_listening(self, account_id: int):
        """Stop listening for incoming calls on account"""
        if account_id in self.listening_threads:
            # Thread will stop when account is removed or daemon thread ends
            del self.listening_threads[account_id]
            
    def _listen_for_incoming_calls(self, account_id: int, port: int):
        """Listen for incoming calls on specified port"""
        try:
            # Create socket for listening
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            sock.settimeout(1.0)  # 1 second timeout for checking if we should stop
            
            print(f"🎧 Listening for incoming calls on port {port} for account {account_id}")
            
            while account_id in self.sip_manager.accounts:
                try:
                    data, addr = sock.recvfrom(4096)
                    message = data.decode('utf-8')
                    
                    # Handle different types of incoming messages
                    if message.startswith('INVITE'):
                        self._handle_incoming_invite(account_id, message, addr, sock)
                    elif message.startswith('OPTIONS'):
                        self._handle_incoming_options(account_id, message, addr, sock)
                    elif message.startswith('BYE'):
                        self._handle_incoming_bye(account_id, message, addr, sock)
                    elif message.startswith('CANCEL'):
                        self._handle_incoming_cancel(account_id, message, addr, sock)
                    elif message.startswith('ACK'):
                        self._handle_incoming_ack(account_id, message, addr, sock)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error receiving incoming call data: {e}")
                    
        except Exception as e:
            print(f"Error setting up incoming call listener for account {account_id}: {e}")
        finally:
            try:
                sock.close()
            except:
                pass
                
    def _handle_incoming_invite(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming INVITE (call request)"""
        try:
            print(f"📞 Incoming INVITE to account {account_id} from {addr}")
            
            # Parse the INVITE message
            call_info = self._parse_invite_message(message)
            call_id = call_info.get('call_id', 'unknown')
            from_user = call_info.get('from_user', 'unknown')
            
            # Store call information with original message
            self.active_calls[call_id] = {
                'account_id': account_id,
                'from_user': from_user,
                'from_addr': addr,
                'sock': sock,
                'state': 'INCOMING',
                'start_time': time.time(),
                'original_message': message,
                'call_info': call_info
            }
            
            # Send 100 Trying immediately
            trying_response = self._create_100_trying_response(call_info)
            sock.sendto(trying_response.encode('utf-8'), addr)
            print(f"📤 Sent 100 Trying for call {call_id}")
            
            # Notify GUI about incoming call
            if self.on_incoming_call:
                self.on_incoming_call(account_id, call_id, from_user, addr)
            else:
                # Auto-answer after 2 seconds if no GUI handler
                threading.Timer(2.0, self._auto_answer_call, args=(call_id,)).start()
                
        except Exception as e:
            print(f"Error handling incoming INVITE: {e}")
            
    def _parse_invite_message(self, message: str) -> Dict[str, str]:
        """Parse incoming INVITE message to extract key information"""
        info = {}
        lines = message.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('Call-ID:'):
                info['call_id'] = line.split(':', 1)[1].strip()
            elif line.startswith('From:'):
                from_header = line.split(':', 1)[1].strip()
                info['from_header'] = from_header
                # Extract username from From header
                user_match = re.search(r'sip:([^@]+)@', from_header)
                if user_match:
                    info['from_user'] = user_match.group(1)
            elif line.startswith('To:'):
                info['to_header'] = line.split(':', 1)[1].strip()
            elif line.startswith('Via:'):
                info['via_header'] = line.split(':', 1)[1].strip()
            elif line.startswith('CSeq:'):
                info['cseq'] = line.split(':', 1)[1].strip()
            elif line.startswith('Contact:'):
                info['contact'] = line.split(':', 1)[1].strip()
                
        return info
        
    def _create_100_trying_response(self, call_info: Dict[str, str]) -> str:
        """Create 100 Trying response for incoming INVITE"""
        return f"""SIP/2.0 100 Trying
Via: {call_info.get('via_header', '')}
From: {call_info.get('from_header', '')}
To: {call_info.get('to_header', '')}
Call-ID: {call_info.get('call_id', '')}
CSeq: {call_info.get('cseq', '')}
Content-Length: 0

"""

    def answer_call(self, call_id: str) -> bool:
        """Answer an incoming call"""
        if call_id not in self.active_calls:
            print(f"Call {call_id} not found")
            return False
            
        call = self.active_calls[call_id]
        try:
            # Create 200 OK response with SDP
            response = self._create_200_ok_response(call_id)
            call['sock'].sendto(response.encode('utf-8'), call['from_addr'])
            
            call['state'] = 'ANSWERED'
            print(f"✅ Answered call {call_id} from {call['from_user']}")
            return True
            
        except Exception as e:
            print(f"Error answering call {call_id}: {e}")
            return False
            
    def reject_call(self, call_id: str) -> bool:
        """Reject an incoming call"""
        if call_id not in self.active_calls:
            return False
            
        call = self.active_calls[call_id]
        try:
            # Create 486 Busy Here response
            response = self._create_486_busy_response(call_id)
            call['sock'].sendto(response.encode('utf-8'), call['from_addr'])
            
            call['state'] = 'REJECTED'
            print(f"❌ Rejected call {call_id} from {call['from_user']}")
            
            # Clean up call
            del self.active_calls[call_id]
            return True
            
        except Exception as e:
            print(f"Error rejecting call {call_id}: {e}")
            return False
            
    def _auto_answer_call(self, call_id: str):
        """Automatically answer a call after timeout"""
        if call_id in self.active_calls and self.active_calls[call_id]['state'] == 'INCOMING':
            print(f"🤖 Auto-answering call {call_id}")
            self.answer_call(call_id)
            
    def _create_200_ok_response(self, call_id: str) -> str:
        """Create 200 OK response for answered call"""
        if call_id not in self.active_calls:
            return ""
            
        call = self.active_calls[call_id]
        call_info = call['call_info']
        
        # Get local IP and port
        local_ip = self.sip_manager.local_ip
        local_port = call['sock'].getsockname()[1]
        
        # Create SDP for audio
        sdp = f"""v=0
o=user 123456 123456 IN IP4 {local_ip}
s=-
c=IN IP4 {local_ip}
t=0 0
m=audio {local_port + 1000} RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""

        response = f"""SIP/2.0 200 OK
Via: {call_info.get('via_header', '')}
From: {call_info.get('from_header', '')}
To: {call_info.get('to_header', '')};tag=incoming-{int(time.time())}
Call-ID: {call_id}
CSeq: {call_info.get('cseq', '')}
Contact: <sip:{local_ip}:{local_port}>
Content-Type: application/sdp
Content-Length: {len(sdp)}

{sdp}"""
        
        return response
        
    def _create_486_busy_response(self, call_id: str) -> str:
        """Create 486 Busy Here response"""
        if call_id not in self.active_calls:
            return ""
            
        call = self.active_calls[call_id]
        call_info = call['call_info']
        
        return f"""SIP/2.0 486 Busy Here
Via: {call_info.get('via_header', '')}
From: {call_info.get('from_header', '')}
To: {call_info.get('to_header', '')};tag=busy-{int(time.time())}
Call-ID: {call_id}
CSeq: {call_info.get('cseq', '')}
Content-Length: 0

"""

    def _handle_incoming_options(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming OPTIONS request"""
        self.sip_manager._send_options_response(sock, message, addr)
        
    def _handle_incoming_bye(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming BYE (call hangup)"""
        call_info = self._parse_invite_message(message)
        call_id = call_info.get('call_id')
        
        if call_id in self.active_calls:
            print(f"📞 Call {call_id} ended by remote party")
            del self.active_calls[call_id]
            
        # Send 200 OK to BYE
        response = f"""SIP/2.0 200 OK
Via: {call_info.get('via_header', '')}
From: {call_info.get('from_header', '')}
To: {call_info.get('to_header', '')}
Call-ID: {call_id}
CSeq: {call_info.get('cseq', '')}
Content-Length: 0

"""
        sock.sendto(response.encode('utf-8'), addr)
        
    def _handle_incoming_cancel(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming CANCEL (call cancellation)"""
        call_info = self._parse_invite_message(message)
        call_id = call_info.get('call_id')
        
        if call_id in self.active_calls:
            print(f"📞 Call {call_id} cancelled by remote party")
            del self.active_calls[call_id]
            
        # Send 200 OK to CANCEL
        response = f"""SIP/2.0 200 OK
Via: {call_info.get('via_header', '')}
From: {call_info.get('from_header', '')}
To: {call_info.get('to_header', '')}
Call-ID: {call_id}
CSeq: {call_info.get('cseq', '')}
Content-Length: 0

"""
        sock.sendto(response.encode('utf-8'), addr)
        
    def _handle_incoming_ack(self, account_id: int, message: str, addr: tuple, sock: socket.socket):
        """Handle incoming ACK (call establishment confirmation)"""
        call_info = self._parse_invite_message(message)
        call_id = call_info.get('call_id')
        
        if call_id in self.active_calls:
            self.active_calls[call_id]['state'] = 'ESTABLISHED'
            print(f"✅ Call {call_id} established successfully")
            
    def get_active_calls(self) -> Dict:
        """Get list of active calls"""
        return self.active_calls.copy()
        
    def hangup_call(self, call_id: str) -> bool:
        """Hangup an active call"""
        if call_id not in self.active_calls:
            return False
            
        call = self.active_calls[call_id]
        try:
            # Send BYE to hangup
            bye_msg = self._create_bye_message(call_id)
            call['sock'].sendto(bye_msg.encode('utf-8'), call['from_addr'])
            
            print(f"📞 Sent BYE for call {call_id}")
            del self.active_calls[call_id]
            return True
            
        except Exception as e:
            print(f"Error hanging up call {call_id}: {e}")
            return False
            
    def _create_bye_message(self, call_id: str) -> str:
        """Create BYE message to hangup call"""
        if call_id not in self.active_calls:
            return ""
            
        call = self.active_calls[call_id]
        local_ip = self.sip_manager.local_ip
        local_port = call['sock'].getsockname()[1]
        
        return f"""BYE sip:{call['from_user']}@{call['from_addr'][0]} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch=z9hG4bK{int(time.time())}
From: <sip:{local_ip}:{local_port}>;tag=local-{int(time.time())}
To: <sip:{call['from_user']}@{call['from_addr'][0]}>
Call-ID: {call_id}
CSeq: 1 BYE
Content-Length: 0

"""
