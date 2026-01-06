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
        python app.py bake_navmesh --manifest ue_pipeline/examples/job_bake.json
    elif [ "$1" = "--manifest" ]; then
        python app.py bake_navmesh --manifest "$2"
    else
        python app.py bake_navmesh --manifest "$1"
    fi
}

ue-sequence() {
    if [ $# -eq 0 ]; then
        python app.py create_sequence --manifest ue_pipeline/examples/job_sequence.json
    elif [ "$1" = "--manifest" ]; then
        python app.py create_sequence --manifest "$2"
    else
        python app.py create_sequence --manifest "$1"
    fi
}

ue-render() {
    if [ $# -eq 0 ]; then
        python app.py render --manifest ue_pipeline/examples/job_render.json
    elif [ "$1" = "--manifest" ]; then
        python app.py render --manifest "$2"
    else
        python app.py render --manifest "$1"
    fi
}

ue-export() {
    if [ $# -eq 0 ]; then
        python app.py export --manifest ue_pipeline/examples/job_export.json
    elif [ "$1" = "--manifest" ]; then
        python app.py export --manifest "$2"
    else
        python app.py export --manifest "$1"
    fi
}

ue-upload() {
    python app.py upload_scenes
}

ue-help() {
    echo ""
    echo "Available shortcut commands:"
    echo "  ue-bake       - Bake NavMesh"
    echo "  ue-sequence   - Create sequences"
    echo "  ue-render     - Render"
    echo "  ue-export     - Export"
    echo "  ue-upload     - Upload scenes"
    echo "  ue-help       - Show this help"
    echo ""
    echo "Examples:"
    echo "  ue-sequence                                            # Use default config"
    echo "  ue-sequence ue_pipeline/examples/job_sequence.json     # Specify config file"
    echo "  ue-sequence --manifest ue_pipeline/examples/job_sequence.json  # Also works"
    echo ""
    echo "Or use app.py directly:"
    echo "  python app.py --help"
    echo "  python app.py create_sequence --manifest ue_pipeline/examples/job_sequence.json"
    echo ""
}

ue-help

echo ""
echo "========================================"
echo "Functions loaded! You can now use:"
echo "  ue-bake, ue-sequence, ue-render, etc."
echo "========================================"
echo ""
