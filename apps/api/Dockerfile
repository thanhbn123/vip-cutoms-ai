FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY app ./app
# Optional build secret `ca_bundle`: a CA file for hosts whose egress is TLS-intercepted. Absent/empty → default trust store.
RUN --mount=type=secret,id=ca_bundle,required=false \
    sh -c 'if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
           pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .'
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
# Demo fixtures (small text files) so `scripts/seed_demo.py --with-case` can seed the V12 reference case inside the container.
COPY tests/fixtures ./tests/fixtures
RUN useradd -m appuser && mkdir -p /data/uploads && chown appuser /data/uploads
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
