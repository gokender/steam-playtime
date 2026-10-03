#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="steam-playtime-builder:python3.13"

cd "$ROOT_DIR"

docker build \
  --file packaging/Dockerfile.linux-x86_64 \
  --tag "$IMAGE_NAME" \
  .

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --volume "$ROOT_DIR:/workspace" \
  --workdir /workspace \
  "$IMAGE_NAME" \
  bash -lc '
    set -euo pipefail

    rm -rf build dist steam-playtime.spec

    python -m venv /tmp/steam-playtime-build
    source /tmp/steam-playtime-build/bin/activate

    python -m pip install --upgrade pip
    python -m pip install ".[build]" pytest

    VERSION="$(python -c "from steam_playtime import __version__; print(__version__)")"
    PACKAGE_DIRECTORY="steam-playtime-${VERSION}"
    ARCHIVE_NAME="${PACKAGE_DIRECTORY}-linux-x86_64.tar.gz"

    pytest

    pyinstaller \
      --clean \
      --noconfirm \
      --onedir \
      --name steam-playtime \
      --paths src \
      --collect-all fastapi \
      --collect-all httpx \
      --collect-all pydantic \
      --collect-all uvicorn \
      src/steam_playtime/__main__.py

    mv dist/steam-playtime "dist/${PACKAGE_DIRECTORY}"

    STEAM_PLAYTIME_CONFIG=/tmp/steam-playtime/config.toml \
    STEAM_PLAYTIME_DATA_DIR=/tmp/steam-playtime/data \
      "dist/${PACKAGE_DIRECTORY}/steam-playtime" status

    tar -C dist \
      -czf "/workspace/dist/${ARCHIVE_NAME}" \
      "${PACKAGE_DIRECTORY}"

    cd dist
    sha256sum "${ARCHIVE_NAME}" > "${ARCHIVE_NAME}.sha256"
    cp "${ARCHIVE_NAME}.sha256" SHA256SUMS
  '

echo
echo "Package created:"
echo "  dist/steam-playtime-<version>-linux-x86_64.tar.gz"
echo "  dist/SHA256SUMS"
