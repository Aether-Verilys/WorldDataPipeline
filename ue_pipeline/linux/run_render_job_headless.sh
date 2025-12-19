#!/bin/bash
# UE Render Job Executor (Headless Mode) for Linux
# Execute a render job using command-line MRQ execution

# ============================================================
# Configuration
# ============================================================

# Default paths (used if not specified in manifest)
DEFAULT_UE_EDITOR="/opt/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd"
DEFAULT_PROJECT="/home/user/Projects/NorthernForest/NorthernForest.uproject"

# ============================================================

echo "========================================"
echo "UE Render Job Executor (Headless Mode)"
echo "========================================"
echo ""

# Check if manifest path is provided
if [ -z "$1" ]; then
    echo "ERROR: Manifest path not provided"
    echo "Usage: $0 <manifest_path>"
    exit 1
fi

MANIFEST_PATH="$1"

# Convert to absolute path
MANIFEST_PATH="$(realpath "$MANIFEST_PATH")"

# Check manifest file
if [ ! -f "$MANIFEST_PATH" ]; then
    echo "ERROR: Manifest file not found: $MANIFEST_PATH"
    exit 1
fi

# Parse manifest using jq (JSON parser)
if ! command -v jq &> /dev/null; then
    echo "ERROR: jq is not installed. Please install it: sudo apt-get install jq"
    exit 1
fi

# Read manifest fields
JOB_ID=$(jq -r '.job_id' "$MANIFEST_PATH")
JOB_TYPE=$(jq -r '.job_type' "$MANIFEST_PATH")

if [ "$JOB_TYPE" != "render" ]; then
    echo "ERROR: Invalid job type '$JOB_TYPE', expected 'render'"
    exit 1
fi

# Read UE paths from manifest or use defaults
UE_EDITOR=$(jq -r '.ue_config.editor_path // empty' "$MANIFEST_PATH")
if [ -z "$UE_EDITOR" ]; then
    UE_EDITOR="$DEFAULT_UE_EDITOR"
    echo "WARNING: No editor_path in manifest, using default: $UE_EDITOR"
else
    # Replace UnrealEditor.exe with UnrealEditor-Cmd for headless mode (only if not already -Cmd)
    if [[ "$UE_EDITOR" == *"UnrealEditor.exe"* ]]; then
        UE_EDITOR="${UE_EDITOR/UnrealEditor.exe/UnrealEditor-Cmd}"
    fi
fi

PROJECT=$(jq -r '.ue_config.project_path // empty' "$MANIFEST_PATH")
if [ -z "$PROJECT" ]; then
    PROJECT="$DEFAULT_PROJECT"
    echo "WARNING: No project_path in manifest, using default: $PROJECT"
fi

# Get render configuration
SEQUENCE=$(jq -r '.sequence' "$MANIFEST_PATH")
MAP=$(jq -r '.map' "$MANIFEST_PATH")
CONFIG_PRESET=$(jq -r '.rendering.preset' "$MANIFEST_PATH")
OUTPUT_PATH=$(jq -r '.rendering.output_path' "$MANIFEST_PATH")

echo "Job ID:       $JOB_ID"
echo "Sequence:     $SEQUENCE"
echo "Map:          $MAP"
echo "Config:       $CONFIG_PRESET"
echo "Output:       $OUTPUT_PATH"
echo "UE Editor:    $UE_EDITOR"
echo "Project:      $PROJECT"
echo ""

# Check required files
if [ ! -f "$UE_EDITOR" ]; then
    echo "ERROR: UE Editor not found at: $UE_EDITOR"
    exit 1
fi

if [ ! -f "$PROJECT" ]; then
    echo "ERROR: Project not found at: $PROJECT"
    exit 1
fi

# Get project directory and ensure necessary directories exist
PROJECT_DIR=$(dirname "$PROJECT")
echo "Project directory: $PROJECT_DIR"

# Create Intermediate, Saved, and other necessary directories
mkdir -p "$PROJECT_DIR/Intermediate"
mkdir -p "$PROJECT_DIR/Saved"
mkdir -p "$PROJECT_DIR/Saved/Logs"

# Check write permissions
if [ ! -w "$PROJECT_DIR" ]; then
    echo "ERROR: No write permission for project directory: $PROJECT_DIR"
    exit 1
fi

# Ensure output directory exists
if [ -n "$OUTPUT_PATH" ]; then
    mkdir -p "$OUTPUT_PATH"
    echo "Output directory ready: $OUTPUT_PATH"
fi

# Get Python worker script path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Go up one level to find python directory (since script is in linux/ subdirectory)
PYTHON_WORKER="$SCRIPT_DIR/../python/worker_render.py"

if [ ! -f "$PYTHON_WORKER" ]; then
    echo "ERROR: Python worker script not found: $PYTHON_WORKER"
    exit 1
fi

echo "Starting headless render job..."
echo ""

# Set manifest path as environment variable for Python script to read
export UE_RENDER_MANIFEST="$MANIFEST_PATH"
echo "Manifest Path: $MANIFEST_PATH"

# Build UE command-line arguments
UE_ARGS=(
    "$PROJECT"
    
    # Execute Python script that calls MRQ API internally
    "-ExecutePythonScript=\"$PYTHON_WORKER\""
    
    # Rendering optimization flags for headless mode
    "-RenderOffscreen"
    
    # Resolution settings
    "-ResX=1920"
    "-ResY=1080"
    "-ForceRes"
    
    # Headless/automation flags
    "-Windowed"
    "-NoLoadingScreen"
    "-NoScreenMessages"
    "-NoSplash"
    "-Unattended"
    "-NoSound"
    "-AllowStdOutLogVerbosity"
    
    # Logging
    "-log"
    "-stdout"
    "-FullStdOutLogOutput"
    "LOG=RenderLog_${JOB_ID}.txt"
)

echo "Command: $UE_EDITOR ${UE_ARGS[@]}"
echo ""
echo "----------------------------------------"

# Launch UE
"$UE_EDITOR" "${UE_ARGS[@]}"
EXIT_CODE=$?

echo ""
echo "----------------------------------------"

if [ $EXIT_CODE -eq 0 ]; then
    echo "Render job completed successfully"
    exit 0
else
    echo "Render job failed with exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
