#!/usr/bin/env bash
set -eu
ROOT="${AIRFLOW_ROOT:-/home/baxic/Documents/GitHub/AirflowMlflow}"
ENV_FILE="$ROOT/.env"
NS=mlops

echo "Importing images into k3s..."
bash /tmp/k3s-import-images.sh \
  airflowmlflow_mlflow:latest \
  airflowmlflow_stormmodel:latest \
  airflowmlflow_airflow-webserver:latest \
  airflowmlflow_airflow-scheduler:latest

kubectl apply -f /tmp/k3s-mlops/namespace.yaml

# Build secret from .env (literal keys) + aliases Airflow/MLflow expect
TMP=$(mktemp)
# shellcheck disable=SC1090
set -a
# parse KEY=VAL ignoring comments
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|\#*) continue ;;
  esac
  key="${line%%=*}"
  val="${line#*=}"
  val="${val%\"}"
  val="${val#\"}"
  printf '%s=%s\n' "$key" "$val" >>"$TMP"
done <"$ENV_FILE"
set +a

# aliases
grep -q '^AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=' "$TMP" || \
  echo "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=$(grep '^AIRFLOW_DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
grep -q '^MLFLOW_BACKEND_STORE_URI=' "$TMP" || \
  echo "MLFLOW_BACKEND_STORE_URI=$(grep '^MLFLOW_DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
grep -q '^AWS_ACCESS_KEY_ID=' "$TMP" || \
  echo "AWS_ACCESS_KEY_ID=$(grep '^S3_ACCESS_KEY=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
grep -q '^AWS_SECRET_ACCESS_KEY=' "$TMP" || \
  echo "AWS_SECRET_ACCESS_KEY=$(grep '^S3_SECRET_KEY=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
grep -q '^AWS_DEFAULT_REGION=' "$TMP" || \
  echo "AWS_DEFAULT_REGION=$(grep '^S3_REGION=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
grep -q '^MLFLOW_S3_ENDPOINT_URL=' "$TMP" || \
  echo "MLFLOW_S3_ENDPOINT_URL=$(grep '^S3_ENDPOINT_URL=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
DOMAIN=$(grep '^AIRFLOW_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)
grep -q '^AIRFLOW__WEBSERVER__BASE_URL=' "$TMP" || \
  echo "AIRFLOW__WEBSERVER__BASE_URL=https://${DOMAIN}" >>"$TMP"
grep -q '^AIRFLOW__CORE__FERNET_KEY=' "$TMP" || \
  echo "AIRFLOW__CORE__FERNET_KEY=$(grep '^AIRFLOW_FERNET_KEY=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
grep -q '^AIRFLOW__WEBSERVER__SECRET_KEY=' "$TMP" || \
  echo "AIRFLOW__WEBSERVER__SECRET_KEY=$(grep '^AIRFLOW_WEBSERVER_SECRET_KEY=' "$ENV_FILE" | cut -d= -f2-)" >>"$TMP"
# MODEL defaults
grep -q '^MODEL_ALIAS=' "$TMP" || echo "MODEL_ALIAS=production" >>"$TMP"
grep -q '^MODEL_POLL_SECONDS=' "$TMP" || echo "MODEL_POLL_SECONDS=60" >>"$TMP"

kubectl -n "$NS" create secret generic mlops-env --from-env-file="$TMP" --dry-run=client -o yaml | kubectl apply -f -
rm -f "$TMP"

echo "Stopping docker-compose stack (free host ports 8080/5000/8000)..."
cd "$ROOT"
docker-compose stop airflow-webserver airflow-scheduler mlflow stormmodel || true

kubectl apply -f /tmp/k3s-mlops/mlops-workloads.yaml
kubectl -n "$NS" rollout status deploy/mlflow --timeout=180s
kubectl -n "$NS" rollout status deploy/stormmodel --timeout=180s
kubectl -n "$NS" rollout status deploy/airflow-webserver --timeout=240s
kubectl -n "$NS" rollout status deploy/airflow-scheduler --timeout=240s
kubectl -n "$NS" get pods -o wide
echo "mlops migrate done"
