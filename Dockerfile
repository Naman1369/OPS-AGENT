# OPS-AGENT API + dashboard (synopsis Phase 8, Weeks 15-16)
#   docker build -t ops-agent:1.0.0 .
#   docker run -p 8000:8000 -e GEMINI_API_KEY=... ops-agent:1.0.0
FROM python:3.11-slim

ARG WITH_TRANSFORMERS=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    OPS_EMBEDDER=tfidf \
    OPS_GOVERNANCE_MODE=auto \
    OPS_CHROMA_DIR=/var/lib/ops-agent/chroma \
    OPS_AUDIT_DB=/var/lib/ops-agent/audit/audit.sqlite3

WORKDIR /app

COPY requirements-runtime.txt ./
RUN pip install -r requirements-runtime.txt \
 && if [ "$WITH_TRANSFORMERS" = "true" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch \
      && pip install "sentence-transformers>=3.0.0"; \
    fi

COPY src ./src
COPY data/knowledge_base ./data/knowledge_base
COPY artifacts ./artifacts
COPY reports/evaluation ./reports/evaluation

RUN useradd --create-home --uid 10001 opsagent \
 && mkdir -p /var/lib/ops-agent/chroma /var/lib/ops-agent/audit \
 && chown -R opsagent:opsagent /var/lib/ops-agent
USER opsagent

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "ops_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
