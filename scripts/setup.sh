#!/usr/bin/env bash
set -euo pipefail

echo "Installing Proba artifact dependencies..."

# Prefer sudo when available; fall back to direct apt-get as root (e.g. containers).
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

if [[ "$(uname -s)" == "Linux" ]]; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "error: automatic compiler installation currently supports Ubuntu/Debian only."
        exit 1
    fi

    run_as_root apt-get update
    run_as_root apt-get install -y \
        gcc-11 \
        g++-11 \
        make \
        git \
        python3 \
        pkg-config \
        curl \
        zip \
        unzip \
        tar \
        ca-certificates

elif [[ "$(uname -s)" == "Darwin" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "error: Homebrew is required on macOS."
        echo "Install Homebrew first: https://brew.sh"
        exit 1
    fi

    brew install gcc@11 pkg-config

else
    echo "error: unsupported operating system."
    exit 1
fi

echo
echo "Compiler versions:"
gcc-11 --version | head -n 1
g++-11 --version | head -n 1

echo
echo "Initializing vcpkg..."
git submodule update --init --recursive
./vcpkg/bootstrap-vcpkg.sh

echo
echo "Installing vcpkg dependencies..."
CC=gcc-11 CXX=g++-11 ./vcpkg/vcpkg install

echo
echo "Setup complete."