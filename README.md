# CS60008 Assignment 1 - Thread-Based Chat Server

I built this project for CS60008 (Internet Architecture and Protocols).  
The server is thread-based, uses Redis for shared state, supports TLS, and can run with Docker.

## What I Implemented

### Problem 1 - Thread-Based Chat Server
- TCP server built with `socket`
- One thread per client using `threading.Thread`
- Graceful disconnect handling
- Broadcast behavior is implemented through room and subscription routing

### Problem 2 - Authentication
- `REGISTER <username> <password>` for account creation
- `LOGIN <username> <password>` for sign-in
- Passwords are hashed with `bcrypt`
- Session is tracked per authenticated connection

### Problem 3 - Duplicate Login Handling
- Policy used: **Force Logout Existing Session**
- If the same user logs in again, the old session is notified and disconnected
- The new login succeeds and becomes the active session

### Problem 4 - Chat Rooms
- `/join <room>`
- `/leave`
- `/rooms`
- Default room on login: `lobby`
- Room messages are delivered only to users in the same room

### Problem 5 - Publish-Subscribe Model
- `/subscribe <username>`
- `/unsubscribe <username>`
- `/subscriptions`
- Messages are multicast only to subscribers when sender is not in a room (`/leave`)
- Subscription state is stored centrally in Redis

### Problem 6 - Redis Integration
- Sessions stored as Redis hashes: `session:<username>`
- Room membership stored as Redis sets: `room:<room>`
- Cross-server communication uses Redis Pub/Sub channel: `chat_broadcast`
- Server instances remain stateless for global session/room state

### Problem 7 - TLS / Encrypted Transport
- Server wraps sockets with Python `ssl` (`ssl.PROTOCOL_TLS_SERVER`)
- Client verifies certificate using `server.crt` (pinned cert for local testing)
- Plaintext clients are rejected when TLS is enabled

### Problem 8 - Dockerized Deployment
- `Dockerfile` for server
- `docker-compose.yml` to start Redis + two server instances
- `docker-compose up --build` starts the test setup

## Project Files

- `server.py`: main server
- `client.py`: CLI client
- `requirements.txt`: Python dependencies
- `Dockerfile`: container image for server
- `docker-compose.yml`: Redis + two server instances
- `generate_cert.sh`: self-signed TLS certificate generation
- `run_local.sh`: helper script for local Linux/macOS setup

## Redis Data Layout

```text
user:<username>                 # hash: password, created
session:<username>              # hash: username, server_id, room, login_time, session_id
room:<room_name>                # set: usernames in room
subscribers:<publisher_username># set: subscribers of publisher
```

## Setup

### Option 1: Docker (recommended)

```bash
docker-compose up --build
```

This starts:
- Redis on `6379`
- Server 1 on `9999`
- Server 2 on `9998`

### Option 2: Local run

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Start Redis (example with Docker):
```bash
docker run -d --name chat_redis -p 6379:6379 redis:7-alpine
```

3. Generate certificates:
```bash
./generate_cert.sh
```

4. Start server:
```bash
python server.py
```

5. Start client:
```bash
python client.py
```

## Credentials and Testing Flow

1. In client A:
```text
REGISTER vivek pass123
LOGIN vivek pass123
/join lobby
```

2. In client B:
```text
REGISTER sakshi pass456
LOGIN sakshi pass456
/join lobby
```

3. In client C:
```text
REGISTER apeksha pass789
LOGIN apeksha pass789
/join lobby
```

4. Send a normal message from vivek and verify sakshi/apeksha receive it.

5. Duplicate login test:
- Open a new client and run `LOGIN vivek pass123`
- Old vivek session should receive logout notice and disconnect

6. Pub-sub test:
- sakshi: `/leave`
- apeksha: `/subscribe sakshi`
- sakshi sends a message
- apeksha should receive `[@sakshi]: ...`

7. Cross-server test:
- Connect vivek to port `9999`
- Connect sakshi to port `9998`
- Put both in same room and verify messages are delivered across instances

## Useful Environment Variables

- `SERVER_HOST` (default: `0.0.0.0`)
- `SERVER_PORT` (default: `9999`)
- `REDIS_HOST` (default: `localhost`)
- `REDIS_PORT` (default: `6379`)
- `USE_TLS` (default: `true`)
- `CERT_FILE` (default: `server.crt`)
- `KEY_FILE` (default: `server.key`)
- `CA_CERT` (client-side, default: `server.crt`)
- `SERVER_ID` (default: `server_<pid>`)

## Notes

- I used the force-logout policy for duplicate sessions.
- This project is focused on assignment requirements, not production hardening.
- Message history and private direct messages are not implemented.
