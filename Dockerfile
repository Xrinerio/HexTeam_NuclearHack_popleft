FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ ./app/

RUN pip install uv \
    && uv pip install --system --no-cache .

ENV UVICORN_HOST=0.0.0.0

EXPOSE 8001 6767 50000/udp

CMD ["python", "-m", "app"]
