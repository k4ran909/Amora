FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY amora ./amora
COPY scripts ./scripts
RUN pip install --no-cache-dir . && python scripts/download_models.py

RUN useradd --create-home amora && mkdir -p /app/data && chown -R amora /app/data
USER amora

CMD ["python", "-m", "amora"]
