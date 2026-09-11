# One-command local Kubernetes demo on kind.
# Prereqs: docker, kind, kubectl. (Install: https://kind.sigs.k8s.io/)
#
#   make up        # create cluster + ingress + build/load image + deploy + seed
#   make open      # print the URL to visit
#   make logs      # tail the app logs
#   make scale N=5 # change replica count by hand
#   make load      # hammer the app so the HPA scales it up
#   make down      # delete the whole cluster

CLUSTER ?= guestbook
IMAGE   ?= guestbook:1.0.0
NS      ?= guestbook
APP_DIR ?= ../app

.PHONY: up cluster ingress image deploy seed open logs scale load status down

up: cluster ingress image deploy seed status
	@echo ""
	@echo ">>> Done. Add an entry only if your DNS blocks it; localdev.me already points to 127.0.0.1."
	@echo ">>> Visit: http://guestbook.localdev.me/docs"

cluster:
	kind create cluster --name $(CLUSTER) --config kind-cluster.yaml

ingress:
	kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
	kubectl -n ingress-nginx wait --for=condition=ready pod \
		--selector=app.kubernetes.io/component=controller --timeout=180s

image:
	docker build -t $(IMAGE) $(APP_DIR)
	kind load docker-image $(IMAGE) --name $(CLUSTER)

deploy:
	kubectl apply -k .
	kubectl -n $(NS) rollout status deploy/guestbook --timeout=180s

seed:
	# (the seed Job is part of the kustomization; this re-runs it on demand)
	-kubectl -n $(NS) delete job seed-guestbook --ignore-not-found
	kubectl -n $(NS) apply -f 40-jobs.yaml

open:
	@echo "http://guestbook.localdev.me/docs"

logs:
	kubectl -n $(NS) logs -l app.kubernetes.io/name=guestbook -f --tail=100

scale:
	kubectl -n $(NS) scale deploy/guestbook --replicas=$(N)

# Generate load to trigger the HorizontalPodAutoscaler.
load:
	kubectl -n $(NS) run loadgen --rm -it --restart=Never --image=busybox -- \
		/bin/sh -c "while true; do wget -q -O- http://guestbook.$(NS).svc.cluster.local/api/info; done"

status:
	kubectl -n $(NS) get pods,svc,ingress,hpa

down:
	kind delete cluster --name $(CLUSTER)
