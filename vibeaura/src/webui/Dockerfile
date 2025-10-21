FROM python:alpine3.21

RUN adduser --disabled-password --gecos "" --uid 1000 webuser

WORKDIR /app

RUN apk add --no-cache \
    curl \
    nano

RUN pip install --no-cache-dir \
    Flask==3.1.0 \
    requests==2.32.3 \
    PyYAML \
    PyJWT \
    cryptography \
    pathlib

USER webuser

COPY ./ /app