#!/bin/sh
set -e

dockerd-entrypoint.sh &

DOCKER_PID=$!

timeout=30
count=0

echo "Waiting for Docker daemon..."

until docker info > /dev/null 2>&1; do
  sleep 2
  count=$((count + 2))

  if ! kill -0 $DOCKER_PID 2>/dev/null; then
    echo "Docker daemon process died"
    exit 1
  fi

  if [ $count -ge $timeout ]; then
    echo "Timeout waiting for Docker daemon"
    kill $DOCKER_PID 2>/dev/null || true
    exit 1
  fi
  echo "Waiting for Docker... ($count/$timeout seconds)"
done

echo "Docker daemon is ready"

exec "$@"
