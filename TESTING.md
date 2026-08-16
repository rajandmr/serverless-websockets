# Testing Guide

Step-by-step guide to test this project end to end: local checks, deploy to
AWS, live WebSocket testing against the deployed stack, and cleanup.

Expect the whole run to take ~15–20 minutes, most of it waiting on deploys.

## 1. Prerequisites

- Node.js + npm — runs the `osls` framework and `wscat`
- `uv` — Python toolchain for the local checks
- AWS CLI v2
- AWS credentials for a throwaway-capable account in `.env` at the repo root
  (git-ignored), in the form:

  ```bash
  AWS_REGION=us-east-1
  AWS_ACCESS_KEY_ID=...
  AWS_SECRET_ACCESS_KEY=...
  ```

Load them into your shell and confirm they point where you expect:

```bash
set -a; source .env; set +a
aws sts get-caller-identity
```

## 2. Local checks (before deploying)

```bash
npm ci
uv sync

npm test               # uv run pytest — unit tests
npm run lint           # uv run ruff check .
npm run typecheck      # uv run mypy functions utils
npx osls print         # rendered serverless config parses
```

All four must pass before spending deploy time.

## 3. Deploy

```bash
npx osls deploy
```

On success it prints the WebSocket endpoint, e.g.
`wss://<api-id>.execute-api.us-east-1.amazonaws.com/dev`.

Collect the values the later steps need — fill these in once, the rest of
the guide reuses them:

```bash
export STAGE=dev
export WEBSOCKET_ENDPOINT=wss://<api-id>.execute-api.us-east-1.amazonaws.com/dev
export USER_POOL_ID=us-east-1_...
export USER_POOL_CLIENT_ID=...
export CONNECTIONS_TABLE=lambda-apigw-sockets-dev-connections
```

`USER_POOL_ID` and `USER_POOL_CLIENT_ID` come from the stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name lambda-apigw-sockets-$STAGE \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId` || OutputKey==`UserPoolClientId`].[OutputKey,OutputValue]' \
  --output table
```

## 4. Create test users and get tokens

Two users, so one can message the other:

```bash
create_user () {
  aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$1" \
    --user-attributes Name=email,Value="$1" Name=email_verified,Value=true \
    --temporary-password 'Wsocks-Test-2026!' \
    --message-action SUPPRESS

  aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$1" \
    --password 'Wsocks-Test-2026!' \
    --permanent
}

create_user ws-test-alice@example.com
create_user ws-test-bob@example.com
```

Sign in and keep the **access tokens** — not ID tokens: the authorizer calls
`cognito-idp:GetUser`, which requires an access token. Tokens expire after
one hour.

Note the user pool client deliberately allows only the public auth flows, so
`admin-initiate-auth` fails with "Auth flow not enabled" — use the public
password flow:

```bash
get_token () {
  aws cognito-idp initiate-auth \
    --client-id "$USER_POOL_CLIENT_ID" \
    --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters USERNAME=$1,PASSWORD='Wsocks-Test-2026!' \
    --query 'AuthenticationResult.AccessToken' \
    --output text
}

export ALICE_TOKEN=$(get_token ws-test-alice@example.com)
export BOB_TOKEN=$(get_token ws-test-bob@example.com)
```

## 5. Live WebSocket tests

Open **three terminals** (all with the exported variables from above):
terminal B for Bob, terminal A for Alice, terminal C for AWS CLI checks.

> **What to expect on the wire:** only *recipients* receive frames. API
> Gateway WebSockets never delivers a route handler's return value to the
> client that sent the message, so the sender's socket stays silent after a
> send — success, validation errors, and unknown actions are all verified
> from the Lambda logs (section 6) or by what the recipient receives.

### T1 — invalid token is rejected

```bash
# terminal B
npx wscat -c "$WEBSOCKET_ENDPOINT?token=not-a-real-token"
```

Expected: wscat exits immediately with `unexpected server response (403)`.
The `cognitoAuthorizer` denied the connect; the `connect` Lambda never ran.

### T2 — both users connect

```bash
# terminal B
npx wscat -c "$WEBSOCKET_ENDPOINT?token=$BOB_TOKEN"

# terminal A
npx wscat -c "$WEBSOCKET_ENDPOINT?token=$ALICE_TOKEN"
```

Expected: both print `Connected (press CTRL+C to quit)` and stay open.

### T3 — connections are registered in DynamoDB

```bash
# terminal C
aws dynamodb scan --table-name "$CONNECTIONS_TABLE" \
  --query 'Items[].[connectionId.S,email.S]' --output text
```

Expected: two rows — one per user, each carrying the verified email the
authorizer put in the context.

### T4 — Alice messages Bob (happy path)

```javascript
// terminal A
{"action":"sendmessage","recipientEmail":"ws-test-bob@example.com","message":"hello from alice"}
```

Expected:

