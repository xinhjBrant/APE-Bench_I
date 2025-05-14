#!/bin/bash

# --- Configuration ---
# TODO: User should customize these paths and settings
# Ensure this script is run from the root of the APE-Bench_I project.

# Path to your local clone of the mathlib4 repository.
# Eleanstic (src/eleanstic/config.yaml) must also be configured to point to this path.
MATHLIB_REPO_PATH="./mathlib4"

# Path to the directory where the APE-Bench_I dataset (from Hugging Face) is cloned.
APE_BENCH_DATASET_DIR="./datasets"

# Specific APE-Bench dataset file (e.g., .parquet) to be used for the benchmark.
# This path should also be set in the main APE-Bench configuration file below.
APE_BENCH_DATASET_FILE="${APE_BENCH_DATASET_DIR}/ape_bench1_test.parquet"

# Main APE-Bench configuration file.
# Ensure its 'project.input_file' points to APE_BENCH_DATASET_FILE.
CONFIG_FILE="configs/config.yaml"

# Eleanstic configuration file.
# Ensure its 'paths.mathlib_repo' points to MATHLIB_REPO_PATH.
ELEANSTIC_CONFIG_FILE="src/eleanstic/config.yaml"

# --- 1. Setup: Clone repositories (if not already present) ---
echo "Step 1: Setting up repositories..."

# Clone Mathlib4
if [ ! -d "$MATHLIB_REPO_PATH" ]; then
    echo "Cloning mathlib4 to $MATHLIB_REPO_PATH..."
    git clone https://github.com/leanprover-community/mathlib4.git "$MATHLIB_REPO_PATH"
    if [ $? -ne 0 ]; then echo "Failed to clone mathlib4. Exiting."; exit 1; fi
else
    echo "Mathlib4 repository found at $MATHLIB_REPO_PATH."
fi

# Clone APE-Bench_I dataset
if [ ! -d "$APE_BENCH_DATASET_DIR" ]; then
    echo "Creating datasets directory..."
    mkdir -p "$APE_BENCH_DATASET_DIR"
fi

if [ ! -f "$APE_BENCH_DATASET_FILE" ]; then
    echo "Cloning APE-Bench_I dataset to $APE_BENCH_DATASET_DIR..."
    git clone https://huggingface.co/datasets/HuajianXin/APE-Bench_I "$APE_BENCH_DATASET_DIR"
    if [ $? -ne 0 ]; then echo "Failed to clone APE-Bench_I dataset. Exiting."; exit 1; fi
else
    echo "APE-Bench dataset file $APE_BENCH_DATASET_FILE already exists."
fi

echo "Repository setup complete."
echo "---------------------------------------------------------------------"

# --- 2. Eleanstic Build (Preprocessing Mathlib Commits) ---
# This step preprocesses all Mathlib commits referenced in the target APE-Bench dataset file.
# It uses Eleanstic and can be time-consuming for the first run.

echo "Step 2: Eleanstic Build..."
echo "IMPORTANT: Ensure Eleanstic configuration ($ELEANSTIC_CONFIG_FILE) is correct, especially 'paths.mathlib_repo'."
echo "This will build Eleanstic data for commits in: $APE_BENCH_DATASET_FILE"

# Assuming the parquet file contains a column named 'commit' for commit hashes.
# Adjust --commit_id_key if your parquet uses a different column name for commit SHAs.
python -m src.eleanstic.main build \
    --config "$ELEANSTIC_CONFIG_FILE" \
    --input_file "$APE_BENCH_DATASET_FILE" \
    --commit_id_key commit # Default key in APE-Bench datasets
    # --max_workers <num_processes> # Optional: adjust based on your system

if [ $? -ne 0 ]; then echo "Eleanstic build failed. Exiting."; exit 1; fi
echo "Eleanstic build complete."
echo "---------------------------------------------------------------------"

# --- 3. Run APE-Bench Pipeline Scripts ---
# These scripts use the main APE-Bench configuration file ($CONFIG_FILE).
# Ensure $CONFIG_FILE is correctly set up, especially:
#   project.input_file: should point to $APE_BENCH_DATASET_FILE
#   generation, verification, judgement sections as per your needs.

echo "Step 3.1: Generating Patches (using $CONFIG_FILE)..."
python -m src.apebench.scripts.1_generate_patches --config "$CONFIG_FILE"
if [ $? -ne 0 ]; then echo "Patch generation failed. Exiting."; exit 1; fi
echo "Patch generation complete."
echo "---------------------------------------------------------------------"


echo "Step 3.2: Verifying Patches (using $CONFIG_FILE)..."
python -m src.apebench.scripts.2_verify_patches --config "$CONFIG_FILE"
if [ $? -ne 0 ]; then echo "Patch verification failed. Exiting."; exit 1; fi
echo "Patch verification complete."
echo "---------------------------------------------------------------------"


echo "Step 3.3: Evaluating Patches (using $CONFIG_FILE)..."
python -m src.apebench.scripts.3_evaluate_patches --config "$CONFIG_FILE"
if [ $? -ne 0 ]; then echo "Patch evaluation failed. Exiting."; exit 1; fi
echo "Patch evaluation complete."
echo "---------------------------------------------------------------------"


echo "APE-Bench pipeline finished successfully!"
echo "Check the 'outputs/' directory for results."

# --- Optional: Rebuilding Data from Scratch ---
# If you need to regenerate the APE-Bench dataset itself (e.g., from new Mathlib commits),
# you can use the 0_collect_data.py script. This is an advanced step.
# echo ""
# echo "Optional: To rebuild the APE-Bench dataset from scratch, inspect and run:"
# echo "# python -m src.apebench.scripts.0_collect_data --config $CONFIG_FILE --repo_path $MATHLIB_REPO_PATH ... (other args)"

exit 0 