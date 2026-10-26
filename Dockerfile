# Python 3.11 base; Node 22 is copied in because the vendored H-MEM engine runs
# with `node --experimental-transform-types`, which newer Node versions reject.
FROM python:3.11-slim-bookworm

# Node 22 binary only (no npm step: H-MEM is vendored in the repo).
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

# Python deps are installed at build time; nothing is downloaded at run time.
COPY agents/legal_agent/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .

# Default: replay the recorded capture offline. Override with `-e SAMPLE_MODE=false`.
ENV SAMPLE_MODE=true

CMD ["python", "run.py", "input_examples/1.json"]
