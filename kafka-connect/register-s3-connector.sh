#!/bin/sh
set -eu

: "${KAFKA_S3_BUCKET:?KAFKA_S3_BUCKET is required}"
: "${KAFKA_S3_ENDPOINT_URL:?KAFKA_S3_ENDPOINT_URL is required}"
: "${KAFKA_S3_ACCESS_KEY_ID:?KAFKA_S3_ACCESS_KEY_ID is required}"
: "${KAFKA_S3_SECRET_ACCESS_KEY:?KAFKA_S3_SECRET_ACCESS_KEY is required}"

KAFKA_S3_REGION="${KAFKA_S3_REGION:-ru-central1}"
KAFKA_S3_FORCE_PATH_STYLE="${KAFKA_S3_FORCE_PATH_STYLE:-false}"
KAFKA_S3_TOPICS_DIR="${KAFKA_S3_TOPICS_DIR:-storm-training}"
KAFKA_S3_FLUSH_SIZE="${KAFKA_S3_FLUSH_SIZE:-1000}"
KAFKA_S3_ROTATE_INTERVAL_MS="${KAFKA_S3_ROTATE_INTERVAL_MS:-600000}"

cat > /tmp/storm-s3-sink.json <<EOF
{
  "connector.class": "io.confluent.connect.s3.S3SinkConnector",
  "tasks.max": "1",
  "topics": "galaxy.storms",
  "s3.bucket.name": "${KAFKA_S3_BUCKET}",
  "s3.region": "${KAFKA_S3_REGION}",
  "store.url": "${KAFKA_S3_ENDPOINT_URL}",
  "s3.path.style.access.enabled": "${KAFKA_S3_FORCE_PATH_STYLE}",
  "aws.access.key.id": "${KAFKA_S3_ACCESS_KEY_ID}",
  "aws.secret.access.key": "${KAFKA_S3_SECRET_ACCESS_KEY}",
  "s3.part.size": "5242880",
  "storage.class": "io.confluent.connect.s3.storage.S3Storage",
  "format.class": "io.confluent.connect.s3.format.json.JsonFormat",
  "s3.compression.type": "gzip",
  "schema.compatibility": "NONE",
  "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
  "partition.duration.ms": "3600000",
  "path.format": "'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH",
  "locale": "en",
  "timezone": "UTC",
  "timestamp.extractor": "Record",
  "topics.dir": "${KAFKA_S3_TOPICS_DIR}",
  "flush.size": "${KAFKA_S3_FLUSH_SIZE}",
  "rotate.schedule.interval.ms": "${KAFKA_S3_ROTATE_INTERVAL_MS}",
  "behavior.on.null.values": "ignore",
  "key.converter": "org.apache.kafka.connect.storage.StringConverter",
  "value.converter": "org.apache.kafka.connect.json.JsonConverter",
  "value.converter.schemas.enable": "false"
}
EOF

curl \
  --fail \
  --show-error \
  --silent \
  --retry 20 \
  --retry-all-errors \
  --retry-delay 3 \
  -X PUT \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/storm-s3-sink.json \
  "${KAFKA_CONNECT_URL}/connectors/storm-s3-sink/config"

printf '\nS3 connector registered successfully.\n'
