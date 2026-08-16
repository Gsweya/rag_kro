#!/usr/bin/env bash
# Resumable pre-download of the heavy ML wheels for the shared python-base image.
#
# torch is ~526MB; on a slow/flaky connection pip cannot resume a partial
# download, so a timeout throws away everything fetched so far. This script
# uses wget -C - (resume) and stores the wheel in
# infra/docker/python-base/wheels/, where the Docker build COPYs it in.
#
# Re-run it any number of times — it picks up where it left off.
set -euo pipefail
cd "$(dirname "$0")"

WHEELS_DIR="wheels"
PY_TAG="cp312"
TORCH_VERSION="2.13.0"
TORCH_WHEEL="torch-${TORCH_VERSION}-${PY_TAG}-${PY_TAG}-manylinux_2_28_x86_64.whl"

mkdir -p "$WHEELS_DIR"

# ---- torch ---------------------------------------------------------------
torch_path="$WHEELS_DIR/$TORCH_WHEEL"
if [ -s "$torch_path" ]; then
    echo "torch already present: $torch_path ($(du -h "$torch_path" | cut -f1))"
else
    echo "==> locating $TORCH_WHEEL on PyPI ..."
    TORCH_URL=$(python3 - "$TORCH_WHEEL" <<'PY'
import json, sys, urllib.request
wheel = sys.argv[1]
d = json.load(urllib.request.urlopen("https://pypi.org/pypi/torch/json"))
for u in d["urls"]:
    if u["filename"] == wheel:
        print(u["url"]); break
PY
)
    echo "==> downloading $TORCH_WHEEL (resumable) ..."
    # download to .part so a partial file is never mistaken for a complete wheel
    wget -c --tries=0 --timeout=60 -O "$torch_path.part" "$TORCH_URL"
    mv "$torch_path.part" "$torch_path"
fi

# ---- sentence-transformers (small, but grab it too for convenience) ------
st_path="$WHEELS_DIR/sentence-transformers.whl"
if [ ! -s "$st_path" ]; then
    echo "==> locating sentence-transformers wheel ..."
    ST_URL=$(python3 - <<'PY'
import json, urllib.request
d = json.load(urllib.request.urlopen("https://pypi.org/pypi/sentence-transformers/json"))
for u in d["urls"]:
    if u["filename"].startswith("sentence_transformers") and u["filename"].endswith("py3-none-any.whl"):
        print(u["url"]); break
PY
)
    echo "==> downloading sentence-transformers ..."
    wget -c --tries=0 --timeout=60 -O "$st_path.part" "$ST_URL"
    mv "$st_path.part" "$st_path"
fi

echo
echo "==> wheels ready in $WHEELS_DIR/:"
ls -lh "$WHEELS_DIR"