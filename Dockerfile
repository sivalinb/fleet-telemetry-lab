FROM otel/opentelemetry-collector-contrib:0.160.0 AS collector
FROM python:3.12-slim
WORKDIR /app
COPY --from=collector /otelcol-contrib /app/tools/collector
ENV LAB_COLLECTOR_BINARY=/app/tools/collector
COPY requirements.lock pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps -e .
COPY . .
RUN useradd --uid 10001 --create-home fleetlab && mkdir -p /app/.runtime && chown -R fleetlab:fleetlab /app
USER fleetlab
CMD ["python", "gradio_app.py"]
