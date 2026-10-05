#!/usr/bin/env bash
# Import local Docker images into k3s containerd (imagePullPolicy: IfNotPresent/Never).
set -eu
if ! command -v docker >/dev/null; then
  echo "docker required on this node" >&2
  exit 1
fi
if ! command -v k3s >/dev/null; then
  echo "k3s required on this node" >&2
  exit 1
fi
for img in "$@"; do
  echo "importing $img"
  docker save "$img" | k3s ctr images import -
done
echo "done"
