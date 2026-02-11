#!/usr/bin/env python3
import socket
import threading
import sys
import os

# Configuration
HOST = os.getenv('SERVER_HOST', 'localhost')
PORT = int(os.getenv('SERVER_PORT', 9999))

class ChatClient:
    def __init__(self):
        self.socket = None
        self.running = True
    
    def connect(self):
        """Connect to the chat server"""
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Connect to server
            self.socket.connect((HOST, PORT))
            print(f"[Client] Connected to {HOST}:{PORT}\n")
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
