# Lambda API Gateway WebSocket Chat

This project deploys a Python 3.12 WebSocket chat prototype using an API Gateway WebSocket API, Lambda, DynamoDB, Cognito, and AWS Lambda Powertools. Connections are authenticated with a Cognito access token, a single user (email) may have several open connections at once (multiple tabs/devices), and messages are delivered to every connection open for a target recipient email.

## What this deploys

```text
client (with a Cognito access token)
  |
  | $connect?token=<AccessToken>
  v
cognitoAuthorizer Lambda  (verifies the token via cognito-idp:GetUser, denies if invalid)
  |
  v
API Gateway WebSocket API
  |
  +--> connect Lambda      (stores connectionId + the token's verified email in DynamoDB)
  +--> disconnect Lambda   (removes connectionId from DynamoDB)
  +--> sendMessage Lambda  (validates {recipientEmail, message}, queries ConnectionsTable's
  |                         EmailIndex for every connection of that recipient, delivers via
  |                         apigatewaymanagementapi, prunes stale connections)
  +--> default Lambda      (rejects unsupported actions)
       |
       v
   ConnectionsTable (DynamoDB, GSI: EmailIndex)
```

## Prerequisites

- An AWS account with credentials configured locally and permission to create CloudFormation, API Gateway, Lambda, IAM, DynamoDB, and Cognito resources.
- Node.js and npm, used to run the `osls` Framework v4.
- Python 3.12. This is the deployed Lambda runtime; `boto3` is available in the AWS Python runtime.
- **AWS Lambda Powertools** is supplied to every function at runtime by its public Lambda Layer (attached in `serverless.yml` via an `${ssm:...}` variable, so it always resolves to the latest python3.12 x86_64 version). **`pydantic`** (used by `sendMessage` for request validation) is supplied the same way, since Powertools bundles it. Both are installed locally as **dev-only** dependencies through `uv sync` for editor type hints and tests; nothing is bundled into the deployment package.

Confirm that the AWS credentials and target region are the ones you expect:

```bash
aws sts get-caller-identity
aws configure get region
```

## Quick start

1. Install the development environment:

   ```bash
   npm ci
   uv sync
   ```

2. Deploy the stack:

   ```bash
   npx osls deploy
   ```

3. Get the deployed WebSocket endpoint and Cognito IDs:

   ```bash
   npx osls info --verbose
   ```

   Note the `WebSocketEndpoint`, `UserPoolId`, and `UserPoolClientId` outputs.

4. Create a Cognito user and confirm it:

   ```bash
   aws cognito-idp sign-up \
     --client-id "$USER_POOL_CLIENT_ID" \
     --username user@example.com \
     --password 'Str0ngPass!23'

   aws cognito-idp admin-confirm-sign-up \
     --user-pool-id "$USER_POOL_ID" \
     --username user@example.com
   ```

5. Sign in to get an access token:

   ```bash
   aws cognito-idp initiate-auth \
     --client-id "$USER_POOL_CLIENT_ID" \
     --auth-flow USER_PASSWORD_AUTH \
     --auth-parameters USERNAME=user@example.com,PASSWORD='Str0ngPass!23'
   ```

   Copy `AuthenticationResult.AccessToken` from the response — **the access token, not the ID token**, since the authorizer calls `cognito-idp:GetUser`, which requires an access token.

6. Connect with the token as a query-string parameter (repeat for a second user, or a second connection for the same user, to see multi-connection delivery):

   ```bash
   npx wscat -c "$WEBSOCKET_ENDPOINT?token=$ACCESS_TOKEN"
   ```

   A connect attempt with a missing or invalid token is rejected by the `cognitoAuthorizer` before it ever reaches the `connect` Lambda.

   Or smoke test with the browser client, passing the token in the URL:

   ```text
   client/index.html?endpoint=wss://<api-id>.execute-api.<region>.amazonaws.com/dev?token=<AccessToken>
   ```

7. Send a message targeted at a recipient's email — it is delivered to every connection open for that email:

   ```json
   {"action":"sendmessage","recipientEmail":"user@example.com","message":"hello from client one"}
   ```

   Each of the recipient's open connections receives:

   ```json
   {"message":"hello from client one","senderConnectionId":"<connection-id>"}
   ```

## How it works

`functions/index.yml` defines the Lambda functions and their WebSocket route triggers:

| Function | Route | Purpose |
| --- | --- | --- |
| `cognitoAuthorizer` | authorizer on `$connect` | Verifies the `token` query-string parameter via `cognito-idp:GetUser`; allows the connection and passes the verified `email` into the authorizer context, or denies it. |
| `connect` | `$connect` | Reads the verified `email` from the authorizer context and stores it with `connectionId` in `ConnectionsTable`. |
| `disconnect` | `$disconnect` | Removes `connectionId` from `ConnectionsTable`. |
| `sendMessage` | `sendmessage` | Validates `{recipientEmail, message}`, queries `ConnectionsTable`'s `EmailIndex` for every connection belonging to `recipientEmail`, and delivers to each via the API Gateway Management API. A delivery failure to one connection does not block delivery to the rest; a `GoneException` prunes that connection from the table. |
| `default` | `$default` | Rejects unsupported actions without closing the connection. |

`resources/dynamodb.yml` defines `ConnectionsTable` (on-demand, hash key `connectionId`, GSI `EmailIndex` on `email`) and two least-privilege IAM roles: `ConnectionLifecycleRole` (`PutItem`/`DeleteItem`, used by `connect`/`disconnect`/`default`) and `BroadcastRole` (`Query`/`DeleteItem` plus `execute-api:ManageConnections` scoped to this WebSocket API, used by `sendMessage`).

`resources/cognito.yml` defines the `UserPool` (email as the username, auto-verified), `UserPoolClient` (no client secret, since browser clients can't store one), and `CognitoAuthorizerRole` (`cognito-idp:GetUser` scoped to the user pool).

Shared helpers live in `utils/helper.py`: `connections_table()`, `management_client(event)`, and `response(status_code, body)`.

## Local checks

```bash
uv run pytest
uv run ruff check .
uv run mypy functions utils
npx osls print
```

## Debugging

```bash
npx osls info --verbose
npx osls logs --function sendMessage --tail
npx osls logs --function cognitoAuthorizer --tail
```

## Remove

Remove the stack when it is no longer required:

```bash
npx osls remove
```

## Project layout

```text
functions/
  index.yml         Lambda, WebSocket route, and authorizer wiring
  authorizer.py     $connect Lambda REQUEST authorizer (verifies a Cognito access token)
  connect.py        $connect handler
  disconnect.py     $disconnect handler
  send_message.py   sendmessage handler
  default.py        $default handler
resources/
  dynamodb.yml       ConnectionsTable (+ EmailIndex GSI) and per-function IAM roles
  cognito.yml        Cognito User Pool, User Pool Client, and the authorizer's IAM role
utils/helper.py       Shared DynamoDB/API Gateway/response helpers
serverless.yml        Service, runtime, IAM layer, packaging, and resource configuration
```
