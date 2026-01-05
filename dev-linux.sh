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

# 3. Change to ue_pipeline directory
echo "Changing working directory..."
cd "$UE_PIPELINE_DIR" || exit
echo "  OK Current directory: $UE_PIPELINE_DIR"

echo ""
echo "========================================"
echo "  Environment Ready!"
echo "========================================"
echo ""

# Define shortcut functions
ue-bake() {
    if [ $# -eq 0 ]; then
        python3 app.py bake_navmesh --manifest examples/job_bake.json
    elif [ "$1" = "--manifest" ]; then
        python3 app.py bake_navmesh --manifest "$2"
    else
        python3 app.py bake_navmesh --manifest "$1"
    fi
}

ue-sequence() {
    if [ $# -eq 0 ]; then
        python3 app.py create_sequence --manifest examples/job_sequence_analysis.json
    elif [ "$1" = "--manifest" ]; then
        python3 app.py create_sequence --manifest "$2"
    else
        python3 app.py create_sequence --manifest "$1"
    fi
}

ue-render() {
    if [ $# -eq 0 ]; then
        python3 app.py render --manifest examples/job_render.json
    elif [ "$1" = "--manifest" ]; then
        python3 app.py render --manifest "$2"
    else
        python3 app.py render --manifest "$1"
    fi
}

ue-export() {
    if [ $# -eq 0 ]; then
        python3 app.py export --manifest examples/job_export.json
    elif [ "$1" = "--manifest" ]; then
        python3 app.py export --manifest "$2"
    else
        python3 app.py export --manifest "$1"
    fi
}

ue-upload() {
    python3 app.py upload_scenes
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
    echo "  ue-sequence                                   # Use default config"
    echo "  ue-sequence examples/job_sequence_cameraman.json  # Specify config file"
    echo "  ue-sequence --manifest examples/job_sequence_cameraman.json  # Also works"
    echo ""
    echo "Or use app.py directly:"
    echo "  python3 app.py --help"
    echo "  python3 app.py create_sequence --manifest examples/job_sequence_analysis.json"
    echo ""
}

# Show help
ue-help

echo ""
echo "========================================"
echo "Functions loaded! You can now use:"
echo "  ue-bake, ue-sequence, ue-render, etc."
echo "========================================"
echo ""
