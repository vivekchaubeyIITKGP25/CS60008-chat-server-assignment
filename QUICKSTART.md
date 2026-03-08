# Quick Start

I use this checklist to demo all required features quickly.

## 1. Start Services

```bash
docker-compose up --build
```

Expected:
- Redis is up on `6379`
- Server 1 listens on `9999`
- Server 2 listens on `9998`

## 2. Open Two Clients (Room Chat)

Terminal A:
```bash
python client.py
```
Then:
```text
REGISTER vivek pass123
LOGIN vivek pass123
/join lobby
```

Terminal B:
```bash
python client.py
```
Then:
```text
REGISTER sakshi pass456
LOGIN sakshi pass456
/join lobby
```

Send a message from vivek. sakshi should receive it.

## 3. Duplicate Login Test

Terminal C:
```bash
python client.py
```
Then:
```text
LOGIN vivek pass123
```

Expected:
- Old vivek session is notified and disconnected
- New vivek session stays active

## 4. Publish-Subscribe Test

In sakshi session:
```text
/leave
```

In vivek session:
```text
/subscribe sakshi
```

In sakshi session, send a normal message.  
Expected: vivek receives `[@sakshi]: <message>`.

## 5. Cross-Server Test

Connect one client to server 2:
```bash
SERVER_PORT=9998 python client.py
```

Keep another client on default port `9999`.  
Join same room on both clients and send messages both ways.

Expected:
- Messages are delivered across server instances using Redis Pub/Sub.

## 6. TLS Check

Client verification is enabled by default with `server.crt`.

Optional check:
```bash
openssl s_client -connect localhost:9999 -CAfile server.crt
```

## 7. Stop Services

```bash
docker-compose down
```
