#!/usr/bin/env bash

DATA_ROOT="${SKILLLINEAGE_DATA_ROOT:-/root/autodl-tmp}"
export HF_HOME="${DATA_ROOT}/cache/huggingface"
export PIP_CACHE_DIR="${DATA_ROOT}/cache/pip"
export XDG_CACHE_HOME="${DATA_ROOT}/cache"
export TOKENIZERS_PARALLELISM=false
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export ALFWORLD_DATA="${ALFWORLD_DATA:-${DATA_ROOT}/cache/alfworld}"

# shellcheck disable=SC1091
source "${DATA_ROOT}/envs/skilllineage/bin/activate"
