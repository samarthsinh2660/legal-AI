# Two targets, one base: `api` takes requests, `worker` answers them.
# Build with --target api or --target worker.
FROM python:3.12-slim AS base

# Model weights land here at first use, so a volume can be mounted on it.
# Without one, every restart re-downloads the embedder and cross-encoder.
ENV HF_HOME=/models \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies before source, so editing a file does not reinstall torch.
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Which torch wheel to install. The default is CPU-only: the CUDA wheel
# carries 2724 MB of driver libraries, which is 47% of the image and dead
# weight on a box with no GPU.
#
# On a machine that has one, build with
#   --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121
# and give the container the GPU (`--gpus all`, or compose `deploy.
# resources.reservations.devices`). Nothing in the code changes:
# sentence-transformers picks CUDA up when torch reports it.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

# Installed first, so the resolution below finds torch already satisfied
# and does not pull the default wheel over it.
RUN pip install --no-cache-dir --index-url "$TORCH_INDEX" torch \
 && pip install --no-cache-dir .

FROM base AS api

EXPOSE 8000

# One uvicorn worker. The rate limiter counts in process memory, so a second
# would double every user's effective budget -- see api/middleware/rate_limit.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker

# The research graph. Only this image runs it.
RUN pip install --no-cache-dir ".[worker]"

# Import what a research turn reaches, including the lazy imports inside
# the discovery fallback. Without this a missing dependency surfaces as a
# failed question in production rather than a failed build: live discovery
# is imported only when the corpus comes up short, so it survived every
# start-up check until a real question needed it.
RUN python -c "\
import worker.loop, worker.research, worker.drafting; \
from legal_ai.graph.build import build_research_graph; build_research_graph(); \
import legal_ai.tools.judgments, legal_ai.ingestion.judgments.dynamic_search; \
from bharat_courts.archive.endpoints import SCI_BUCKET; \
print('worker imports resolve')"

# No EXPOSE: a worker opens connections and accepts none, which is what lets
# it run on another machine behind any NAT.
CMD ["python", "-m", "worker"]