- **Terminal B** (Bob) receives the message:

  ```json
  {"message":"hello from alice","senderConnectionId":"<alice-connection-id>"}
  ```

- **Terminal A** (Alice) receives nothing — that is correct, not a failure
  (see the note above). Confirm the send in the logs (section 6): the
  `sendMessage` function logs `"message":"Delivered WebSocket message"` with
  `"delivered":1`.

### T5 — multi-connection delivery (same user, two sockets)

Connect a second wscat for Bob in terminal C
(`npx wscat -c "$WEBSOCKET_ENDPOINT?token=$BOB_TOKEN"`), then resend T4's
message from Alice.

Expected: **both** of Bob's sockets receive the message, and the
`sendMessage` log shows `"delivered":2`. Close the extra Bob socket (Ctrl+C)
after this check.

### T6 — invalid payload is rejected

```javascript
// terminal A
{"action":"sendmessage","recipientEmail":"ws-test-bob@example.com","message":"   "}
```

Expected: Bob receives nothing, and Alice's socket stays silent. In the
`sendMessage` logs the invocation appears (Powertools logs the incoming
event) but has **no** `"Delivered WebSocket message"` line — the pydantic
validation rejected the blank message before any delivery.

Other bodies that behave the same way: missing `recipientEmail`, malformed
email, non-string `message`, non-JSON body.

### T7 — unknown action falls through to $default

```javascript
// terminal A
{"action":"bogus","foo":"bar"}
```

Expected: nothing on either socket, connection stays open (resend T4 to
confirm). Verify in the `default` function's logs: one invocation with
`"routeKey":"$default"`.

### T8 — offline recipient is a graceful no-op

```javascript
// terminal A
{"action":"sendmessage","recipientEmail":"ws-test-nobody@example.com","message":"anyone there?"}
```

Expected: no frames anywhere, no errors. The `sendMessage` log shows
`"Delivered WebSocket message"` with `"delivered":0`.

### T9 — disconnect cleans up DynamoDB

Close Bob's socket (Ctrl+C in terminal B), wait a couple of seconds, then:

```bash
# terminal C
aws dynamodb scan --table-name "$CONNECTIONS_TABLE" \
  --query 'Items[].[connectionId.S,email.S]' --output text
```

Expected: only Alice's row remains (the `disconnect` Lambda also logs
`"WebSocket client disconnected"` with the removed `connection_id`). Close
Alice's socket and rescan — the table is now empty.

## 6. Checking Lambda logs

```bash
npx osls logs --function sendMessage --tail
npx osls logs --function cognitoAuthorizer --tail
npx osls logs --function default --tail
npx osls logs --function disconnect --tail
```

Useful Powertools fields: `cold_start`, `delivered` (per-send delivery
count), `email` (who connected), `connection_id`. For T1 the authorizer logs
a WARNING `"Rejected WebSocket connect: missing or invalid Cognito access
token"`.

Or filter recent events directly:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/lambda-apigw-sockets-$STAGE-sendMessage \
  --start-time $(( ($(date +%s) - 900) * 1000 )) \
  --filter-pattern '"Delivered WebSocket message"' \
  --query 'events[].message' --output text
```

## 7. Optional: browser client

Open `client/index.html` and paste the full endpoint **including** the token
into the endpoint box (browsers tend to drop a second `?` from the URL
query, so passing it via `?endpoint=...?token=...` may not survive):

```text
wss://<api-id>.execute-api.us-east-1.amazonaws.com/dev?token=<AccessToken>
```

Connect two tabs with the two users' tokens and repeat T4–T8 through the UI.

## 8. Cleanup

Delete the test users and the stack:

```bash
for U in ws-test-alice@example.com ws-test-bob@example.com; do
  aws cognito-idp admin-delete-user --user-pool-id "$USER_POOL_ID" --username "$U"
done

npx osls remove   # prompts for confirmation
```

`osls remove` does not delete the CloudWatch log groups; drop them manually
for a spotless account:

```bash
for FG in CognitoAuthorizer Connect Disconnect SendMessage Default; do
  aws logs delete-log-group --log-group-name /aws/lambda/lambda-apigw-sockets-$STAGE-$FG
done
```

## Quick reference — expected observable behavior

| Client action | Immediately observable |
| --- | --- |
| Connect with bad/missing token | Handshake rejected, HTTP 403 |
| Valid connect | Item appears in `ConnectionsTable` (connectionId + email) |
| `sendmessage` (as recipient) | Frame: `{"message":<text>,"senderConnectionId":<id>}` |
| `sendmessage` (as sender) | Nothing on the socket; `"delivered":N` in `sendMessage` logs |
| `sendmessage` with invalid body | Nothing anywhere; no `Delivered` log line for that invocation |
| Unknown `action` | Nothing anywhere; one `$default` invocation in logs |
| Disconnect | Connection row removed from `ConnectionsTable` |
