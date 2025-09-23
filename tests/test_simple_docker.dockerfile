FROM node:20-alpine

# Install system dependencies
RUN apk add --no-cache \
    git \
    curl \
    python3 \
    py3-pip \
    bash

# Test user creation step by step
RUN addgroup -g 1001 codex
RUN adduser -D -u 1001 -G codex codex

# Test directory creation
RUN mkdir -p /app/workspace /app/config /app/sessions
RUN chown -R codex:codex /app

USER codex
WORKDIR /app

CMD ["echo", "Container test successful"]