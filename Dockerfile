# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m build --wheel --outdir /wheels


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="irminsul"
LABEL org.opencontainers.image.description="A documentation system for complex codebases."
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later"
LABEL org.opencontainers.image.source="https://github.com/huajie-zhong/irminsul"

RUN useradd --create-home --shell /bin/bash irminsul
WORKDIR /home/irminsul

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels irminsul \
 && rm -rf /wheels

USER irminsul
WORKDIR /workspace

ENTRYPOINT ["irminsul"]
CMD ["--help"]
