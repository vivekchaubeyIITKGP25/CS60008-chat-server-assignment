#!/usr/bin/env python3
"""
Thread-Based Chat Server - Problems 1-4
CS60008 - Internet Architecture and Protocols

Problems Implemented:
1. Thread-Based Chat Server
2. Authentication
3. Duplicate Login Handling (Force Logout Policy)
4. Chat Rooms
"""

import socket
import threading
import hashlib
import json
import os
from datetime import datetime

# Configuration
HOST = os.getenv('SERVER_HOST', '0.0.0.0')
PORT = int(os.getenv('SERVER_PORT', 9999))

class ChatServer:
    def __init__(self):
        # In-memory storage (simulating database)
        self.users = {}  # username -> {'password_hash': hash, 'salt': salt}
        self.sessions = {}  # username -> {'socket': socket, 'room': room}
        self.rooms = {'lobby': set()}  # room_name -> set of usernames
        
        # Thread synchronization
        self.users_lock = threading.Lock()
        self.sessions_lock = threading.Lock()
        self.rooms_lock = threading.Lock()
        
        print("[Server] Initialized")
        print(f"[Server] Storage: In-memory dictionaries")
    
    def hash_password(self, password, salt=None):
        """Hash password with salt using SHA-256"""
        if salt is None:
            salt = os.urandom(32).hex()
        
        # Combine password and salt, then hash
        pwd_salt = (password + salt).encode()
        pwd_hash = hashlib.sha256(pwd_salt).hexdigest()
        
        return pwd_hash, salt
    
    def register_user(self, username, password):
        """Register a new user with hashed password"""
        with self.users_lock:
            if username in self.users:
                return False, "Username already exists"
            
            # Hash the password
            pwd_hash, salt = self.hash_password(password)
            
            # Store user credentials
            self.users[username] = {
                'password_hash': pwd_hash,
                'salt': salt,
                'created': datetime.now().isoformat()
            }
            
            print(f"[Register] User '{username}' registered successfully")
            return True, "Registration successful"
    
    def authenticate(self, username, password):
        """Authenticate user credentials"""
        with self.users_lock:
            if username not in self.users:
                return False, "Invalid username or password"
            
            user_data = self.users[username]
            pwd_hash, _ = self.hash_password(password, user_data['salt'])
            
            if pwd_hash == user_data['password_hash']:
                return True, "Authentication successful"
            
            return False, "Invalid username or password"
    
    def check_duplicate_login(self, username):
        """
        Check if user is already logged in
        Policy: FORCE LOGOUT EXISTING SESSION
        """
        with self.sessions_lock:
            if username in self.sessions:
                return True, self.sessions[username]
            return False, None
    
    def force_logout(self, username):
        """Force logout existing session"""
        with self.sessions_lock:
            if username in self.sessions:
                old_session = self.sessions[username]
                old_socket = old_session['socket']
                old_room = old_session['room']
                
                # Send notification to old session
                try:
                    message = "\n[SYSTEM] You have been logged out (new login from another location)\n"
                    old_socket.sendall(message.encode())
                except:
                    pass
                
                # Remove from room
                with self.rooms_lock:
                    if old_room in self.rooms:
                        self.rooms[old_room].discard(username)
                
                # Close old connection
                try:
                    old_socket.close()
                except:
                    pass
                
                # Remove session
                del self.sessions[username]
                
                print(f"[Force Logout] User '{username}' previous session terminated")
    
    def create_session(self, username, client_socket):
        """Create user session"""
        with self.sessions_lock:
            self.sessions[username] = {
                'socket': client_socket,
                'room': 'lobby',
                'login_time': datetime.now().isoformat()
            }
        
        # Add to lobby
        with self.rooms_lock:
            self.rooms['lobby'].add(username)
        
        print(f"[Session] User '{username}' logged in, joined 'lobby'")
    
    def remove_session(self, username):
        """Remove user session"""
        with self.sessions_lock:
            if username not in self.sessions:
                return
            
            session = self.sessions[username]
            current_room = session['room']
            
            # Remove from room
            with self.rooms_lock:
                if current_room in self.rooms:
                    self.rooms[current_room].discard(username)
            
            # Remove session
            del self.sessions[username]
        
        print(f"[Disconnect] User '{username}' logged out")
    
    def join_room(self, username, room_name):
        """Join a chat room"""
        with self.sessions_lock:
            if username not in self.sessions:
                return False, "Not logged in"
            
            session = self.sessions[username]
            old_room = session['room']
            
            # Leave old room
            with self.rooms_lock:
                if old_room in self.rooms:
                    self.rooms[old_room].discard(username)
                
                # Create room if doesn't exist
                if room_name not in self.rooms:
                    self.rooms[room_name] = set()
                
                # Join new room
                self.rooms[room_name].add(username)
            
            # Update session
            session['room'] = room_name
            
            print(f"[Room] User '{username}' joined room '{room_name}' (left '{old_room}')")
            return True, f"Joined room '{room_name}'"
    
    def leave_room(self, username):
        """Leave current room"""
        with self.sessions_lock:
            if username not in self.sessions:
                return False, "Not logged in"
            
            session = self.sessions[username]
            current_room = session['room']
            
            if not current_room:
                return False, "Not in any room"
            
            # Remove from room
            with self.rooms_lock:
                if current_room in self.rooms:
                    self.rooms[current_room].discard(username)
            
            # Clear room from session
            session['room'] = None
            
            print(f"[Room] User '{username}' left room '{current_room}'")
            return True, f"Left room '{current_room}'"
    
    def list_rooms(self):
        """Get list of all rooms"""
        with self.rooms_lock:
            return list(self.rooms.keys())
    
    def broadcast_to_room(self, room_name, message, exclude_user=None):
        """Broadcast message to all users in a room"""
        with self.rooms_lock:
            if room_name not in self.rooms:
                return
            
            room_members = self.rooms[room_name].copy()
        
        # Send to each member
        with self.sessions_lock:
            for username in room_members:
                if username == exclude_user:
                    continue
                
                if username in self.sessions:
                    try:
                        socket = self.sessions[username]['socket']
                        socket.sendall(message.encode())
                    except Exception as e:
                        print(f"[Broadcast Error] Failed to send to '{username}': {e}")
    
    def handle_client(self, client_socket, client_address):
        """Handle individual client connection"""
        print(f"[Connection] New connection from {client_address}")
        
        username = None
        authenticated = False
        
        try:
            # Send welcome message
            welcome = "=== Chat Server ===\n"
            welcome += "Commands: REGISTER <username> <password> or LOGIN <username> <password>\n"
            client_socket.sendall(welcome.encode())
            
            # Authentication phase
            while not authenticated:
                data = client_socket.recv(4096).decode().strip()
                
                if not data:
                    break
                
                parts = data.split()
                
                if len(parts) < 3:
                    client_socket.sendall(b"ERROR: Invalid command format\n")
                    client_socket.sendall(b"Usage: REGISTER <username> <password> or LOGIN <username> <password>\n")
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
                    
                    # Check for duplicate login (Problem 3: Force Logout Policy)
                    has_duplicate, old_session = self.check_duplicate_login(username_input)
                    
                    if has_duplicate:
                        # Force logout the old session
                        self.force_logout(username_input)
                        # Small delay to ensure message is delivered
                        threading.Event().wait(0.3)
                    
                    # Create new session
                    username = username_input
                    self.create_session(username, client_socket)
                    authenticated = True
                    
                    welcome_msg = f"SUCCESS: Welcome {username}! You are in 'lobby'\n"
                    welcome_msg += "Commands: /join <room>, /leave, /rooms, /help, /quit\n"
                    client_socket.sendall(welcome_msg.encode())
                
                else:
                    client_socket.sendall(b"ERROR: Unknown command. Use REGISTER or LOGIN\n")
            
            if not authenticated:
                return
            
            # Main message loop
            while True:
                data = client_socket.recv(4096).decode().strip()
                
                if not data:
                    break
                
                # Handle commands
                if data.startswith('/'):
                    self.handle_command(username, client_socket, data)
                else:
                    # Regular message - broadcast to room
                    with self.sessions_lock:
                        if username not in self.sessions:
                            break
                        current_room = self.sessions[username]['room']
                    
                    if current_room:
                        # Format and broadcast message
                        formatted_msg = f"[{current_room}] {username}: {data}\n"
                        
                        # Echo to sender
                        client_socket.sendall(formatted_msg.encode())
                        
                        # Broadcast to room members
                        self.broadcast_to_room(current_room, formatted_msg, exclude_user=username)
                    else:
                        client_socket.sendall(b"ERROR: You are not in any room. Use /join <room>\n")
        
        except Exception as e:
            print(f"[Error] Client {username or client_address}: {e}")
        
        finally:
            if username:
                self.remove_session(username)
            
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
                success, message = self.join_room(username, room_name)
                
                if success:
                    client_socket.sendall(f"SUCCESS: {message}\n".encode())
                else:
                    client_socket.sendall(f"ERROR: {message}\n".encode())
            
            elif cmd == '/leave':
                success, message = self.leave_room(username)
                
                if success:
                    client_socket.sendall(f"SUCCESS: {message}\n".encode())
                else:
                    client_socket.sendall(f"ERROR: {message}\n".encode())
            
            elif cmd == '/rooms':
                rooms = self.list_rooms()
                
                if rooms:
                    client_socket.sendall(f"Available rooms: {', '.join(rooms)}\n".encode())
                else:
                    client_socket.sendall(b"No rooms available\n")
            
            elif cmd == '/help':
                help_text = """
Available commands:
  /join <room>   - Join a chat room
  /leave         - Leave current room
  /rooms         - List all rooms
  /help          - Show this help
  /quit          - Disconnect
"""
                client_socket.sendall(help_text.encode())
            
            elif cmd == '/quit':
                client_socket.sendall(b"Goodbye!\n")
                client_socket.close()
            
            else:
                client_socket.sendall(f"ERROR: Unknown command '{cmd}'\n".encode())
        
        except Exception as e:
            client_socket.sendall(f"ERROR: {str(e)}\n".encode())
    
    def start(self):
        """Start the chat server"""
        # Create socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        
        print(f"[Server] Listening on {HOST}:{PORT}")
        print(f"[Server] Press Ctrl+C to stop")
        
        try:
            while True:
                try:
                    client_socket, client_address = server_socket.accept()
                    
                    # Create new thread for client (Problem 1: Thread-Based Server)
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                
                except Exception as e:
                    print(f"[Error] Accept failed: {e}")
        
        except KeyboardInterrupt:
            print("\n[Server] Shutting down...")
        
        finally:
            server_socket.close()

if __name__ == '__main__':
    server = ChatServer()
    server.start()
