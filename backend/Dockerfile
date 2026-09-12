# Build from the repository root: docker build -f backend/Dockerfile -t robotcontrol .
FROM python:3.14.7-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# OpenCV and SQL Server also require native libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unixodbc libgl1 libglib2.0-0 \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
       -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -f /tmp/packages-microsoft-prod.deb \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-cache
COPY backend ./backend
# Build the frontend on the host before building this image.
COPY frontend/dist ./frontend/dist
RUN groupadd -r robotcontrol && useradd -r -g robotcontrol robotcontrol \
    && mkdir -p /app/data && chown -R robotcontrol:robotcontrol /app
USER robotcontrol
EXPOSE 8005
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1
CMD ["python", "backend/main.py", "--host", "0.0.0.0", "--port", "8005", "--no-browser"]
