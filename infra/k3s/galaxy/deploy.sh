#!/usr/bin/env bash
set -eu
ROOT="${GALAXY_ROOT:-/home/baxic/Galaxy-map}"
# fallback paths
if [ ! -d "$ROOT" ]; then ROOT="/home/baxic/Documents/GitHub/Galaxy-map"; fi
if [ ! -d "$ROOT" ]; then
  # discover from running compose labels / common layout
  if [ -d /home/baxic/Galaxy-map ]; then ROOT=/home/baxic/Galaxy-map
  elif [ -d /home/baxic/Documents/GitHub/Galaxy-map ]; then ROOT=/home/baxic/Documents/GitHub/Galaxy-map
  else
    echo "Galaxy-map root not found" >&2
    ls /home/baxic || true
    exit 1
  fi
fi
echo "GALAXY_ROOT=$ROOT"
NS=galaxy

bash /tmp/k3s-import-images.sh \
  redis:7-alpine \
  apache/kafka:3.9.0 \
  maildev/maildev:3.0.0 \
  galaxy-map-catalog-service:latest \
  galaxy-map-auth-service:latest \
  galaxy-map-asset-service:latest \
  galaxy-map-storm-service:latest \
  galaxy-map-kafka-connect:latest \
  galaxy-map-api-gateway:latest \
  galaxy-map-client:latest

kubectl apply -f /tmp/k3s-galaxy/namespace.yaml

make_secret() {
  local name="$1"
  local file="$2"
  if [ -f "$file" ]; then
    kubectl -n "$NS" create secret generic "$name" --from-env-file="$file" --dry-run=client -o yaml | kubectl apply -f -
    echo "secret $name from $file"
  else
    echo "warn: missing $file (optional secret $name)"
  fi
}

make_secret galaxy-catalog-env "$ROOT/server/services/catalog-service/.env"
make_secret galaxy-auth-env "$ROOT/server/services/auth-service/.env"
make_secret galaxy-asset-env "$ROOT/server/services/asset-service/.env"
make_secret galaxy-storm-env "$ROOT/server/services/storm-service/.env"
make_secret galaxy-gateway-env "$ROOT/server/api-gateway/.env"
make_secret galaxy-kafka-connect-env "$ROOT/kafka-connect/.env"

echo "Stopping galaxy docker-compose services..."
cd "$ROOT"
docker-compose stop \
  client api-gateway storm-service asset-service catalog-service auth-service \
  smtp-service-galaxy redis kafka kafka-connect || true

kubectl apply -f /tmp/k3s-galaxy/galaxy-infra.yaml
kubectl apply -f /tmp/k3s-galaxy/galaxy-apps.yaml

for d in redis kafka smtp-service-galaxy catalog-service auth-service asset-service storm-service kafka-connect api-gateway client; do
  kubectl -n "$NS" rollout status "deploy/$d" --timeout=300s || true
done

kubectl -n "$NS" get pods -o wide
echo "galaxy migrate done"
