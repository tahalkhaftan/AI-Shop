#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
export CMAKE_BUILD_PARALLEL_LEVEL=2
export CMAKE_ARGS="${CMAKE_ARGS:--DGGML_CUDA=OFF}"
.venv/bin/python -m pip install --disable-pip-version-check --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu '.[local]'
.venv/bin/python -m ai_shop download-model
echo 'Ready. See docs/integration.md to connect your own public website data.'
