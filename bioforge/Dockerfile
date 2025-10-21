FROM golang:1.24-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o main main.go

FROM debian:bookworm-slim AS runner

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --system appuser && useradd --system --gid appuser --home /app appuser
USER appuser

COPY --from=builder --chown=appuser:appuser /app/main .
COPY --chown=appuser:appuser ./assets ./assets
COPY --chown=appuser:appuser ./bin/genlang /srv/

CMD ["./main"]
