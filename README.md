# Lambda API Gateway WebSocket Broadcast Chat

This project deploys a Python 3.12 WebSocket broadcast-chat prototype using API Gateway WebSocket APIs, Lambda, DynamoDB, and AWS Lambda Powertools.

## Architecture

- `$connect` records a client connection ID in DynamoDB.
- `$disconnect` removes the connection ID.
- `sendmessage` broadcasts a client message to every connected client.
- `$default` rejects unsupported actions without closing the connection.
- Stale client IDs reported by the API Gateway Management API are removed during broadcast.

## Prerequisites

- Node.js and npm
- Python 3.12
- AWS CLI
- `osls` available on `PATH`
- AWS credentials in the local `.env` file

Install dependencies:

```bash
npm ci
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## Local Checks

```bash
.venv/bin/ruff check .
.venv/bin/mypy app
.venv/bin/pytest
npm run build:dependencies
osls print --stage dev --region us-east-1
osls package --stage dev --region us-east-1
```

## Deploy

Load credentials without printing them, then verify the AWS account:

```bash
set -a
. ./.env
set +a
aws sts get-caller-identity
npm run build:dependencies
osls deploy --stage dev --region us-east-1
```

The deployment output includes `WebSocketEndpoint`. It has the form:

```text
wss://<api-id>.execute-api.<region>.amazonaws.com/dev
```

## Smoke Test

### Browser Client

Open `client/index.html` in two browser tabs. Paste the `WebSocketEndpoint` output into each tab and connect. Send a message from either tab to verify that both receive the broadcast.

The endpoint can also be provided in the URL:

```text
client/index.html?endpoint=wss://<api-id>.execute-api.<region>.amazonaws.com/dev
```

### wscat

Open two terminals and connect each client:

```bash
npx wscat -c "$WEBSOCKET_ENDPOINT"
```

In either client, send:

```json
{"action":"sendmessage","message":"hello from client one"}
```

Both clients receive:

```json
{"message":"hello from client one","senderConnectionId":"<connection-id>"}
```

Close one client and send another message from the remaining client. The disconnected ID is removed by `$disconnect`; a connection that has already gone stale is also removed during broadcast.

## Debugging

Use the deployed stack and CloudWatch logs to diagnose failures:

```bash
osls info --stage dev --region us-east-1
osls logs --function sendMessage --stage dev --region us-east-1
```

Do not print, commit, or package `.env`.

## Remove

Remove the stack when it is no longer required:

```bash
osls remove --stage dev --region us-east-1
```
