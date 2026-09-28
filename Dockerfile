ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION}
ARG UV_VERSION=0.10.8
ARG API_PORT=8000
WORKDIR /srv/app
ENV PATH="/srv/app/.venv/bin:$PATH" API_PORT=${API_PORT}
RUN pip install --no-cache-dir "uv==${UV_VERSION}"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --all-groups --no-install-project
COPY . .
RUN uv sync --frozen --all-groups
EXPOSE ${API_PORT}
CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT}"]
