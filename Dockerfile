FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps -e .
COPY . .
RUN useradd --uid 10001 --create-home fleetlab && mkdir -p /app/.runtime && chown -R fleetlab:fleetlab /app
USER fleetlab
CMD ["python", "-m", "streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
