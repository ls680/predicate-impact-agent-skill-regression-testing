#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${SKILLLINEAGE_DATA_ROOT:-/root/autodl-tmp}"
ALFWORLD_ROOT="${ALFWORLD_DATA:-${DATA_ROOT}/cache/alfworld}"
VENV_ROOT="${DATA_ROOT}/envs/skilllineage"
DOWNLOAD_PREFIX="${GITHUB_DOWNLOAD_PREFIX:-}"

if ! command -v java >/dev/null 2>&1; then
  echo "Java 8 or newer is required by ScienceWorld." >&2
  echo "Ubuntu: apt-get update && apt-get install -y openjdk-17-jre-headless" >&2
  exit 1
fi

mkdir -p "${ALFWORLD_ROOT}" "${DATA_ROOT}/cache/pip"
export PIP_CACHE_DIR="${DATA_ROOT}/cache/pip"
"${VENV_ROOT}/bin/python" -m pip install \
  "alfworld==0.4.2" "scienceworld==1.2.3" "textworld==1.7.0"

download_and_extract() {
  local url="$1"
  local archive
  archive="$(mktemp "${ALFWORLD_ROOT}/download.XXXXXX.zip")"
  curl -L --fail --retry 8 --retry-delay 2 -o "${archive}" "${DOWNLOAD_PREFIX}${url}"
  "${VENV_ROOT}/bin/python" -m zipfile -e "${archive}" "${ALFWORLD_ROOT}"
  rm -f "${archive}"
}

if [[ ! -d "${ALFWORLD_ROOT}/json_2.1.1" ]]; then
  download_and_extract \
    "https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_json.zip"
fi

if ! find "${ALFWORLD_ROOT}/json_2.1.1" -name game.tw-pddl -print -quit | grep -q .; then
  download_and_extract \
    "https://github.com/alfworld/alfworld/releases/download/0.4.0/json_2.1.2_tw-pddl.zip"
fi

export ALFWORLD_DATA="${ALFWORLD_ROOT}"
"${VENV_ROOT}/bin/python" - <<'PY'
from importlib.metadata import version
from scienceworld import ScienceWorldEnv

print("alfworld=" + version("alfworld"))
print("textworld=" + version("textworld"))
print("scienceworld=" + version("scienceworld"))
env = ScienceWorldEnv("", envStepLimit=5)
print("scienceworld_tasks=" + str(len(env.get_task_names())))
env.close()
PY
