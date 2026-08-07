#!/usr/bin/env bash
set -euo pipefail

echo "Installing Proba artifact dependencies..."

if [[ "$(uname -s)" == "Linux" ]]; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "error: automatic compiler installation currently supports Ubuntu/Debian only."
        exit 1
    fi

    sudo apt-get update
    sudo apt-get install -y \
        gcc-11 \
        g++-11 \
        make \
        git \
        python3

elif [[ "$(uname -s)" == "Darwin" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "error: Homebrew is required on macOS."
        echo "Install Homebrew first: https://brew.sh"
        exit 1
    fi

    brew install gcc@11

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