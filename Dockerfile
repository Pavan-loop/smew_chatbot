FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.19
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "app"]
