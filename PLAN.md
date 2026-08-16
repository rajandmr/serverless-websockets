# Implementation Plan

## Goal

Build and deploy a Python 3.12 WebSocket broadcast-chat prototype using AWS API Gateway WebSocket APIs, AWS Lambda, DynamoDB, AWS Lambda Powertools, and the available `osls` Serverless-compatible CLI. Follow the layout and deployment conventions from `../ecs-fargate-spot`.

Deploy with `osls` using credentials loaded from `.env`, smoke-test the deployed `dev` stack, debug failures, and leave the working stack deployed.

## Architecture

```text
WebSocket clients
  -> API Gateway WebSocket API
     -> $connect Lambda
     -> $disconnect Lambda
     -> sendmessage Lambda
     -> $default Lambda

Lambda handlers
  -> DynamoDB connections table
  -> API Gateway Management API
  -> CloudWatch Logs
```

API Gateway selects routes from `$request.body.action`. Clients send `{"action":"sendmessage","message":"hello"}`. The message handler broadcasts a JSON payload to every stored connection and deletes stale connections reported by the management API.

Authentication is intentionally out of scope for this prototype.

## Structure

```text
app/
  __init__.py
  main.py
resources/
  dynamodb.yml
tests/
  test_main.py
.gitignore
package.json
package-lock.json
pyproject.toml
requirements.txt
requirements-dev.txt
README.md
serverless.yml
```

Keep the application compact in `app/main.py` and place supporting CloudFormation resources in `resources/`.

## Work

1. Pin project dependencies and development tooling. Configure Ruff, mypy, and pytest. Build production dependencies into a package-only `.requirements` directory.
2. Define a Serverless WebSocket API with `$connect`, `$disconnect`, `sendmessage`, and `$default` routes. Use stage-qualified naming, Python 3.12, and least-privilege DynamoDB and API Gateway Management API permissions.
3. Create an on-demand DynamoDB table keyed by `connectionId`.
4. Implement Powertools-typed handlers: connect persists a connection, disconnect removes it, sendmessage validates and broadcasts messages, removes stale connections, and default rejects unsupported actions.
5. Add unit tests for lifecycle storage, validation, fanout, stale-connection cleanup, and route fallback.
6. Document prerequisites, `.env` credential loading, deployment, two-client `wscat` testing, logs, and cleanup.
7. Run linting, typing, tests, Serverless configuration inspection, and packaging.
8. Load `.env` without exposing it, verify AWS identity, deploy with `osls`, connect two WebSocket clients, verify broadcast and cleanup behavior, and use Serverless/CloudWatch diagnostics to resolve any failures.

## Completion Criteria

- Local lint, type, test, and packaging checks pass.
- The `dev` stack deploys with credentials from `.env`.
- Two active clients receive each broadcast message.
- Disconnects and stale send targets are removed from DynamoDB.
- Logs provide structured operational context.
- The README accurately documents deployment and smoke testing.
- The working `dev` stack remains deployed.
