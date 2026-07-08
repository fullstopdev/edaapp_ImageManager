# Build status-publisher (Go) then copy into the Python controller image.
FROM golang:1.26.2-bookworm AS statusbuilder
WORKDIR /src
COPY statuspublisher/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /status-publisher .

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/fullstopdev/edaapp_ImageManager"
LABEL org.opencontainers.image.description="EDA Image Manager Controller"
LABEL org.opencontainers.image.license="MIT"
#
# Runtime deps:
# - PyJWT provides the `jwt` module used by auth.py (OIDC signature validation).
# - cryptography is required by PyJWT for signature verification.
# CI passes because dev deps are installed for tests, but this image must
# install runtime deps explicitly.
RUN python3 -m pip install --no-cache-dir "PyJWT>=2.3.0" "cryptography>=3.4.0"
COPY --from=statusbuilder /status-publisher /app/status-publisher
COPY controller/ /app/
WORKDIR /app
USER 65534
CMD ["python3", "main.py"]
