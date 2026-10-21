FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/app.db PORT=8000
COPY requirements.lock ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.lock
COPY app/ ./app/
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/_health', timeout=2).read()" || exit 1
CMD ["python", "-m", "app"]

# Statistically Speaking owns its version independently of any hosting site. Keep the
# label after dependency installation so a version bump reuses those layers.
ARG STATISTICALLY_SPEAKING_VERSION=dev
LABEL org.opencontainers.image.version=$STATISTICALLY_SPEAKING_VERSION

# Hosting-specific defaults belong in a variant of this app's own image.
# Production still requires a persistent session secret supplied at runtime.
# Proxy trust stays a runtime choice for the particular host/network.
FROM runtime AS athenaeum
ENV APP_ENV=production ROOT_PATH=/statistically-speaking

# A plain docker build remains general-purpose and serves at the root path.
# The release Compose file builds both standalone and athenaeum targets.
FROM runtime AS standalone
