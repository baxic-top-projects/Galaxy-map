#!/usr/bin/env bash
set -euo pipefail

namespace=${KAFKA_NAMESPACE:-galaxy-map}
bootstrap=${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}

kube=(k3s kubectl --kubeconfig "${KUBECONFIG:-$HOME/.kube/config}")
if ! command -v k3s >/dev/null 2>&1; then
  kube=(kubectl)
fi

kafka_pod=$(
  "${kube[@]}" get pods -n "$namespace" \
    -l app=galaxy-map-kafka \
    -o jsonpath='{.items[0].metadata.name}'
)
[[ -n "$kafka_pod" ]] || {
  echo "Kafka pod not found in namespace $namespace" >&2
  exit 1
}

"${kube[@]}" wait -n "$namespace" \
  --for=condition=Ready "pod/$kafka_pod" --timeout=5m

topics=(
  _galaxy_connect_offsets
  _galaxy_connect_configs
  _galaxy_connect_status
)
for topic in "${topics[@]}"; do
  "${kube[@]}" exec -n "$namespace" "$kafka_pod" -- \
    /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$bootstrap" \
    --create --if-not-exists \
    --topic "$topic" \
    --partitions 1 \
    --replication-factor 1 \
    --config cleanup.policy=compact

  # Existing topics may have been auto-created with cleanup.policy=delete.
  "${kube[@]}" exec -n "$namespace" "$kafka_pod" -- \
    /opt/kafka/bin/kafka-configs.sh \
    --bootstrap-server "$bootstrap" \
    --alter \
    --entity-type topics \
    --entity-name "$topic" \
    --add-config cleanup.policy=compact
done

"${kube[@]}" rollout restart \
  deployment/galaxy-map-kafka-connect -n "$namespace"
"${kube[@]}" rollout status \
  deployment/galaxy-map-kafka-connect -n "$namespace" --timeout=5m

