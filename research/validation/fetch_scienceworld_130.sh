#!/usr/bin/env bash
set -euo pipefail
# Invoke from the paper project root. No package environment is overwritten.
sw_directory=research/validation/vendor
sw_target="$sw_directory/scienceworld-e8216d6.jar"
sw_sha=e77b0fee7d68abe3ca5b12e57d86e2bfe7603f20c5200da0b0f085939faeb465
mkdir -p "$sw_directory"
if [ ! -f "$sw_target" ]; then
    sw_download=$(mktemp "$sw_directory/scienceworld-download.XXXXXX.partial")
    curl --fail --silent --show-error --location --connect-timeout 15 --max-time 180 \
      https://raw.githubusercontent.com/allenai/ScienceWorld/e8216d6044e8e39be9fcb185e3b2dfb602584b52/scienceworld/scienceworld.jar \
      --output "$sw_download"
    test "$(sha256sum "$sw_download" | cut -d ' ' -f 1)" = "$sw_sha"
    mv -n "$sw_download" "$sw_target"
fi
test "$(sha256sum "$sw_target" | cut -d ' ' -f 1)" = "$sw_sha"
