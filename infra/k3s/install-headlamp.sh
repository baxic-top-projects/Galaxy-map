#!/usr/bin/env bash
set -euo pipefail

kubectl create namespace headlamp --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/headlamp/main/kubernetes/headlamp-deployment.yaml

# Wait a bit for the service object from the manifest
for _ in $(seq 1 30); do
  kubectl -n headlamp get svc headlamp >/dev/null 2>&1 && break
  sleep 2
done

kubectl -n headlamp patch svc headlamp --type='json' -p='[
  {"op":"replace","path":"/spec/type","value":"NodePort"},
  {"op":"replace","path":"/spec/ports/0/nodePort","value":30446}
]' || kubectl -n headlamp patch svc headlamp -p '{"spec":{"type":"NodePort"}}'

# Ensure nodePort is 30446 if patch above only set type
NODE_PORT="$(kubectl -n headlamp get svc headlamp -o jsonpath='{.spec.ports[0].nodePort}')"
echo "Headlamp NodePort=${NODE_PORT}"
kubectl -n headlamp get svc,pods -o wide

# Admin service account token for first login
kubectl -n headlamp create serviceaccount headlamp-admin --dry-run=client -o yaml | kubectl apply -f -
kubectl create clusterrolebinding headlamp-admin \
  --clusterrole=cluster-admin \
  --serviceaccount=headlamp:headlamp-admin \
  --dry-run=client -o yaml | kubectl apply -f -

# Token (K8s >=1.24)
kubectl -n headlamp create token headlamp-admin --duration=8760h > /tmp/headlamp-admin.token
echo "Token saved to /tmp/headlamp-admin.token"
wc -c /tmp/headlamp-admin.token
