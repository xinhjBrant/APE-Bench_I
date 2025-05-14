[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# Eleanstic: Efficient Version-Aware Lean Verification Environment

Eleanstic is a sophisticated system designed for managing and utilizing multiple versions of the Mathlib4 formal mathematics library. Its primary purpose is to provide an efficient backend for the syntactic verification of Lean code patches against specific, historical Mathlib commit states, as required by benchmarks like APE-Bench I.

It tackles the challenge of prohibitive computational and storage costs associated with naively building and maintaining numerous Mathlib versions by implementing a content-addressable storage (CAS) system for build artifacts and a snapshotting mechanism for quick environment restoration.

## 1. Core Design Philosophy

The core idea behind Eleanstic is to **decouple the expensive, stateful Mathlib build process from the lightweight, stateless Lean file verification process.**

*   **Build Once, Store Smartly**: Each required Mathlib commit is fully built only once. Its build artifacts (primarily the `.lake` directory) are then "collapsed" into a space-efficient representation.
*   **Content-Addressable Storage (CAS)**: Instead of storing entire `.lake` directories for each commit, Eleanstic stores each unique file from these directories just once in a central CAS. Files are identified by the hash of their content (SHA256 by default).
*   **Snapshots (File Maps)**: For each processed commit, a compact binary "snapshot" (or file map) is created. This map stores the directory structure of the original `.lake` (and potentially other necessary files) and links each file path to its corresponding hash in the CAS.
*   **Rapid Restoration**: When verification is needed for a specific commit, Eleanstic uses its snapshot to quickly reconstruct the necessary build environment in an isolated, temporary worktree by fetching the required files from the CAS.
*   **Parallelism**: Eleanstic is designed to perform many of its operations in parallel, including preprocessing multiple commits, restoring files, and verifying Lean code snippets.

This approach drastically reduces disk space requirements (as reported in the APE-Bench I paper, from 15.6 TB to 1.1 TB for thousands of commits) and allows for near-instantaneous setup of versioned Lean environments for verification.

## 2. Key Components and Modules

Eleanstic's functionality is primarily implemented within the `src/eleanstic/` directory:

*   **Configuration (`core/config.py`, `config.yaml`)**:
    *   **`config.yaml`**: The main static configuration file where users define paths (Mathlib repo, storage directories, logs), concurrency limits, hashing algorithms, cache settings, etc.
    *   **`core/config.py`**: Defines Pydantic models (`PathsConfig`, `StorageConfig`, `ConcurrencyConfig`, etc., aggregated into a main `Config` model) to load, validate, and provide typed access to the settings from `config.yaml`. A `ConfigManager` singleton ensures global access to configuration.

*   **Main Orchestration (`main.py`)**:
    *   Provides the command-line interface (CLI) for Eleanstic using `argparse`.
    *   Supports two primary subcommands:
        *   `build`: For preprocessing Mathlib commits (building, snapshotting).
        *   `verify`: For verifying Lean code snippets against preprocessed commit environments.
    *   Manages parallelism using `concurrent.futures.ProcessPoolExecutor` to distribute work (e.g., building or verifying different commits) across multiple processes.
    *   Handles input data (lists of commits, Lean records for verification) typically from JSONL or CSV files.
    *   Initializes and dispatches tasks to `BuildCoordinator` or `VerifyCoordinator`.

*   **Coordinators (`core/coordinators.py`)**:
    *   **`BuildCoordinator`**:
        *   **Purpose**: Manages the "preprocessing" lifecycle of a Mathlib commit.
        *   **Workflow**:
            1.  Creates a temporary Git worktree for the specified commit from the local Mathlib repository.
            2.  Downloads pre-compiled dependencies using `lake exe cache get` (utilizing a shared cache directory configured by `XDG_CACHE_HOME`).
            3.  Executes `lake build` to compile Mathlib for that commit.
            4.  Invokes `store_worktree_directory()`:
                *   Iterates through files in the built `.lake` directory.
                *   Hashes each file (content for regular files, target path for symlinks) via `FileMapManager`.
                *   Stores unique file contents into the CAS via `FileMapManager`.
                *   Creates a binary snapshot (file map) of the `.lake` structure and its file hashes using `FileMapManager.store_file_mapping()`.
            5.  Optionally (if `remove_worktree_after_build` is true), cleans up the original `.lake` directory from the temporary worktree to save space.
            6.  Updates the commit's status using `CommitStatus`.
    *   **`VerifyCoordinator`**:
        *   **Purpose**: Manages the verification of Lean code against a specific, preprocessed Mathlib commit.
        *   **Workflow**:
            1.  Calls `restore_worktree_directory()`:
                *   Retrieves the binary snapshot (file map) for the commit using `FileMapManager.get_file_mapping()`.
                *   Reconstructs the original `.lake` directory structure in a new temporary worktree by copying files from the CAS based on the snapshot, using `FileMapManager.restore_file()`. This is often parallelized.
            2.  Performs an "integrity build" by running `lake build` on the restored worktree to ensure it's a valid environment.
            3.  For each Lean code snippet provided (e.g., a patched file from APE-Bench):
                *   Uses `lean_utils.verify_with_lean()`: This function writes the code to a temporary `.lean` file within the restored worktree and invokes `lake env lean <temp_file.lean>` for compilation and verification.
                *   Verification of multiple snippets can be parallelized using `ThreadPoolExecutor`.
            4.  Records detailed results (pass/fail, compiler output) to a JSONL file.

*   **File Mapping & Storage (`core/file_map.py`)**:
    *   **`FileMapManager`**:
        *   Manages the CAS:
            *   `compute_file_hash()`: Calculates SHA256 (or xxhash64) for files.
            *   `get_storage_path()`: Determines the path in the CAS based on the hash (e.g., `storage/fa/ce/face...`).
            *   `store_file()` (implicitly used by `BuildCoordinator` when storing unique contents, though not a direct public method of `FileMapManager` itself, it relies on the hash to place files in CAS).
        *   Manages Snapshots (File Maps):
            *   `store_file_mapping()`: Serializes the list of (relative_path, hash, type) entries for a commit's `.lake` into a compact binary `.bin` file.
            *   `get_file_mapping()`: Deserializes this binary file back into a dictionary.
        *   Manages File Restoration:
            *   `restore_file()`: Copies a file (identified by hash and type) from the CAS to a specified destination path, creating symlinks appropriately.

*   **Commit Status (`core/status.py`)**:
    *   **`CommitStatus`**: Likely manages the state of each commit (e.g., `PENDING`, `BUILDING`, `COLLAPSED` (built and snapshotted), `READY` (restored and verified buildable), `FAILED_BUILD`, `FAILED_VERIFY`). This state is probably persisted to disk (e.g., in the `status_dir` defined in `PathsConfig`).

*   **Utilities (`utils/`)**:
    *   **`lean_utils.py`**:
        *   `run_command()`: Generic subprocess execution.
        *   `run_lake_build()`: Wrapper for `lake build`.
        *   `verify_with_lean()`: Core function to compile a temporary Lean file within a worktree.
        *   `parse_lean_output()`: Structures Lean compiler messages.
    *   **`sys_utils.py`**: System utilities, e.g., `find_and_kill_processes` for cleanup.
    *   **`log_utils.py`**: Configures logging for the system.

## 3. Data Flow and Lifecycle

### A. Preprocessing Phase (`build` command)

1.  **Input**: A list of Mathlib commit SHAs (e.g., from a JSONL or CSV file specified by `--input_file`). Configuration from `config.yaml`.
2.  **Orchestration**: `main.py` reads the commits and distributes `build_commit` tasks to `BuildCoordinator` instances running in parallel processes.
3.  **For each commit (`BuildCoordinator.build_commit`)**:
    a.  A fresh Git worktree for the commit is created.
    b.  Lake cache (`lake exe cache get`) is populated for the worktree.
    c.  `lake build` is executed for the worktree.
    d.  If successful, the `.lake` directory is traversed:
        i.  Files are hashed.
        ii. Unique file contents are copied to the CAS (e.g., `storage/ab/cd/<hash>`).
        iii. A binary snapshot (`<commit_id>.bin` in `file_maps/`) is created, mapping relative paths in `.lake` to their content hashes and types.
    e.  The original `.lake` directory in the worktree is (optionally) deleted.
    f.  The commit's status is updated (e.g., to `STATUS_COLLAPSED`).
4.  **Output**: A populated CAS and a set of snapshot files. Status files indicating build success/failure.

### B. Verification Phase (`verify` command)

1.  **Input**:
    *   A list of verification tasks (e.g., from a JSONL file via `--input_file`). Each task specifies a `commit_id` and contains one or more Lean code snippets to verify (e.g., `code_key: "patched_lean_code"`).
    *   Configuration from `config.yaml`.
    *   Path to Eleanstic's CAS and snapshots (from config).
2.  **Orchestration**: `main.py` reads the verification tasks, groups them by `commit_id`, and distributes `verify_commit` tasks to `VerifyCoordinator` instances running in parallel processes.
3.  **For each commit (`VerifyCoordinator.verify_commit`)**:
    a.  **Environment Restoration (`restore_worktree_directory`)**:
        i.  The snapshot (`<commit_id>.bin`) is loaded.
        ii. A new temporary worktree is created.
        iii. The `.lake` directory (and other snapshotted files) are reconstructed in this worktree by copying files from the CAS according to the snapshot. This is often done with parallel file copying.
    b.  **Integrity Check**: `lake build` is run on the restored worktree to ensure it's a valid and functional Lean environment.
    c.  **Lean Code Verification**:
        i.  For each Lean code snippet associated with this commit:
            *   `lean_utils.verify_with_lean()` is called.
            *   The snippet is written to a temporary `.lean` file inside the restored worktree.
            *   `lake env lean <temp_file.lean>` is executed to compile it.
            *   The result (pass/fail, errors, warnings, compiler output) is captured.
        ii. This verification can be done in parallel for multiple snippets using a thread pool.
    d.  The commit's status is updated (e.g., to `STATUS_READY` or `STATUS_FAILED_VERIFY`).
4.  **Output**: JSONL files in `--results_dir`, where each line contains the original input record augmented with the detailed `verification_result` for each Lean code snippet.

## 4. Usage Instructions

This section details how to use Eleanstic for both preprocessing Mathlib commits and verifying Lean code.

### A. Initial Setup (One-Time Preprocessing - `build` command)

1.  **Configuration**:
    *   Ensure you have a local clone of the `leanprover-community/mathlib4` repository.
    *   Edit `src/eleanstic/config.yaml`:
        *   Set `paths.mathlib_repo` to the path of your Mathlib4 clone.
        *   Set `paths.worktree_dir`, `paths.storage_dir` (for CAS), `paths.cache_dir` (for `lake exe cache get`), `paths.log_dir`, and `status_dir` under `paths.workspace_root` to desired locations. Ensure these locations have ample disk space.
        *   Adjust `concurrency.max_workers` based on your system's capabilities.
2.  **Prepare Input File for `build`**: Create a file (e.g., `commits_to_build.jsonl` or `commits_to_build.csv`) listing the Mathlib commit SHAs that need to be preprocessed. Each line/record should contain the commit SHA under a key (default `commit_hash`, configurable via `--commit_id_key` argument for the `build` command). If specific Lean toolchains are needed per commit, include them under a `toolchain_content` key.
    *Example `commits_to_build.jsonl`*:
    ```json
    {"commit_hash": "abcdef123456...", "toolchain_content": "leanprover/lean4:v4.7.0"}
    {"commit_hash": "fedcba654321...", "toolchain_content": "leanprover/lean4:v4.8.0"}
    ```
3.  **Run Preprocessing (`build` command)**:
    ```bash
    python -m src.eleanstic.main build \
        --config src/eleanstic/config.yaml \
        --input_file /path/to/commits_to_build.jsonl \
        --commit_id_key commit_hash \
        --max_workers <num_processes>
    ```
    *   Optionally add `--force` to rebuild commits even if they have a `STATUS_COLLAPSED` status.
    *   This step will take a significant amount of time, depending on the number of commits and system performance. Monitor logs in the configured `log_dir`.

### B. Verifying Lean Code Patches (`verify` command)

Eleanstic's `verify` command can process input in two main formats for JSONL files, determined by the presence and value of the `--lean_records_key` argument. The `--code_key` argument (default: `"code"`) specifies the key holding the Lean code string within each individual record to be verified. The `--commit_id_key` argument (default: `"commit_hash"`) specifies the key holding the commit SHA.

1.  **Ensure Preprocessing is Done**: The Mathlib commits against which you want to verify must have been successfully preprocessed by the `build` command.
2.  **Prepare Input File for `verify`**:

    *   **Option 1: Flat JSONL Format (Each line is a single verification task)**
        *   In this format, each JSON line is a self-contained record holding both the commit identifier and the code to verify.
        *   When using this format, you **do not** provide the `--lean_records_key` argument to the `verify` command.
        *Example `patches_to_verify_flat.jsonl`*:
        ```json
        {"task_id": "t1", "commit_hash": "abcdef123456...", "code": "theorem foo : True := by trivial"}
        {"task_id": "t2", "commit_hash": "abcdef123456...", "code": "def bar := 1\\n#print bar"}
        {"task_id": "t3", "commit_hash": "fedcba654321...", "code": "theorem baz : 1 + 1 = 2 := rfl"}
        ```
        *Run Verification Command (Flat Format)*:
        ```bash
        python -m src.eleanstic.main verify \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/patches_to_verify_flat.jsonl \
            --commit_id_key commit_hash \
            --code_key code \
            --results_dir /path/to/verification_outputs \
            --max_workers <num_processes>
        ```

    *   **Option 2: Grouped JSONL Format (Each line contains a commit and a list of tasks)**
        *   In this format, each JSON line contains a commit identifier and then, under a specified key, a list of records to be verified against that commit.
        *   When using this format, you **must** provide the `--lean_records_key` argument to the `verify` command, specifying the key that holds the list of task records (e.g., `patches_data`).
        *Example `patches_to_verify_grouped.jsonl`*:
        ```json
        {"benchmark_id": "b1", "commit_hash": "abcdef123456...", "patches_data": [{"id": "task1", "code": "theorem foo : True := by trivial"}, {"id": "task2", "code": "def bar := 1\\n#print bar"}]}
        {"benchmark_id": "b2", "commit_hash": "fedcba654321...", "patches_data": [{"id": "task3", "code": "theorem baz : 1 + 1 = 2 := rfl"}]}
        ```
        *Run Verification Command (Grouped Format)*:
        ```bash
        python -m src.eleanstic.main verify \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/patches_to_verify_grouped.jsonl \
            --commit_id_key commit_hash \
            --lean_records_key patches_data \
            --code_key code \
            --results_dir /path/to/verification_outputs \
            --max_workers <num_processes>
        ```
    *   Results will be written as JSONL files (one per unique commit ID) in the specified `--results_dir`. Each output line will be the original input record (or sub-record in the grouped case) augmented with a `verification_result` object.

## 5. Interaction with APE-Bench

Eleanstic serves as the syntactic verification backend for the APE-Bench I framework. The `src/apebench/evaluation_pipelines/verification_manager.py` script orchestrates the verification process.

Here's how they interact:

1.  **Patch Generation**: APE-Bench's inference pipeline generates potential patches for various tasks. These results are typically stored in multiple JSONL files, where each file might correspond to a specific model or a batch of tasks.
2.  **Data Preparation for Eleanstic**:
    *   The `verification_manager.py` script in APE-Bench calls `src.apebench.evaluation_pipelines.gather_results` with the `--pipeline patch` argument.
    *   This `gather_results` utility collects all the generated patch data from various input files and transforms it into a **single, flat JSONL file** (e.g., `patches_for_verification_{timestamp}.jsonl`).
    *   Each line in this flat file represents one verification task and contains all necessary information, including the `commit_hash` and the Lean `code` snippet (patch).
    *   *Example line prepared by APE-Bench for Eleanstic*:
        ```json
        {"task_id": "some_unique_id", "commit_hash": "abcdef123...", "code": "theorem T : True := by trivial", "model_name": "gpt-4", ...}
        ```
3.  **Eleanstic Invocation by APE-Bench**:
    *   `verification_manager.py` then invokes `src.eleanstic.main verify` using this flat JSONL file.
    *   The command used by APE-Bench is structured as follows (defaults for `--commit_id_key` and `--code_key` are often relied upon if they are `commit_hash` and `code` respectively):
        ```bash
        python -m src.eleanstic.main verify \
            --config /path/to/eleanstic_config.yaml \
            --input_file /path/to/temp_dir/patches_for_verification_{timestamp}.jsonl \
            --commit_id_key "commit_hash" \
            --code_key "code" \
            --results_dir /path/to/apebench_verification_outputs/results_{timestamp} \
            --max_workers <num_workers_from_apebench_config>
        ```
    *   Note: APE-Bench uses the **flat input format** for Eleanstic, so it does not use the `--lean_records_key` argument when calling Eleanstic.
4.  **Result Collection by APE-Bench**:
    *   Eleanstic processes these flat records and writes its output (original records + `verification_result`) to the directory specified by `--results_dir`, creating one JSONL file per unique commit.
    *   `verification_manager.py` then again calls `src.apebench.evaluation_pipelines.gather_results`, this time with `--pipeline verification`, to collect all these individual output files from Eleanstic into a single consolidated `verification_results_{timestamp}.jsonl` file. This file is then used for further analysis and metric calculation within APE-Bench.

This workflow ensures that APE-Bench can efficiently verify a large number of patches against diverse Mathlib versions using Eleanstic's specialized capabilities.

## 6. Customization and Secondary Development

*   **Configuration**: Modify `config.yaml` and `core/config.py` to add new parameters.
*   **Storage Backend**: `FileMapManager` could be adapted to use different storage systems (e.g., cloud storage, different database for file maps) though this would be a major change.
*   **Build Process**: `BuildCoordinator` and `lean_utils.py` can be modified if the Mathlib build process changes or if different build tools need support.
*   **Verification Logic**: `VerifyCoordinator` and `lean_utils.verify_with_lean` can be extended for more nuanced verification (e.g., specific linter checks, resource profiling).
*   **Parallelism**: Concurrency settings in `config.yaml` and the use of `ProcessPoolExecutor`/`ThreadPoolExecutor` in `main.py` and `coordinators.py` can be tuned or adapted.

---
<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# Eleanstic：高效的、版本感知的 Lean 验证环境

Eleanstic 是一个为管理和利用 Mathlib4 形式化数学库的多个版本而设计的复杂系统。其主要目的是为 Lean 代码补丁针对特定的、历史的 Mathlib 提交状态进行语法验证提供高效的后端，正如 APE-Bench I 等基准测试所要求的那样。

它通过为构建产物实现内容寻址存储 (CAS) 系统和用于快速环境恢复的快照机制，解决了因天真地构建和维护众多 Mathlib 版本而带来的高昂计算和存储成本的挑战。

## 1. 核心设计理念

Eleanstic 背后的核心思想是**将昂贵的、有状态的 Mathlib 构建过程与轻量级的、无状态的 Lean 文件验证过程解耦。**

*   **一次构建，智能存储**：每个所需的 Mathlib 提交仅完整构建一次。其构建产物（主要是 `.lake` 目录）随后被"折叠"成节省空间的表示形式。
*   **内容寻址存储 (CAS)**：Eleanstic 不会为每个提交存储整个 `.lake` 目录，而是在中央 CAS 中仅存储这些目录中每个唯一文件一次。文件通过其内容哈希（默认为 SHA256）进行识别。
*   **快照（文件映射）**：为每个处理过的提交创建一个紧凑的二进制"快照"（或文件映射）。此映射存储原始 `.lake`（以及可能需要的其他文件）的目录结构，并将每个文件路径链接到其在 CAS 中的相应哈希。
*   **快速恢复**：当需要针对特定提交进行验证时，Eleanstic 使用其快照通过从 CAS 中获取所需文件，在隔离的临时工作树中快速重建必要的构建环境。
*   **并行性**：Eleanstic 设计用于并行执行其许多操作，包括预处理多个提交、恢复文件和验证 Lean 代码片段。

这种方法极大地减少了磁盘空间需求（正如 APE-Bench I 论文所报告的，对于数千个提交，从 15.6 TB 减少到 1.1 TB），并允许近乎即时地设置版本化的 Lean 环境以进行验证。

## 2. 关键组件和模块

Eleanstic 的功能主要在 `src/eleanstic/` 目录中实现：

*   **配置 (`core/config.py`, `config.yaml`)**：
    *   **`config.yaml`**：主要的静态配置文件，用户在此定义路径（Mathlib 仓库、存储目录、日志）、并发限制、哈希算法、缓存设置等。
    *   **`core/config.py`**：定义 Pydantic 模型（`PathsConfig`、`StorageConfig`、`ConcurrencyConfig` 等，聚合到主 `Config` 模型中）以加载、验证并提供对 `config.yaml` 中设置的类型化访问。`ConfigManager` 单例确保对配置的全局访问。

*   **主编排 (`main.py`)**：
    *   使用 `argparse` 为 Eleanstic 提供命令行界面 (CLI)。
    *   支持两个主要的子命令：
        *   `build`：用于预处理 Mathlib 提交（构建、快照）。
        *   `verify`：用于针对预处理的提交环境验证 Lean 代码片段。
    *   使用 `concurrent.futures.ProcessPoolExecutor` 管理并行性，以在多个进程之间分配工作（例如，构建或验证不同的提交）。
    *   处理通常来自 JSONL 或 CSV 文件的输入数据（提交列表、用于验证的 Lean 记录）。
    *   初始化任务并将其分派给 `BuildCoordinator` 或 `VerifyCoordinator`。

*   **协调器 (`core/coordinators.py`)**：
    *   **`BuildCoordinator`**：
        *   **目的**：管理 Mathlib 提交的"预处理"生命周期。
        *   **工作流**：
            1.  从本地 Mathlib 存储库为指定的提交创建一个临时的 Git 工作树。
            2.  使用 `lake exe cache get` 下载预编译的依赖项（利用由 `XDG_CACHE_HOME` 配置的共享缓存目录）。
            3.  执行 `lake build` 为该提交编译 Mathlib。
            4.  调用 `store_worktree_directory()`：
                *   遍历构建的 `.lake` 目录中的文件。
                *   通过 `FileMapManager` 哈希每个文件（常规文件的内容，符号链接的目标路径）。
                *   通过 `FileMapManager` 将唯一的文件内容存储到 CAS 中。
                *   使用 `FileMapManager.store_file_mapping()` 创建 `.lake` 结构及其文件哈希的二进制快照（文件映射）。
            5.  可选地（如果 `remove_worktree_after_build` 为 true），从临时工作树中清除原始的 `.lake` 目录以节省空间。
            6.  使用 `CommitStatus` 更新提交的状态。
    *   **`VerifyCoordinator`**：
        *   **目的**：管理针对特定的、预处理的 Mathlib 提交验证 Lean 代码。
        *   **工作流**：
            1.  调用 `restore_worktree_directory()`：
                *   使用 `FileMapManager.get_file_mapping()` 检索提交的二进制快照（文件映射）。
                *   通过 `FileMapManager.restore_file()` 根据快照从 CAS 复制文件，在新的临时工作树中重建原始的 `.lake` 目录结构。这通常是并行化的。
            2.  通过在恢复的工作树上运行 `lake build` 来执行"完整性构建"，以确保它是一个有效的环境。
            3.  对于提供的每个 Lean 代码片段（例如，来自 APE-Bench 的修补文件）：
                *   使用 `lean_utils.verify_with_lean()`：此函数将代码写入恢复的工作树中的临时 `.lean` 文件，并调用 `lake env lean <temp_file.lean>` 进行编译和验证。
                *   可以使用线程池并行验证多个片段。
            4.  将详细结果（通过/失败、编译器输出）记录到 JSONL 文件中。

*   **文件映射与存储 (`core/file_map.py`)**：
    *   **`FileMapManager`**：
        *   管理 CAS：
            *   `compute_file_hash()`：计算文件的 SHA256（或 xxhash64）。
            *   `get_storage_path()`：根据哈希确定 CAS 中的路径（例如，`storage/fa/ce/face...`）。
            *   `store_file()`（由 `BuildCoordinator` 在存储唯一内容时隐式使用，尽管它不是 `FileMapManager` 本身的直接公共方法，但它依赖哈希将文件放入 CAS）。
        *   管理快照（文件映射）：
            *   `store_file_mapping()`：将提交的 `.lake` 的（relative_path、hash、type）条目列表序列化为紧凑的二进制 `.bin` 文件。
            *   `get_file_mapping()`：将此二进制文件反序列化回字典。
        *   管理文件恢复：
            *   `restore_file()`：将 CAS 中的文件（由哈希和类型标识）复制到指定的目标路径，并适当地创建符号链接。

*   **提交状态 (`core/status.py`)**：
    *   **`CommitStatus`**：可能管理每个提交的状态（例如，`PENDING`、`BUILDING`、`COLLAPSED`（已构建并快照）、`READY`（已恢复并验证可构建）、`FAILED_BUILD`、`FAILED_VERIFY`）。此状态可能持久化到磁盘（例如，在 `PathsConfig` 中定义的 `status_dir` 中）。

*   **实用程序 (`utils/`)**：
    *   **`lean_utils.py`**：
        *   `run_command()`：通用子流程执行。
        *   `run_lake_build()`：`lake build` 的包装器。
        *   `verify_with_lean()`：在工作树中编译临时 Lean 文件的核心函数。
        *   `parse_lean_output()`：构造 Lean 编译器消息。
    *   **`sys_utils.py`**：系统实用程序，例如用于清理的 `find_and_kill_processes`。
    *   **`log_utils.py`**：配置系统的日志记录。

## 3. 数据流和生命周期

### A. 预处理阶段（`build` 命令）

1.  **输入**：Mathlib 提交 SHA 列表（例如，来自 `--input_file` 指定的 JSONL 或 CSV 文件）。来自 `config.yaml` 的配置。
2.  **编排**：`main.py` 读取提交并将 `build_commit` 任务分配给在并行进程中运行的 `BuildCoordinator` 实例。
3.  **对于每个提交 (`BuildCoordinator.build_commit`)**：
    a.  为提交创建一个新的 Git 工作树。
    b.  为工作树填充 Lake 缓存 (`lake exe cache get`)。
    c.  为工作树执行 `lake build`。
    d.  如果成功，则遍历 `.lake` 目录：
        i.  文件被哈希处理。
        ii. 唯一的文件内容被复制到 CAS（例如，`storage/ab/cd/<hash>`）。
        iii. 创建一个二进制快照（`file_maps/` 中的 `<commit_id>.bin`），将 `.lake` 中的相对路径映射到其内容哈希和类型。
    e.  工作树中的原始 `.lake` 目录（可选）被删除。
    f.  提交的状态被更新（例如，更新为 `STATUS_COLLAPSED`）。
4.  **输出**：填充的 CAS 和一组快照文件。指示构建成功/失败的状态文件。

### B. 验证阶段（`verify` 命令）

1.  **输入**：
    *   验证任务列表（例如，来自通过 `--input_file` 指定的 JSONL 文件）。每个任务指定一个 `commit_id` 并包含一个或多个要验证的 Lean 代码片段（例如，`code_key: "patched_lean_code"`）。
    *   来自 `config.yaml` 的配置。
    *   Eleanstic 的 CAS 和快照的路径（来自配置）。
2.  **编排**：`main.py` 读取验证任务，按 `commit_id` 对其进行分组，并将 `verify_commit` 任务分配给在并行进程中运行的 `VerifyCoordinator` 实例。
3.  **对于每个提交 (`VerifyCoordinator.verify_commit`)**：
    a.  **环境恢复 (`restore_worktree_directory`)**：
        i.  加载快照 (`<commit_id>.bin`)。
        ii. 创建一个新的临时工作树。
        iii. 根据快照从 CAS 复制文件，在此工作树中重建 `.lake` 目录（和其他快照文件）。这通常通过并行文件复制来完成。
    b.  **完整性检查**：在恢复的工作树上运行 `lake build`，以确保它是一个有效且功能正常的 Lean 环境。
    c.  **Lean 代码验证**：
        i.  对于与此提交关联的每个 Lean 代码片段：
            *   调用 `lean_utils.verify_with_lean()`。
            *   该片段被写入恢复的工作树内的临时 `.lean` 文件中。
            *   执行 `lake env lean <temp_file.lean>` 进行编译。
            *   捕获结果（通过/失败、错误、警告、编译器输出）。
        ii. 可以使用线程池并行验证多个片段。
    d.  提交的状态被更新（例如，更新为 `STATUS_READY` 或 `STATUS_FAILED_VERIFY`）。
4.  **输出**：`--results_dir` 中的 JSONL 文件，其中每行包含原始输入记录，并为每个 Lean 代码片段增加了详细的 `verification_result`。

## 4. 使用说明

本节详细说明如何使用 Eleanstic 预处理 Mathlib 提交和验证 Lean 代码。

### A. 初始设置（一次性预处理 - `build` 命令）

1.  **配置**：
    *   确保您拥有 `leanprover-community/mathlib4` 存储库的本地克隆。
    *   编辑 `src/eleanstic/config.yaml`：
        *   将 `paths.mathlib_repo` 设置为 Mathlib4 克隆的路径。
        *   将 `paths.workspace_root` 下的 `paths.worktree_dir`、`paths.storage_dir`（用于 CAS）、`paths.cache_dir`（用于 `lake exe cache get`）、`paths.log_dir` 和 `status_dir` 设置为所需位置。确保这些位置有足够的磁盘空间。
        *   根据系统功能调整 `concurrency.max_workers`。
2.  **为 `build` 准备输入文件**：创建一个文件（例如 `commits_to_build.jsonl` 或 `commits_to_build.csv`），列出需要预处理的 Mathlib 提交 SHA。每行/记录应在某个键下包含提交 SHA（默认为 `commit_hash`，可通过 `build` 命令的 `--commit_id_key` 参数配置）。如果每个提交需要特定的 Lean 工具链，请将其包含在 `toolchain_content` 键下。
    *示例 `commits_to_build.jsonl`*：
    ```json
    {"commit_hash": "abcdef123456...", "toolchain_content": "leanprover/lean4:v4.7.0"}
    {"commit_hash": "fedcba654321...", "toolchain_content": "leanprover/lean4:v4.8.0"}
    ```
3.  **运行预处理（`build` 命令）**：
    ```bash
    python -m src.eleanstic.main build \
        --config src/eleanstic/config.yaml \
        --input_file /path/to/commits_to_build.jsonl \
        --commit_id_key commit_hash \
        --max_workers <num_processes>
    ```
    *   可选地添加 `--force` 以重新构建提交，即使它们的状态为 `STATUS_COLLAPSED`。
    *   此步骤将花费大量时间，具体取决于提交数量和系统性能。在配置的 `log_dir` 中监控日志。

### B. 验证 Lean 代码补丁（`verify` 命令）

Eleanstic 的 `verify` 命令可以处理 JSONL 文件的两种主要输入格式，具体取决于 `--lean_records_key` 参数是否存在及其值。`--code_key` 参数（默认为 `"code"`）指定在要验证的每个单独记录中保存 Lean 代码字符串的键。`--commit_id_key` 参数（默认为 `"commit_hash"`）指定保存提交 SHA 的键。

1.  **确保预处理已完成**：您要验证的 Mathlib 提交必须已通过 `build` 命令成功预处理。
2.  **为 `verify` 准备输入文件**：

    *   **选项 1：扁平 JSONL 格式（每行是一个单独的验证任务）**
        *   在此格式中，每个 JSON 行都是一个自包含的记录，同时包含提交标识符和要验证的代码。
        *   使用此格式时，您**不**向 `verify` 命令提供 `--lean_records_key` 参数。
        *示例 `patches_to_verify_flat.jsonl`*：
        ```json
        {"task_id": "t1", "commit_hash": "abcdef123456...", "code": "theorem foo : True := by trivial"}
        {"task_id": "t2", "commit_hash": "abcdef123456...", "code": "def bar := 1\\n#print bar"}
        {"task_id": "t3", "commit_hash": "fedcba654321...", "code": "theorem baz : 1 + 1 = 2 := rfl"}
        ```
        *运行验证命令（扁平格式）*：
        ```bash
        python -m src.eleanstic.main verify \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/patches_to_verify_flat.jsonl \
            --commit_id_key commit_hash \
            --code_key code \
            --results_dir /path/to/verification_outputs \
            --max_workers <num_processes>
        ```

    *   **选项 2：分组 JSONL 格式（每行包含一个提交和一系列任务）**
        *   在此格式中，每个 JSON 行包含一个提交标识符，然后在指定的键下包含要针对该提交进行验证的记录列表。
        *   使用此格式时，您**必须**向 `verify` 命令提供 `--lean_records_key` 参数，指定保存任务记录列表的键（例如 `patches_data`）。
        *示例 `patches_to_verify_grouped.jsonl`*：
        ```json
        {"benchmark_id": "b1", "commit_hash": "abcdef123456...", "patches_data": [{"id": "task1", "code": "theorem foo : True := by trivial"}, {"id": "task2", "code": "def bar := 1\\n#print bar"}]}
        {"benchmark_id": "b2", "commit_hash": "fedcba654321...", "patches_data": [{"id": "task3", "code": "theorem baz : 1 + 1 = 2 := rfl"}]}
        ```
        *运行验证命令（分组格式）*：
        ```bash
        python -m src.eleanstic.main verify \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/patches_to_verify_grouped.jsonl \
            --commit_id_key commit_hash \
            --lean_records_key patches_data \
            --code_key code \
            --results_dir /path/to/verification_outputs \
            --max_workers <num_processes>
        ```
    *   结果将作为 JSONL 文件（每个唯一提交 ID 一个文件）写入指定的 `--results_dir`。每个输出行将是原始输入记录（或分组情况下的子记录），并增加了 `verification_result` 对象。

## 5. 与 APE-Bench 的交互

Eleanstic 作为 APE-Bench I 框架的语法验证后端。`src/apebench/evaluation_pipelines/verification_manager.py` 脚本负责协调验证过程。

以下是它们如何交互的：

1.  **补丁生成**：APE-Bench 的推理流程为各种任务生成潜在的补丁。这些结果通常存储在多个 JSONL 文件中，其中每个文件可能对应一个特定的模型或一批任务。
2.  **为 Eleanstic 准备数据**：
    *   APE-Bench 中的 `verification_manager.py` 脚本使用 `--pipeline patch` 参数调用 `src.apebench.evaluation_pipelines.gather_results`。
    *   这个 `gather_results` 实用程序从各种输入文件中收集所有生成的补丁数据，并将其转换为**单个扁平的 JSONL 文件**（例如 `patches_for_verification_{timestamp}.jsonl`）。
    *   此扁平文件中的每一行代表一个验证任务，并包含所有必要的信息，包括 `commit_hash` 和 Lean `code` 片段（补丁）。
    *   *APE-Bench 为 Eleanstic 准备的示例行*：
        ```json
        {"task_id": "some_unique_id", "commit_hash": "abcdef123...", "code": "theorem T : True := by trivial", "model_name": "gpt-4", ...}
        ```
3.  **APE-Bench 调用 Eleanstic**：
    *   `verification_manager.py` 然后使用此扁平 JSONL 文件调用 `src.eleanstic.main verify`。
    *   APE-Bench 使用的命令结构如下（如果 `--commit_id_key` 和 `--code_key` 分别是 `commit_hash` 和 `code`，则通常依赖它们的默认值）：
        ```bash
        python -m src.eleanstic.main verify \
            --config /path/to/eleanstic_config.yaml \
            --input_file /path/to/temp_dir/patches_for_verification_{timestamp}.jsonl \
            --commit_id_key "commit_hash" \
            --code_key "code" \
            --results_dir /path/to/apebench_verification_outputs/results_{timestamp} \
            --max_workers <num_workers_from_apebench_config>
        ```
    *   注意：APE-Bench 对 Eleanstic 使用**扁平输入格式**，因此在调用 Eleanstic 时不使用 `--lean_records_key` 参数。
4.  **APE-Bench 收集结果**：
    *   Eleanstic 处理这些扁平记录并将其输出（原始记录 + `verification_result`）写入 `--results_dir` 指定的目录，为每个唯一的提交创建一个 JSONL 文件。
    *   然后，`verification_manager.py` 再次使用 `--pipeline verification` 参数调用 `src.apebench.evaluation_pipelines.gather_results`，以将 Eleanstic 的所有这些单独输出文件收集到一个整合的 `verification_results_{timestamp}.jsonl` 文件中。然后，此文件用于 APE-Bench 内的进一步分析和指标计算。

此工作流确保 APE-Bench 可以使用 Eleanstic 的专门功能高效地针对不同的 Mathlib 版本验证大量补丁。

## 6. 定制和二次开发

*   **配置**：修改 `config.yaml` 和 `core/config.py` 以添加新参数。
*   **存储后端**：可以将 `FileMapManager` 调整为使用不同的存储系统（例如云存储、用于文件映射的不同数据库），但这将是一项重大更改。
*   **构建过程**：如果 Mathlib 构建过程发生更改或需要支持不同的构建工具，则可以修改 `BuildCoordinator` 和 `lean_utils.py`。
*   **验证逻辑**：可以扩展 `VerifyCoordinator` 和 `lean_utils.verify_with_lean` 以进行更细致的验证（例如，特定的 linter 检查、资源分析）。
*   **并行性**：可以调整 `config.yaml` 中的并发设置以及 `main.py` 和 `coordinators.py` 中 `ProcessPoolExecutor`/`ThreadPoolExecutor` 的使用。