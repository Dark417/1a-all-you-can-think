# `app/` — the Guestbook service

A deliberately small, **12-factor**, cloud-native FastAPI service used as the
single workload deployed by [`raw/`](../raw), [`eks/`](../eks) and
[`gke/`](../gke). It stores `messages` in MongoDB and serves Swagger UI at
`/docs`.

## Why it's shaped this way (it's a teaching prop)

| Property | Why it matters for Kubernetes |
|---|---|
| Config from **env vars** | Injected by ConfigMaps/Secrets — no rebuilds to reconfigure |
| **Stateless** (state in Mongo) | Run N replicas, scale freely, Pods are disposable |
| Separate **`/healthz`** (liveness) & **`/readyz`** (readiness) | Lets Kubernetes restart vs. depool correctly (see top-level README §4) |
| Reports **`POD_NAME`** via Downward API | Makes load-balancing & self-healing *visible* (`/api/info`) |
| **Non-root**, read-only rootfs | Satisfies the `restricted` Pod Security Standard |
| Logs to **stdout** | The container-native logging contract |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness — process is up (no deps) |
| GET | `/readyz` | Readiness — can reach MongoDB |
| GET | `/api/messages` | List messages |
| POST | `/api/messages` | Add a message `{author, text}` |
| GET | `/api/info` | Which Pod / version served you |
| GET | `/docs` | Swagger UI |

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `MONGODB_URI` | `mongodb://localhost:27017` | Connection string (from a Secret in k8s) |
| `MONGODB_DB` | `guestbook` | Database name (from a ConfigMap) |
| `APP_VERSION` | `1.0.0` | Reported by `/api/info` |
| `POD_NAME` | hostname | Injected via the Downward API in k8s |

## Run it locally without Kubernetes

```bash
cd k8s/app
pip install -r requirements.txt
# Point at any MongoDB (e.g. the one in ../../mongodb/docker-compose.yml):
export MONGODB_URI="mongodb://localhost:27017"
uvicorn main:app --reload
# open http://localhost:8000/docs
```

## Build the image

```bash
docker build -t guestbook:1.0.0 .
```

The same image is loaded into kind locally, and pushed to **ECR** (EKS) or
**Artifact Registry** (GKE) in the cloud overlays.
