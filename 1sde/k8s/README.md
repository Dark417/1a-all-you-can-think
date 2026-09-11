# Kubernetes, explained — with three runnable versions of one app

This module teaches Kubernetes by deploying **one identical application** — a
tiny [FastAPI guestbook](./app) backed by **MongoDB** — three ways:

| Folder | Target | What it shows |
|---|---|---|
| [`raw/`](./raw) | **Local** cluster ([kind](https://kind.sigs.k8s.io/)) | Pure, vendor-neutral Kubernetes. Run it on your laptop in minutes. |
| [`eks/`](./eks) | **AWS** Elastic Kubernetes Service | The same app on a managed cloud cluster (ALB, EBS CSI, IRSA, ECR). |
| [`gke/`](./gke) | **GCP** Google Kubernetes Engine | The same app on GKE (GCE Ingress, PD CSI, Workload Identity, Autopilot). |

`eks/` and `gke/` are **Kustomize overlays** of `raw/` — they reuse the exact
same manifests and only *patch* the few cloud-specific bits. That is the whole
point of Kubernetes: **write once, run on any conformant cluster.**

> The database side is explored in depth in [`../mongodb`](../mongodb).

---

## 1. What problem does Kubernetes solve?

You have containers (immutable, portable process bundles). In production you need
to run *many* of them across *many* machines and keep them healthy: restart
crashes, reschedule when a node dies, roll out new versions without downtime,
scale with load, give them stable network names, wire in config and secrets, and
attach storage. Doing this by hand does not scale.

**Kubernetes is a cluster operating system.** You describe the *desired state*
("I want 3 replicas of this image, reachable here, with this config") as
declarative YAML, and Kubernetes' **controllers** continuously reconcile reality
toward that state. You stop managing servers and start managing *intent*.

---

## 2. Cluster anatomy

A cluster = a **control plane** + a set of **worker nodes**.

### Control plane (the brain)
- **kube-apiserver** — the front door. Every change goes through its REST API;
  `kubectl` just talks to it. It validates and persists objects.
- **etcd** — the consistent key-value store that holds *all* cluster state. The
  single source of truth (back it up!).
- **kube-scheduler** — decides *which node* each new Pod runs on, based on
  resource requests, affinity, taints, topology spread, etc.
- **kube-controller-manager** — runs the control loops (Deployment, ReplicaSet,
  Job, Node, endpoints, …) that drive actual → desired.
- **cloud-controller-manager** — integrates with the cloud (provisions load
  balancers, disks, routes). On EKS/GKE this is managed *for* you.

### Worker nodes (the muscle)
- **kubelet** — the node agent; starts/stops containers and reports health.
- **container runtime** — containerd/CRI-O actually runs the containers.
- **kube-proxy** — programs node networking so Service virtual IPs work.
- **CNI plugin** — gives every Pod an IP (kindnet locally; VPC CNI on EKS;
  Dataplane V2/Cilium on GKE).

You declare intent at the apiserver → scheduler places Pods → kubelets run them →
controllers keep correcting drift. **Reconciliation** is the core idea.

---

## 3. The objects, grouped by what they do

Everything below appears in [`raw/`](./raw) — each manifest is heavily commented.

### Running workloads
- **Pod** — the smallest deployable unit: one or more co-located containers
  sharing a network namespace and volumes. You rarely create Pods directly.
- **ReplicaSet** — keeps *N* identical Pods running. Managed by a Deployment.
- **Deployment** — declarative updates for **stateless** apps: scaling, rolling
  updates, instant rollback. → our `guestbook` API runs as a Deployment.
- **StatefulSet** — for **stateful** apps needing stable identity + per-Pod
  storage: Pods are `mongo-0`, `mongo-1`, … and keep their own volume. → MongoDB.
- **DaemonSet** — one Pod per node (log shippers, node agents).
- **Job** — run-to-completion batch work (our DB seeder).
- **CronJob** — Jobs on a schedule (our periodic counter).

### Networking & exposure
- **Service** — a stable virtual IP + DNS name load-balancing across the *ready*
  Pods it selects. Types: `ClusterIP` (internal), `NodePort`, `LoadBalancer`
  (cloud L4), and *headless* (`clusterIP: None`, stable per-Pod DNS for
  StatefulSets).
- **Ingress** + **Ingress controller** — L7 HTTP routing (host/path → Service).
  The Ingress is rules; a controller (ingress-nginx locally, ALB on EKS, GCE LB
  on GKE) implements them.
- **Gateway API** — the modern successor to Ingress (more expressive, role-
  oriented). Shown as an alternative in the GKE overlay.
- **NetworkPolicy** — a Pod-level firewall (default-deny + explicit allows).
  Needs an enforcing CNI.

### Configuration & secrets
- **ConfigMap** — non-secret config injected as env vars or files. Decouples
  config from the image.
- **Secret** — same, for sensitive data (base64-encoded at rest in etcd; enable
  encryption-at-rest and/or an external secrets manager in production).
- **Downward API** — inject Pod metadata (e.g. `metadata.name`) as env vars. Our
  app uses it to report *which Pod* served you.

### Storage
- **PersistentVolume (PV)** — a piece of storage in the cluster.
- **PersistentVolumeClaim (PVC)** — a request for storage by a Pod.
- **StorageClass** — *dynamic* provisioning: a PVC referencing a StorageClass
  auto-creates a PV (an EBS volume on EKS, a Persistent Disk on GKE). MongoDB's
  StatefulSet uses a `volumeClaimTemplate` to get one PVC per replica.

### Identity, access & governance
- **Namespace** — a virtual cluster: a scope for names + a boundary for quotas,
  RBAC and NetworkPolicies. Everything here lives in `guestbook`.
- **ServiceAccount** — the identity a Pod runs as. On EKS/GKE it is linked to a
  cloud IAM role (**IRSA** / **Workload Identity**) so Pods reach cloud services
  with *no static credentials*.
- **RBAC** (Role/ClusterRole + RoleBinding/ClusterRoleBinding) — who can do what
  to which API objects.
- **ResourceQuota / LimitRange** — cap aggregate usage per namespace and set
  per-container defaults/bounds.
- **PodDisruptionBudget** — preserve availability during voluntary disruptions
  (node drains, upgrades).
- **Pod Security Standards** — the `restricted` profile (enforced via the
  namespace label) bans privileged/root containers.

---

## 4. The two concepts people get wrong

**Liveness vs readiness probes.** They look similar and do opposite things:

- **livenessProbe** answers *"is this process wedged?"* — on failure Kubernetes
  **restarts** the container. Keep it dependency-free (just `/healthz`).
- **readinessProbe** answers *"can I serve traffic right now?"* — on failure
  Kubernetes **removes the Pod from the Service** (no restart) until it passes.
  This one *should* check dependencies (our `/readyz` pings MongoDB).

Mixing them up causes restart storms (if liveness checks the DB and the DB
blips, every Pod restarts) — so the demo app deliberately separates them.

**Requests vs limits.** `requests` are what the scheduler reserves and what the
HPA measures against; `limits` are the hard ceiling (CPU throttled, memory →
OOMKill). Set both.

---

## 5. How a request flows in this demo

```
browser → Ingress controller (L7) → Service (stable VIP, picks a ready Pod)
        → guestbook Pod (FastAPI) → Service "mongo" (headless DNS)
        → mongo-0 Pod (StatefulSet) → its PersistentVolume
```

Scale the Deployment (`kubectl scale` or let the **HPA** do it) and the Service
spreads traffic across more Pods — hit `/api/info` repeatedly and watch
`served_by` change. Kill a Pod (`kubectl delete pod …`) and the Deployment
recreates it within seconds. That is reconciliation you can see.

---

## 6. Which version should I run?

- **Start with [`raw/`](./raw)** — zero cloud cost, 5 minutes, the real
  concepts. Everything above is demonstrable on your laptop.
- **Then [`eks/`](./eks) or [`gke/`](./gke)** — see how the *same manifests*
  gain a managed control plane, cloud load balancers, cloud disks, and
  keyless cloud IAM. The READMEs there list exactly what each cloud requires
  (accounts, CLIs, IAM, networking) and include teardown steps so you don't
  leave billable resources running.

> **Portability caveat:** ~90% is identical across all three. The deltas are
> exactly the things clouds do differently — Ingress implementation, StorageClass
> provisioner, Service `LoadBalancer` integration, and Pod→cloud IAM. The
> overlays isolate those deltas so you can see them at a glance.

---

## 7. Glossary cheat-sheet

| Term | One-liner |
|---|---|
| Reconciliation | Controllers continuously drive actual state → desired state |
| Pod | Smallest unit; 1+ containers sharing network + storage |
| Deployment | Stateless, scalable, rolling-updatable Pods |
| StatefulSet | Stable identity + per-Pod storage (databases) |
| Service | Stable VIP/DNS load-balancing ready Pods |
| Ingress / Gateway | L7 HTTP routing into the cluster |
| ConfigMap / Secret | Externalized config / sensitive config |
| PVC / StorageClass | Request storage / dynamically provision it |
| HPA | Autoscale replicas on metrics |
| Namespace | Scope + policy boundary |
| ServiceAccount + IRSA/WI | Pod identity, linked to cloud IAM |
| Kustomize overlay | Patch a shared base per environment |
```
