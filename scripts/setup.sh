#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

VCPKG_DIR="${ROOT_DIR}/vcpkg"
VCPKG_REPO="https://github.com/microsoft/vcpkg.git"

# Pin the same vcpkg revision as the repository submodule.
VCPKG_COMMIT="d92484ed3c5020c6679d095ad3e5add907887b62"

echo "Installing Proba artifact dependencies..."

run_as_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        echo "error: root privileges required (install sudo or run as root)."
        exit 1
    fi
}

# ----------------------------------------------------------------------
# Install basic dependencies
# ----------------------------------------------------------------------
if [[ "$(uname -s)" == "Linux" ]]; then
    if command -v apt-get >/dev/null 2>&1; then
        run_as_root apt-get update
        run_as_root apt-get install -y \
            build-essential \
            make \
            git \
            python3 \
            pkg-config \
            curl \
            zip \
            unzip \
            tar \
            ca-certificates
    else
        echo "warning: automatic package installation is supported only"
        echo "         on Ubuntu/Debian. Please ensure the required tools"
        echo "         are already installed."
    fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "error: Homebrew is required on macOS."
        echo "Install Homebrew first: https://brew.sh"
        exit 1
    fi

    brew install pkg-config
else
    echo "warning: unsupported OS for automatic dependency installation."
fi

# ----------------------------------------------------------------------
# Select compiler
#
# Respect user-provided CC/CXX first. Otherwise use the compiler
# available on the system.
# ----------------------------------------------------------------------
if [[ -z "${CC:-}" ]]; then
    CC="$(command -v gcc || command -v cc || true)"
fi

if [[ -z "${CXX:-}" ]]; then
    CXX="$(command -v g++ || command -v c++ || true)"
fi

if [[ -z "${CC}" || -z "${CXX}" ]]; then
    echo "error: no suitable C/C++ compiler found."
    echo "Set CC and CXX explicitly, for example:"
    echo "  CC=gcc CXX=g++ ./scripts/setup.sh"
    exit 1
fi

export CC
export CXX

echo
echo "Using compilers:"
echo "  CC=${CC}"
echo "  CXX=${CXX}"
"${CC}" --version | head -n 1
"${CXX}" --version | head -n 1

# ----------------------------------------------------------------------
# Initialise/retrieve vcpkg
#
# A normal git clone contains vcpkg as a submodule. GitHub/Zenodo ZIP
# archives do not include submodule contents, so fall back to retrieving
# the pinned vcpkg revision directly.
# ----------------------------------------------------------------------
echo
echo "Preparing vcpkg..."

if [[ ! -f "${VCPKG_DIR}/bootstrap-vcpkg.sh" ]]; then
    # First try the normal submodule path when this is a git checkout.
    if git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Initialising vcpkg submodule..."
        git -C "${ROOT_DIR}" submodule update --init --recursive vcpkg || true
    fi
fi

# ZIP archives contain no submodule checkout. Retrieve it explicitly.
if [[ ! -f "${VCPKG_DIR}/bootstrap-vcpkg.sh" ]]; then
    echo "vcpkg submodule contents not found."
    echo "Downloading pinned vcpkg revision..."

    rm -rf "${VCPKG_DIR}"

    git clone "${VCPKG_REPO}" "${VCPKG_DIR}"
    git -C "${VCPKG_DIR}" checkout --detach "${VCPKG_COMMIT}"
fi

echo
echo "Bootstrapping vcpkg..."
"${VCPKG_DIR}/bootstrap-vcpkg.sh"

echo
echo "Installing vcpkg dependencies..."
(
    cd "${ROOT_DIR}"
    CC="${CC}" CXX="${CXX}" "${VCPKG_DIR}/vcpkg" install
)

echo
echo "Setup complete."