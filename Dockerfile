FROM python:3.12-slim
WORKDIR /srv/app
ENV PATH="/srv/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.10.8
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --all-groups --no-install-project
COPY . .
RUN uv sync --frozen --all-groups
EXPOSE 8000
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
