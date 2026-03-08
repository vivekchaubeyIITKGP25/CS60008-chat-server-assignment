#!/usr/bin/env python3
"""
Thread-Based Chat Server with Authentication, Rooms, Pub-Sub, Redis, and TLS
CS60008 - Internet Architecture and Protocols
"""

import socket
import threading
import ssl
import json
import bcrypt
import redis
import os
import uuid
from datetime import datetime

# Configuration
HOST = os.getenv('SERVER_HOST', '0.0.0.0')
PORT = int(os.getenv('SERVER_PORT', 9999))
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
USE_TLS = os.getenv('USE_TLS', 'true').lower() == 'true'
CERT_FILE = os.getenv('CERT_FILE', 'server.crt')
KEY_FILE = os.getenv('KEY_FILE', 'server.key')

class ChatServer:
    def __init__(self):
        # Redis connection
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        self.redis_pubsub = self.redis_client.pubsub()
        
        # Local state (connections only, sessions in Redis)
        self.clients = {}  # socket -> (username, session_id)
        self.clients_lock = threading.Lock()
        
        # Server identification for multi-instance support
        self.server_id = os.getenv('SERVER_ID', f'server_{os.getpid()}')
        
        # Start Redis subscriber thread
        self.running = True
        self.pubsub_thread = threading.Thread(target=self._redis_subscriber, daemon=True)
        self.pubsub_thread.start()
        
        print(f"[Server {self.server_id}] Initialized")
        print(f"[Server {self.server_id}] Redis connection: {REDIS_HOST}:{REDIS_PORT}")
    
    def _redis_subscriber(self):
        """Listen for messages from Redis pub/sub"""
        self.redis_pubsub.subscribe('chat_broadcast')
        
        for message in self.redis_pubsub.listen():
            if not self.running:
                break
            
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    # Only broadcast if this server has the recipient
                    self._local_broadcast(data)
                except Exception as e:
                    print(f"[Redis Sub Error] {e}")
    
    def _local_broadcast(self, data):
        """Broadcast message to local clients only"""
        msg_type = data.get('type')
        sender = data.get('sender')
        content = data.get('content')
        room = data.get('room')
        
        with self.clients_lock:
            for client_sock, client_info in list(self.clients.items()):
                username = client_info[0]
                try:
                    # Check if message is for this user
                    if msg_type == 'room_message':
                        # Check if user is in the room
                        user_room = self.redis_client.hget(f'session:{username}', 'room')
                        if user_room == room and username != sender:
                            formatted = f"[{room}] {sender}: {content}\n"
                            client_sock.sendall(formatted.encode())
                    
                    elif msg_type == 'pubsub_message':
                        # Check if user is subscribed to sender
                        subscribers = self.redis_client.smembers(f'subscribers:{sender}')
                        if username in subscribers:
                            formatted = f"[@{sender}]: {content}\n"
                            client_sock.sendall(formatted.encode())
                    
                    elif msg_type == 'system':
                        # Optional server-scoped system messages to specific user
                        target = data.get('target')
                        target_server = data.get('target_server_id')
                        if target == username and (not target_server or target_server == self.server_id):
                            client_sock.sendall(f"[SYSTEM] {content}\n".encode())
                    
                    elif msg_type == 'force_logout':
                        # Force logout only if this server holds the old connection
                        target = data.get('target')
                        old_server = data.get('old_server_id')
                        notice = data.get('content') or "You have been logged out (new login detected)"
                        if target == username and old_server == self.server_id:
                            try:
                                client_sock.sendall(f"[SYSTEM] {notice}\n".encode())
                            except:
                                pass
                            try:
                                client_sock.close()
                            except:
                                pass
                            self._remove_local_client(client_sock)
                
                except Exception as e:
                    print(f"[Broadcast Error] {username}: {e}")
    
    def _publish_message(self, msg_type, sender, content, room=None, target=None):
        """Publish message to Redis for cross-server communication"""
        data = {
            'type': msg_type,
            'sender': sender,
            'content': content,
            'room': room,
            'target': target,
            'server_id': self.server_id,
            'timestamp': datetime.now().isoformat()
        }
        self.redis_client.publish('chat_broadcast', json.dumps(data))
    
    def register_user(self, username, password):
        """Register a new user with hashed password"""
        if self.redis_client.exists(f'user:{username}'):
            return False, "Username already exists"
        
        # Hash password with bcrypt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        
        # Store in Redis
        self.redis_client.hset(f'user:{username}', mapping={
            'password': hashed.decode(),
            'created': datetime.now().isoformat()
        })
        
        return True, "Registration successful"
    
    def authenticate(self, username, password):
        """Authenticate user credentials"""
        user_data = self.redis_client.hgetall(f'user:{username}')
        
        if not user_data:
            return False, "Invalid username or password"
        
        stored_hash = user_data['password'].encode()
        
        if bcrypt.checkpw(password.encode(), stored_hash):
            return True, "Authentication successful"
        
        return False, "Invalid username or password"
    
    def check_duplicate_login(self, username):
        """
        Check if user is already logged in
        Policy: FORCE LOGOUT EXISTING SESSION
        Returns: (has_existing_session, session_data)
        """
        session_key = f'session:{username}'
        session_data = self.redis_client.hgetall(session_key)
        
        if session_data:
            return True, session_data
        return False, None
    
    def create_session(self, username, client_socket):
        """Create user session in Redis"""
        session_key = f'session:{username}'
        session_id = uuid.uuid4().hex
        
        self.redis_client.hset(session_key, mapping={
            'username': username,
            'server_id': self.server_id,
            'room': 'lobby',
            'login_time': datetime.now().isoformat(),
            'session_id': session_id
        })
        
        # Add to lobby by default
        self.redis_client.sadd('room:lobby', username)
        
        # Register local connection
        with self.clients_lock:
            self.clients[client_socket] = (username, session_id)
    
    def remove_session(self, username, client_socket=None):
        """Remove user session from Redis and local state"""
        session_key = f'session:{username}'
        session_data = self.redis_client.hgetall(session_key)
        should_delete_redis = False

        if session_data:
            if client_socket is None:
                # Administrative cleanup (e.g., duplicate login) - delete regardless of server_id
                should_delete_redis = True
            else:
                # Only delete if this connection owns the active session
                local_session_id = None
                with self.clients_lock:
                    client_info = self.clients.get(client_socket)
                    if client_info:
                        local_session_id = client_info[1]
                if (
                    session_data.get('server_id') == self.server_id
                    and local_session_id
                    and session_data.get('session_id') == local_session_id
                ):
                    should_delete_redis = True

        if should_delete_redis and session_data:
            current_room = session_data.get('room', 'lobby')
            self.redis_client.srem(f'room:{current_room}', username)
            self.redis_client.delete(session_key)
        
        # Remove from local clients
        if client_socket:
            self._remove_local_client(client_socket)

    def _disconnect_local_user(self, username, reason=None):
        """Disconnect all local sockets for a username"""
        sockets = []
        with self.clients_lock:
            for sock, client_info in list(self.clients.items()):
                if client_info[0] == username:
                    sockets.append(sock)
        for sock in sockets:
            if reason:
                try:
                    sock.sendall(f"[SYSTEM] {reason}\n".encode())
                except:
                    pass
            try:
                sock.close()
            except:
                pass
            self._remove_local_client(sock)

    def _remove_local_client(self, client_socket):
        """Remove a client socket from local tracking only"""
        with self.clients_lock:
            self.clients.pop(client_socket, None)
    
    def handle_client(self, client_socket, client_address):
        """Handle individual client connection"""
        print(f"[Connection] New connection from {client_address}")
        
        username = None
        authenticated = False
        
        try:
            # Send welcome message
            client_socket.sendall(b"=== Chat Server ===\n")
            client_socket.sendall(b"Commands: REGISTER <username> <password> or LOGIN <username> <password>\n")
            
            # Authentication phase
            while not authenticated:
                data = client_socket.recv(4096).decode().strip()
                
                if not data:
                    break
                
                parts = data.split()
                
                if len(parts) < 3:
                    client_socket.sendall(b"ERROR: Invalid command format\n")
                    continue
                
                command = parts[0].upper()
                username_input = parts[1]
                password_input = parts[2]
                
                if command == 'REGISTER':
                    success, message = self.register_user(username_input, password_input)
                    if success:
                        client_socket.sendall(f"SUCCESS: {message}\n".encode())
                        client_socket.sendall(b"Now please LOGIN\n")
                    else:
                        client_socket.sendall(f"ERROR: {message}\n".encode())
                
                elif command == 'LOGIN':
                    # Authenticate
                    success, message = self.authenticate(username_input, password_input)
                    
                    if not success:
                        client_socket.sendall(f"ERROR: {message}\n".encode())
                        continue
                    
                    # Check for duplicate login (Force Logout Policy)
                    has_duplicate, old_session = self.check_duplicate_login(username_input)
                    
                    if has_duplicate:
                        # Force logout the old session
                        old_server = old_session.get('server_id')
                        if old_server == self.server_id:
                            self._disconnect_local_user(
                                username_input,
                                reason="You have been logged out (new login from another location)"
                            )
                        else:
                            self.redis_client.publish('chat_broadcast', json.dumps({
                                'type': 'force_logout',
                                'target': username_input,
                                'old_server_id': old_server,
                                'content': 'You have been logged out (new login from another location)',
                                'server_id': self.server_id,
                                'timestamp': datetime.now().isoformat()
                            }))
                        # Give time for message to be delivered
                        threading.Event().wait(0.5)
                        # Clean up old session in Redis
                        self.remove_session(username_input)
                    
                    # Create new session
                    username = username_input
                    self.create_session(username, client_socket)
                    authenticated = True
                    
                    client_socket.sendall(f"SUCCESS: Welcome {username}! You are in 'lobby'\n".encode())
                    client_socket.sendall(b"Commands: /join <room>, /leave, /rooms, /subscribe <user>, /unsubscribe <user>, /subscriptions, /help, /quit\n")
                
                else:
                    client_socket.sendall(b"ERROR: Unknown command. Use REGISTER or LOGIN\n")
            
            if not authenticated:
                return
            
            # Main message loop
            while self.running:
                data = client_socket.recv(4096).decode().strip()
                
                if not data:
                    break
                
                # Handle commands
                if data.startswith('/'):
                    should_disconnect = self.handle_command(username, client_socket, data)
                    if should_disconnect:
                        break
                else:
                    # Regular message - check current mode
                    session = self.redis_client.hgetall(f'session:{username}')
                    if not session:
                        client_socket.sendall(b"ERROR: Session expired. Please reconnect and LOGIN again.\n")
                        break
                    current_room = session.get('room', 'lobby')
                    
                    if current_room:
                        # Room-based messaging
                        self._publish_message('room_message', username, data, room=current_room)
                        # Echo to sender
                        client_socket.sendall(f"[{current_room}] {username}: {data}\n".encode())
                    else:
                        # Pub-sub mode
                        self._publish_message('pubsub_message', username, data)
                        # Echo to sender
                        client_socket.sendall(f"[@{username}]: {data}\n".encode())
        
        except Exception as e:
            print(f"[Error] Client {username or client_address}: {e}")
        
        finally:
            if username:
                print(f"[Disconnect] {username}")
                self.remove_session(username, client_socket)
            
            try:
                client_socket.close()
            except:
                pass
    
    def handle_command(self, username, client_socket, command):
        """Handle client commands"""
        parts = command.split()
        cmd = parts[0].lower()
        
        try:
            if cmd == '/join':
                if len(parts) < 2:
                    client_socket.sendall(b"ERROR: Usage: /join <room>\n")
                    return
                
                room_name = parts[1]
                session = self.redis_client.hgetall(f'session:{username}')
                old_room = session.get('room')
                
                # Leave old room
                if old_room:
                    self.redis_client.srem(f'room:{old_room}', username)
                
                # Join new room
                self.redis_client.sadd(f'room:{room_name}', username)
                self.redis_client.hset(f'session:{username}', 'room', room_name)
                
                client_socket.sendall(f"SUCCESS: Joined room '{room_name}'\n".encode())
            
            elif cmd == '/leave':
                session = self.redis_client.hgetall(f'session:{username}')
                current_room = session.get('room')
                
                if current_room:
                    self.redis_client.srem(f'room:{current_room}', username)
                    self.redis_client.hset(f'session:{username}', 'room', '')
                    client_socket.sendall(f"SUCCESS: Left room '{current_room}'\n".encode())
                else:
                    client_socket.sendall(b"ERROR: You are not in any room\n")
            
            elif cmd == '/rooms':
                # Get all rooms from Redis
                keys = self.redis_client.keys('room:*')
                rooms = [key.split(':')[1] for key in keys]
                
                if rooms:
                    client_socket.sendall(f"Available rooms: {', '.join(rooms)}\n".encode())
                else:
                    client_socket.sendall(b"No rooms available\n")
            
            elif cmd == '/subscribe':
                if len(parts) < 2:
                    client_socket.sendall(b"ERROR: Usage: /subscribe <username>\n")
                    return
                
                target_user = parts[1]
                
                # Check if target user exists
                if not self.redis_client.exists(f'user:{target_user}'):
                    client_socket.sendall(f"ERROR: User '{target_user}' does not exist\n".encode())
                    return
                
                if target_user == username:
                    client_socket.sendall(b"ERROR: Cannot subscribe to yourself\n")
                    return
                
                # Add to subscriber list
                self.redis_client.sadd(f'subscribers:{target_user}', username)
                client_socket.sendall(f"SUCCESS: Subscribed to @{target_user}\n".encode())
            
            elif cmd == '/unsubscribe':
                if len(parts) < 2:
                    client_socket.sendall(b"ERROR: Usage: /unsubscribe <username>\n")
                    return
                
                target_user = parts[1]
                self.redis_client.srem(f'subscribers:{target_user}', username)
                client_socket.sendall(f"SUCCESS: Unsubscribed from @{target_user}\n".encode())
            
            elif cmd == '/subscriptions':
                # Show who this user is subscribed to
                keys = self.redis_client.keys('subscribers:*')
                subscribed_to = []
                
                for key in keys:
                    if self.redis_client.sismember(key, username):
                        publisher = key.split(':')[1]
                        subscribed_to.append(publisher)
                
                if subscribed_to:
                    client_socket.sendall(f"You are subscribed to: {', '.join(subscribed_to)}\n".encode())
                else:
                    client_socket.sendall(b"You have no subscriptions\n")
            
            elif cmd == '/help':
                help_text = """
Available commands:
  /join <room>          - Join a chat room
  /leave                - Leave current room
  /rooms                - List all rooms
  /subscribe <user>     - Subscribe to a user's messages
  /unsubscribe <user>   - Unsubscribe from a user
  /subscriptions        - List your subscriptions
  /help                 - Show this help
  /quit                 - Disconnect
"""
                client_socket.sendall(help_text.encode())
            
            elif cmd == '/quit':
                client_socket.sendall(b"Goodbye!\n")
                try:
                    client_socket.close()
                except:
                    pass
                return True
            
            else:
                client_socket.sendall(f"ERROR: Unknown command '{cmd}'\n".encode())
        
        except Exception as e:
            client_socket.sendall(f"ERROR: {str(e)}\n".encode())
        
        return False
    
    def start(self):
        """Start the chat server"""
        # Create socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        
        # Wrap with TLS if enabled
        if USE_TLS:
            if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
                print(f"[ERROR] TLS enabled but certificate files not found!")
                print(f"[ERROR] Looking for: {CERT_FILE}, {KEY_FILE}")
                return
            
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(CERT_FILE, KEY_FILE)
            server_socket = context.wrap_socket(server_socket, server_side=True)
            print(f"[Server] TLS enabled")
        
        print(f"[Server] Listening on {HOST}:{PORT}")
        print(f"[Server] ID: {self.server_id}")
        
        try:
            while self.running:
                try:
                    client_socket, client_address = server_socket.accept()
                    
                    # Create new thread for client
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                
                except Exception as e:
                    if self.running:
                        print(f"[Error] Accept failed: {e}")
        
        except KeyboardInterrupt:
            print("\n[Server] Shutting down...")
        
        finally:
            self.running = False
            server_socket.close()
            self.redis_pubsub.close()
            self.redis_client.close()

if __name__ == '__main__':
    server = ChatServer()
    server.start()
