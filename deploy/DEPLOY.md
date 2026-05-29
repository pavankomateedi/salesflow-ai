# Deploying SalesFlow AI

One Docker image serves everything: the React SPA (`/`, `/voice`, `/dashboard`),
the JSON APIs (`/api/*`), and the voice WebSocket (`/ws/voice`). The conversation
engine runs with **no keys**; set `OPENAI_API_KEY` (phrasing) and
`CARTESIA_API_KEY` (live voice) as environment variables to upgrade.

Build locally to verify:

```bash
docker build -t salesflow-ai .
docker run -p 8000:8000 salesflow-ai      # http://localhost:8000
```

## Render (simplest — blueprint in repo)

`render.yaml` is at the repo root. Render → New + → Blueprint → pick the repo →
Apply. Render builds the Dockerfile and assigns a public `https://…onrender.com`.

## GCP Cloud Run

Cloud Build auto-detects the repo `Dockerfile`:

```bash
gcloud run deploy salesflow-ai \
  --source . --region us-central1 --allow-unauthenticated --port 8000
```

Set secrets with `--set-env-vars OPENAI_API_KEY=...,CARTESIA_API_KEY=...`
(or, preferred, `--set-secrets` backed by Secret Manager). A Knative manifest is
in `deploy/cloudrun.service.yaml` for `gcloud run services replace`.

## AWS App Runner (from a container image)

```bash
# 1) build + push to ECR
aws ecr create-repository --repository-name salesflow-ai
docker build -t salesflow-ai .
docker tag salesflow-ai:latest ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/salesflow-ai:latest
aws ecr get-login-password --region REGION | docker login --username AWS \
  --password-stdin ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com
docker push ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/salesflow-ai:latest

# 2) create the service (edit ACCOUNT_ID/REGION in the JSON first)
aws apprunner create-service --cli-input-json file://deploy/apprunner-service.json
```

App Runner health-checks `/healthz` and injects `PORT` (the app honours it).
For AWS Elastic Beanstalk or ECS Fargate, point them at the same image; the
container listens on `$PORT` (default 8000).

## WebSocket note

The voice loop uses `/ws/voice`. Render, Cloud Run, and App Runner all support
WebSockets with no extra config. Behind a custom Nginx/ALB, allow HTTP/1.1
`Upgrade`/`Connection` headers on that path.
