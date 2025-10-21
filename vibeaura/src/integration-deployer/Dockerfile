FROM docker:24.0.5-dind

EXPOSE 8992

RUN apk add --no-cache tini \
    python3 py3-pip py3-setuptools py3-wheel \
    bash curl git iproute2

RUN pip3 install \
    Flask==3.1.0 \
    requests==2.32.3 \
    PyYAML

WORKDIR /app

COPY ./ /app

COPY start_docker.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/entrypoint.sh"]

CMD ["python3", "app.py"]
