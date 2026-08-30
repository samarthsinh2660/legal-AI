# The API service. Not the ingest jobs -- those are run by hand against the
# same database and have no place in a service image.
FROM python:3.12-slim

# Model weights land here at first use. Named so a volume can be mounted on
# it: without one, every container restart re-downloads the embedder and the
# cross-encoder.
ENV HF_HOME=/models \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies before source, so editing a file does not reinstall torch.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

EXPOSE 8000

# One worker by default. The rate limiter counts in process memory, so each
# extra worker multiplies the effective limit -- see api/middleware/rate_limit.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
