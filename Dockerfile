# syntax=docker/dockerfile:1.7
#
# Builds a slim runtime image around a pre-built wheel. The wheel is produced
# on the GitHub Actions runner (where the .git history is intact and hatch-vcs
# can derive the version from the tag) and copied into `dist/` before
# `docker build` runs.

FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="irminsul"
LABEL org.opencontainers.image.description="A documentation system for complex codebases."
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later"
LABEL org.opencontainers.image.source="https://github.com/huajie-zhong/irminsul"

RUN useradd --create-home --shell /bin/bash irminsul

COPY dist/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl \
 && rm -rf /tmp/wheels

USER irminsul
WORKDIR /workspace

ENTRYPOINT ["irminsul"]
CMD ["--help"]
