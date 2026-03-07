FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install uv \
    && uv pip install --system --no-cache -r pyproject.toml

COPY app/ ./app/

ENV UVICORN_HOST=0.0.0.0

EXPOSE 8001 6767 50000/udp

CMD ["py", "-m", "app"]
