#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="steam-playtime-builder:python3.11"
FORCE=false

if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--force]" >&2
  exit 2
fi

cd "$ROOT_DIR"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/steam_playtime/__init__.py)"
if [[ -z "$VERSION" ]]; then
  echo "Could not determine the application version." >&2
  exit 1
fi

PACKAGE_DIRECTORY="steam-playtime-${VERSION}"
ARCHIVE_NAME="${PACKAGE_DIRECTORY}-linux-x86_64.tar.gz"
if [[ ( -e "dist/${PACKAGE_DIRECTORY}" || -e "dist/${ARCHIVE_NAME}" ) && "$FORCE" != "true" ]]; then
  echo "Package version ${VERSION} already exists. Bump the version or use --force." >&2
  exit 2
fi

docker build \
  --file packaging/Dockerfile.linux-x86_64 \
  --tag "$IMAGE_NAME" \
  .

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --env FORCE="$FORCE" \
  --env VERSION="$VERSION" \
  --volume "$ROOT_DIR:/workspace" \
  --workdir /workspace \
  "$IMAGE_NAME" \
  bash -lc '
    set -euo pipefail

    rm -rf build steam-playtime.spec dist/steam-playtime

    python -m venv /tmp/steam-playtime-build
    source /tmp/steam-playtime-build/bin/activate

    python -m pip install --upgrade pip
    python -m pip install ".[build]" pytest

    INSTALLED_VERSION="$(python -c "from steam_playtime import __version__; print(__version__)")"
    if [[ "$INSTALLED_VERSION" != "$VERSION" ]]; then
      echo "Installed version does not match the source version." >&2
      exit 1
    fi
    PACKAGE_DIRECTORY="steam-playtime-${VERSION}"
    ARCHIVE_NAME="${PACKAGE_DIRECTORY}-linux-x86_64.tar.gz"

    if [[ -e "dist/${PACKAGE_DIRECTORY}" || -e "dist/${ARCHIVE_NAME}" ]]; then
      if [[ "$FORCE" != "true" ]]; then
        echo "Package version ${VERSION} already exists. Bump the version or use --force." >&2
        exit 2
      fi
      rm -rf "dist/${PACKAGE_DIRECTORY}"
      rm -f "dist/${ARCHIVE_NAME}" "dist/${ARCHIVE_NAME}.sha256"
    fi

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
    cat ./*.tar.gz.sha256 > SHA256SUMS
  '

echo
echo "Package created:"
echo "  dist/steam-playtime-<version>-linux-x86_64.tar.gz"
echo "  dist/SHA256SUMS"
