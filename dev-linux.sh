#!/bin/bash
# UE Pipeline Development Environment Setup Script (Linux)
# Usage: source dev-linux.sh  (note: must be sourced)

echo "========================================"
echo "  UE Pipeline Development Environment (Linux)"
echo "========================================"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$REPO_ROOT/.venv"
UE_PIPELINE_DIR="$REPO_ROOT/ue_pipeline"

# 1. Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
    echo "  OK Virtual environment activated"
else
    echo "  WARNING Virtual environment not found: $VENV_PATH"
    echo "  Please create it first: python3 -m venv .venv"
fi

# 2. Set environment variables
echo "Setting environment variables..."
export UE_SYSTEM_TYPE="linux"
echo "  OK UE_SYSTEM_TYPE = linux"

echo ""
echo "========================================"
echo "  Environment Ready!"
echo "========================================"
echo ""

# Define shortcut functions
ue-bake() {
    if [ $# -eq 0 ]; then
        python app.py bake_navmesh
    elif [ "$1" = "--manifest" ]; then
        python app.py bake_navmesh --manifest "$2"
    else
        python app.py bake_navmesh --manifest "$1"
    fi
}

ue-sequence() {
    if [ $# -eq 0 ]; then
        python app.py create_sequence
    elif [ "$1" = "--manifest" ]; then
        python app.py create_sequence --manifest "$2"
    else
        python app.py create_sequence --manifest "$1"
    fi
}

ue-render() {
    if [ $# -eq 0 ]; then
        python app.py render
    elif [ "$1" = "--manifest" ]; then
        python app.py render --manifest "$2"
    else
        python app.py render --manifest "$1"
    fi
}

ue-export() {
    if [ $# -eq 0 ]; then
        python app.py export
    elif [ "$1" = "--manifest" ]; then
        python app.py export --manifest "$2"
    else
        python app.py export --manifest "$1"
    fi
}

ue-upload() {
    python app.py upload_scenes
}

ue-download() {
    if [ $# -eq 0 ]; then
        python app.py download_scene --list
    elif [ "$1" = "--list" ] || [ "$1" = "-l" ]; then
        python app.py download_scene --list
    elif [ "$1" = "--search" ] || [ "$1" = "-s" ]; then
        python app.py download_scene --search "$2"
    elif [ "$1" = "--scene" ]; then
        python app.py download_scene --scene "$2"
    else
        python app.py download_scene --scene "$1"
    fi
}

ue-copy() {
    if [ $# -eq 0 ]; then
        python app.py copy_scene --list
    elif [ "$1" = "--list" ] || [ "$1" = "-l" ]; then
        python app.py copy_scene --list
    else
        python app.py copy_scene --scene "$@"
    fi
}

ue-help() {
    echo ""
    echo "Available shortcut commands:"
    echo "  ue-bake       - Bake NavMesh"
    echo "  ue-sequence   - Create sequences"
    echo "  ue-render     - Render"
    echo "  ue-export     - Export"
    echo "  ue-upload     - Upload scenes to BOS"
    echo "  ue-download   - Download scene from BOS"
    echo "  ue-copy       - Copy scene between BOS buckets"
    echo "  ue-help       - Show this help"
    echo ""
    echo "Examples:"
    echo "  ue-sequence                                  # Use config/job_config.json"
    echo "  ue-sequence custom_job.json                  # Use custom config file"
    echo "  ue-download --list                           # List available scenes"
    echo "  ue-download Seaside_Town                     # Download a scene"
    echo "  ue-copy --list                               # List scenes to copy"
    echo "  ue-copy Scene1 Scene2                        # Copy multiple scenes"
    echo ""
    echo "Or use app.py directly:"
    echo "  python app.py --help"
    echo "  python app.py download_scene --scene Seaside_Town"
    echo ""
}

ue-help

echo ""
echo "========================================"
echo "Functions loaded! You can now use:"
echo "  ue-bake, ue-sequence, ue-render,"
echo "  ue-export, ue-upload, ue-download, ue-copy"
echo "========================================"
echo ""
