# k3s cluster (Galaxy + MLops)

## Nodes

| Node | IP | Role |
|------|-----|------|
| `cp-baxic` | 89.124.86.173 | control-plane + mlops (Airflow/MLflow/stormmodel) |
| `worker-146` | 146.103.110.27 | Galaxy-map stack |
| `worker-45` / `worker-192` | … | join when SSH/agent available |

UI: https://k8s.baxic.ru (Headlamp). Traefik disabled; host nginx serves `*.baxic.ru`.

## Namespaces

- `mlops` — pinned to `cp-baxic`, hostPorts `8080/5000/8000` for existing nginx
- `galaxy` — pinned to `worker-146`, hostPorts `9999/9998/9997`
- `headlamp` — cluster UI

## Migrate from docker-compose

On **cp-baxic**:

```bash
sudo bash /tmp/k3s-mlops/deploy.sh
```

On **worker-146**:

```bash
sudo bash /tmp/k3s-galaxy/deploy.sh
```

Images are imported from local Docker into k3s containerd (`imagePullPolicy: Never` / `IfNotPresent`).

## Useful

```bash
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl -n mlops logs deploy/stormmodel --tail=100
kubectl -n galaxy logs deploy/storm-service --tail=100
```
