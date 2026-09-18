#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(pwd)}"
DATA_ROOT="${SKILLLINEAGE_DATA_ROOT:-/root/autodl-tmp}"
VENV_ROOT="${DATA_ROOT}/envs/skilllineage"

mkdir -p \
  "${DATA_ROOT}/cache/huggingface" \
  "${DATA_ROOT}/cache/pip" \
  "${DATA_ROOT}/envs"

export HF_HOME="${DATA_ROOT}/cache/huggingface"
export PIP_CACHE_DIR="${DATA_ROOT}/cache/pip"
export XDG_CACHE_HOME="${DATA_ROOT}/cache"

if [[ ! -x "${VENV_ROOT}/bin/python" ]]; then
  python -m venv --system-site-packages "${VENV_ROOT}"
fi

"${VENV_ROOT}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_ROOT}/bin/python" -m pip install -e "${PROJECT_ROOT}[dev,model]"

"${VENV_ROOT}/bin/python" - <<'PY'
import torch
import transformers

print(f"torch={torch.__version__}")
print(f"torch_cuda={torch.version.cuda}")
print(f"transformers={transformers.__version__}")
print(f"cuda_available={torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"gpu={torch.cuda.get_device_name(0)}")
    print(f"capability={torch.cuda.get_device_capability(0)}")
PY
