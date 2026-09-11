# `raw/` — vanilla Kubernetes on your laptop (kind)

Pure, vendor-neutral Kubernetes. No cloud account, no bill. This is the best
place to *learn* — every concept from [`../README.md`](../README.md) is
demonstrable here in a few minutes.

## What you get

The [guestbook app](../app) (FastAPI + Swagger UI) and **MongoDB**, deployed as:

```
guestbook namespace
├── ResourceQuota + LimitRange         (governance)
├── MongoDB StatefulSet + headless Service + PVC   (stateful storage)
├── guestbook Deployment (2 replicas)  (stateless compute)
│   ├── ConfigMap + Secret             (config)
│   ├── liveness / readiness / startup probes
│   └── Service (ClusterIP)            (stable VIP)
├── Ingress (ingress-nginx)            (L7 entry → http://guestbook.localdev.me)
├── HorizontalPodAutoscaler + PodDisruptionBudget
├── NetworkPolicies                    (default-deny + allows)
└── Job (seed) + CronJob (counter)     (batch)
```

## Prerequisites

| Tool | Install |
|---|---|
| Docker | https://docs.docker.com/get-docker/ (daemon must be running) |
| kind | `go install sigs.k8s.io/kind@latest` or https://kind.sigs.k8s.io/ |
| kubectl | https://kubernetes.io/docs/tasks/tools/ |
| make | usually preinstalled on Linux/macOS |

Verify: `docker info`, `kind version`, `kubectl version --client`.

## Quick start (one command)

```bash
cd k8s/raw
make up
```

`make up` will: create a 3-node kind cluster → install ingress-nginx → build the
app image and load it into the cluster → `kubectl apply -k .` → wait for rollout
→ run the seed Job. Then open:

- **App / Swagger UI:** http://guestbook.localdev.me/docs
- (`localdev.me` and its subdomains resolve to `127.0.0.1` via public DNS, so no
  `/etc/hosts` edit is needed. The kind config maps host ports 80/443 in.)

Try it:
```bash
curl -s http://guestbook.localdev.me/api/info        # which Pod answered?
curl -s -X POST http://guestbook.localdev.me/api/messages \
     -H 'content-type: application/json' \
     -d '{"author":"you","text":"hello k8s"}'
curl -s http://guestbook.localdev.me/api/messages
```

## Step-by-step (what `make up` does, manually)

```bash
# 1) Cluster
kind create cluster --name guestbook --config kind-cluster.yaml
kubectl cluster-info --context kind-guestbook

# 2) Ingress controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=180s

# 3) Build the image and load it into kind (no registry needed)
docker build -t guestbook:1.0.0 ../app
kind load docker-image guestbook:1.0.0 --name guestbook

# 4) Deploy everything (Kustomize)
kubectl apply -k .
kubectl -n guestbook rollout status deploy/guestbook
```

## Things to actually try (the concepts, made visible)

**Self-healing** — delete a Pod and watch it come back:
```bash
kubectl -n guestbook delete pod -l app.kubernetes.io/name=guestbook --wait=false
kubectl -n guestbook get pods -w
```

**Load-balancing across replicas** — `served_by` changes between Pods:
```bash
for i in $(seq 10); do curl -s http://guestbook.localdev.me/api/info | grep -o '"pod":"[^"]*"'; done
```

**Manual scaling**, then **autoscaling**:
```bash
kubectl -n guestbook scale deploy/guestbook --replicas=5
# Enable metrics for the HPA, then generate load:
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
make load            # in one terminal
kubectl -n guestbook get hpa -w     # in another — watch replicas climb
```

**Readiness in action** — scale Mongo to 0 and watch app Pods go *NotReady*
(but NOT restart), then recover:
```bash
kubectl -n guestbook scale statefulset/mongo --replicas=0
kubectl -n guestbook get pods -w        # guestbook pods become 0/1 Ready
kubectl -n guestbook scale statefulset/mongo --replicas=1
```

**Persistence / stable storage** — data survives a Mongo Pod restart because the
PVC is re-attached:
```bash
kubectl -n guestbook delete pod mongo-0
kubectl -n guestbook get pvc           # the PVC (and your messages) remain
```

**Config without rebuilds** — edit the ConfigMap and roll:
```bash
kubectl -n guestbook edit configmap app-config   # change APP_VERSION
kubectl -n guestbook rollout restart deploy/guestbook
```

**Batch** — re-run the seed Job and inspect the CronJob:
```bash
kubectl -n guestbook create job --from=cronjob/count-messages count-now
kubectl -n guestbook logs job/count-now
```

## Inspecting & debugging

```bash
kubectl -n guestbook get all                 # everything at a glance
kubectl -n guestbook describe deploy guestbook
kubectl -n guestbook logs -l app.kubernetes.io/name=guestbook -f
kubectl -n guestbook exec -it mongo-0 -- mongosh -u root -p example-change-me
kubectl -n guestbook port-forward svc/guestbook 8080:80   # bypass the Ingress
```

## Teardown

```bash
make down        # or: kind delete cluster --name guestbook
```

## Notes / caveats

- **NetworkPolicies are not enforced by kind's default CNI** (kindnet). They are
  included to teach the pattern and *are* enforced on EKS/GKE. To enforce
  locally, recreate the cluster with Calico/Cilium.
- The MongoDB Secret uses a throwaway password for the demo — never commit real
  credentials. See [`../eks`](../eks) / [`../gke`](../gke) for keyless,
  cloud-IAM-based secret handling.
- `make load` triggers the HPA only after the **metrics-server** is installed
  (the snippet above patches it for kind's self-signed kubelet certs).
