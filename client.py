#!/usr/bin/env python3
import socket
import ssl
import threading
import sys
import os

# Configuration
HOST = os.getenv('SERVER_HOST', 'localhost')
PORT = int(os.getenv('SERVER_PORT', 9999))
USE_TLS = os.getenv('USE_TLS', 'true').lower() == 'true'
CA_CERT = os.getenv('CA_CERT', 'server.crt')

class ChatClient:
    def __init__(self):
        self.socket = None
        self.running = True
    
    def connect(self):
        """Connect to the chat server"""
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Wrap with TLS if enabled
            if USE_TLS:
                if not os.path.exists(CA_CERT):
                    print(f"[ERROR] TLS enabled but CA certificate not found: {CA_CERT}")
                    return False
                
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False  # For self-signed certs
                context.verify_mode = ssl.CERT_REQUIRED
                context.load_verify_locations(CA_CERT)
                
                self.socket = context.wrap_socket(
                    self.socket,
                    server_hostname=HOST
                )
                print("[Client] TLS connection established")
            
            # Connect to server
            self.socket.connect((HOST, PORT))
            print(f"[Client] Connected to {HOST}:{PORT}")
            return True
        
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            return False
    
    def receive_messages(self):
        """Receive messages from server in separate thread"""
        while self.running:
            try:
                data = self.socket.recv(4096)
                
                if not data:
                    print("\n[Disconnected from server]")
                    self.running = False
                    break
                
                message = data.decode()
                print(message, end='')
            
            except Exception as e:
                if self.running:
                    print(f"\n[ERROR] Receive failed: {e}")
                self.running = False
                break
    
    def send_messages(self):
        """Send messages to server"""
        while self.running:
            try:
                message = input()
                
                if not message:
                    continue
                
                if message.lower() == '/quit':
                    self.running = False
                    break
                
                self.socket.sendall(message.encode())
            
            except KeyboardInterrupt:
                print("\n[Exiting...]")
                self.running = False
                break
            
            except Exception as e:
                if self.running:
                    print(f"[ERROR] Send failed: {e}")
                self.running = False
                break
    
    def start(self):
        """Start the client"""
        if not self.connect():
            return
        
        # Start receive thread
        receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
        receive_thread.start()
        
        # Send messages in main thread
        self.send_messages()
        
        # Cleanup
        try:
            self.socket.close()
        except:
            pass
        
        print("[Client] Disconnected")

if __name__ == '__main__':
    client = ChatClient()
    client.start()
