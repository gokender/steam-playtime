# Linux x86_64 manual packaging

## Quick build

From the repository root:

```bash
./scripts/package-linux-x86_64.sh
```

The script builds the image, runs the test suite, creates the PyInstaller
directory package, smoke-tests it, and produces:

```text
dist/
├── steam-playtime-<version>/
├── steam-playtime-<version>-linux-x86_64.tar.gz
├── steam-playtime-<version>-linux-x86_64.tar.gz.sha256
└── SHA256SUMS
```

The version comes from `src/steam_playtime/__init__.py`. Use the versioned
directory for immediate local testing. The `.tar.gz` archive is the portable
Linux x86_64 package.

Previous versioned packages are preserved. The script refuses to replace an
existing version; bump the application version before a new release, or use
`--force` only when intentionally rebuilding the same version:

```bash
./scripts/package-linux-x86_64.sh --force
```

This image builds a PyInstaller directory package on Debian Bookworm (glibc
2.36), which is compatible with Steam Deck's glibc 2.41. It is intentionally a
manual workflow: it does not publish releases or run CI jobs.

## Build the image

From the repository root:

```bash
docker build \
  --file packaging/Dockerfile.linux-x86_64 \
  --tag steam-playtime-builder:python3.11 \
  .
```

Check the build environment if desired:

```bash
docker run --rm steam-playtime-builder:python3.11 python --version
docker run --rm steam-playtime-builder:python3.11 ldd --version
```

## Build and test the package

Open an interactive build shell. The repository is mounted, so `dist/` is
written directly to the host.

```bash
docker run --rm --interactive --tty \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --volume "$PWD:/workspace" \
  --workdir /workspace \
  steam-playtime-builder:python3.11
```

Inside the container:

```bash
python -m venv /tmp/steam-playtime-build
source /tmp/steam-playtime-build/bin/activate

python -m pip install --upgrade pip
python -m pip install ".[build]" pytest
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

dist/steam-playtime/steam-playtime --help
dist/steam-playtime/steam-playtime status
```

Copy the complete `dist/steam-playtime/` directory to the Steam Deck. The
target does not need Python, pip, or uv to run the packaged executable.

## GitHub Actions

The `Package Linux` workflow can be started manually to build an artifact
without creating a release. A pushed `v*` tag runs the same build, verifies
that the tag matches the package version, then creates or updates the GitHub
Release with the archive and checksums. The workflow never creates Git tags.
