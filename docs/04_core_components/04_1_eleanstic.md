[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 4.1 Eleanstic: Version-Aware Syntactic Verification

Eleanstic is a critical backend component of the APE-Bench I framework, responsible for the **syntactic verification** stage of the evaluation pipeline. It addresses the challenge of efficiently compiling Lean code patches against many different historical versions of the Mathlib4 library.

Refer to `src/eleanstic/` for the source code and `src/eleanstic/README.md` for any specific technical notes from the developers.

## Design Rationale

*   **Problem**: Mathlib4 is a rapidly evolving library. Verifying a patch (an edit) requires compiling it within the *exact* versioned environment (Mathlib commit) from which the task was derived. Naively rebuilding Mathlib for each of the thousands of commits in the benchmark is computationally infeasible (hours per build, terabytes of artifacts).
*   **Solution**: Eleanstic decouples the expensive, stateful process of building Mathlib from the cheap, stateless process of validating individual file edits. It achieves this through:
    *   **Content-Addressable Storage (CAS)**: Each unique file from Mathlib build artifacts (`.lake` directory) across all relevant commits is stored only once, identified by its content hash (SHA-256).
    *   **Snapshotting**: For each processed Mathlib commit, Eleanstic creates a compact binary snapshot. This snapshot records the mapping from relative file paths within that commit's build environment to their content hashes in the CAS.
    *   **Rapid Restoration**: When a patch needs verification for a specific task (commit), Eleanstic uses the corresponding snapshot to quickly reconstruct the necessary Lean build environment in an isolated temporary worktree by fetching files from the CAS.

As noted in the APE-Bench I paper, this approach achieves significant storage reduction (e.g., 15.6 TB to 1.1 TB) and allows for fast environment restoration (under a second on SSDs).

## Key Functionalities

*   **Batch Commit Preprocessing**: Scripts or functions within `src/eleanstic/main.py` handle the initial processing of a list of Mathlib commits. For each commit:
    *   It's checked out from a local Mathlib4 git repository.
    *   `lake build` is executed (potentially using `lake exe cache get` to speed up individual builds).
    *   The resulting `.lake` build artifacts are traversed, files are hashed, and unique content is added to the CAS.
    *   A snapshot file is generated.
    *   The original large `.lake` directory in the temporary worktree can then be removed.
*   **Elastic Storage System**: The CAS (`src/eleanstic/core/`) manages the deduplicated storage of build files (regular files and symbolic links).
*   **Worktree Management**: Handles the compression (storing in CAS) and expansion (restoring from CAS) of Mathlib build environments.
*   **Patch Verification Service**: During APE-Bench evaluations, when a model-generated patch for a task needs syntactic checking:
    1.  The `src/apebench/evaluation_pipelines/verification_manager.py` script prepares an input JSONL file. Each line in this file represents a single verification task and contains at least the Mathlib `commit_hash` and the Lean `code` snippet to be verified, along with other metadata.
    2.  `verification_manager.py` invokes `src/eleanstic/main.py verify` with this JSONL file.
    3.  For each task in the input file, Eleanstic:
        a.  Restores the Mathlib build environment for the specified `commit_hash` from its CAS using the pre-generated snapshot.
        b.  Writes the provided Lean `code` snippet to a temporary file within this restored environment.
        c.  Invokes the Lean compiler (`lake env lean <temp_file.lean>`) on this temporary file.
        d.  Captures the compilation result (success/failure, errors, warnings) and augments the original input task data with this `verification_result`.
    4.  Eleanstic writes these augmented results to output JSONL files, typically one per processed commit.

## Configuration

Eleanstic is configured via `src/eleanstic/config.yaml`. Key settings include:

```yaml
# Base path configurations
paths:
  mathlib_repo: "/path/to/your/mathlib4_clone"  # Path to your local Mathlib4 repo
  workspace_root: "verify_database"  # Base directory for all Eleanstic data
  worktree_dir: "worktrees"  # Directory for temporary Git worktrees
  storage_dir: "storage"  # Directory for content-addressable storage
  cache_dir: "cache"  # Directory for Lake cache
  log_dir: "logs"  # Directory for log files
  verify_results_dir: "./verify_results"  # Directory for verification results

# Concurrency settings
concurrency:
  max_workers: 128  # Maximum number of worker processes
  max_concurrent_file_storage: 8  # Maximum parallel file storage threads
  max_concurrent_lean_verifications: 64  # Maximum parallel Lean verification threads

# Storage settings
storage:
  hash_algorithm: "sha256"  # Hashing algorithm (sha256/xxhash64)
  remove_worktree_after_build: true  # Whether to remove worktree after build

# Additional settings for cache, logging, verification
# ...
```

Proper configuration of these paths is essential before running the Eleanstic preprocessing step.

## Usage

1.  **Initial Setup (Preprocessing)**:
    *   Ensure Mathlib4 is cloned locally.
    *   Configure `src/eleanstic/config.yaml` as described above.
    *   Run the Eleanstic preprocessing using the `build` command:
        ```bash
        python -m src.eleanstic.main build \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/commits_to_build.jsonl \
            --commit_id_key commit_hash \
            --max_workers <num_processes>
        ```
        
        The input file should be in JSONL format with each line containing at least a commit ID field (e.g., `{"commit_hash": "abcdef123456..."}`. If specific Lean toolchains are needed per commit, include them under a `toolchain_content` key.

        This is a one-time, potentially lengthy process that will populate the CAS and create snapshots for all Mathlib commits relevant to APE-Bench I.

2.  **During APE-Bench Evaluation (Syntactic Verification)**:
    *   Once Eleanstic is set up and preprocessed, it is invoked by the `src/apebench/evaluation_pipelines/verification_manager.py` script as part of the APE-Bench evaluation workflow.
    *   **Data Preparation**: The `verification_manager.py` script first calls `src.apebench.evaluation_pipelines.gather_results --pipeline patch`. This utility collects results from the patch generation phase (LLM outputs) and transforms them into a JSONL file (e.g., `patches_for_verification_{timestamp}.jsonl`). Each line in this file is a JSON object representing a single verification task. For Eleanstic to process it correctly via the APE-Bench workflow, each JSON object *must* contain:
        *   A field for the commit hash. The key for this field is passed to Eleanstic via the `--commit_id_key` argument (APE-Bench uses `"commit_hash"`).
        *   A field for the Lean code snippet to be verified. The key for this field is passed to Eleanstic via the `--code_key` argument (APE-Bench uses `"code"`).
        *   Example line in `patches_for_verification_{timestamp}.jsonl`:
            ```json
            {"task_id": "unique_task_identifier", "commit_hash": "abcdef1234567890fedcba0987654321abcdef01", "code": "theorem example (n : Nat) : n = n := by rfl", "model_name": "some_model", "prompt_id": "p01"}
            ```
    *   **Eleanstic Invocation**: `verification_manager.py` then runs `src/eleanstic/main.py verify` with this prepared JSONL file. A typical command structure is:
        ```bash
        python -m src.eleanstic.main verify \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/patches_for_verification_{timestamp}.jsonl \
            --commit_id_key "commit_hash" \
            --code_key "code" \
            --results_dir /path/to/output_verification_results_dir \
            --max_workers <number_of_parallel_workers>
        ```
    *   Eleanstic processes each line, performs the verification as described under "Key Functionalities", and outputs JSONL files containing the original data plus a `verification_result` object for each task. These are typically written to subdirectories within the specified `--results_dir`, one file per commit.
    *   The `verification_manager.py` script then uses `src.apebench.evaluation_pipelines.gather_results --pipeline verification` to aggregate these individual Eleanstic output files into a single consolidated results file.

This clarifies that Eleanstic is used transparently by the APE-Bench pipeline for syntactic checks once it has been set up. Direct user interaction with Eleanstic's `verify` command during evaluation is generally not needed, as `verification_manager.py` handles it.

## Secondary Development

*   **Improving Efficiency**: Optimizing hashing, file I/O, CAS structure, or the snapshot/restoration process in `src/eleanstic/core/`.
*   **Supporting Lean/Lake Updates**: If Lean or Lake changes its build system or artifact structure significantly, Eleanstic might need updates to correctly parse and manage `.lake` directories.
*   **Concurrency and Robustness**: Enhancing parallel commit processing or error handling during the build/snapshotting phase.
*   **Customizing Storage**: Adjusting the storage configuration to optimize for specific hardware or environments.

---

Next: [Data Handling: Tasks and Format](./04_2_apebench_data.md)

<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 4.1 Eleanstic：版本感知的语法验证

Eleanstic 是 APE-Bench I 框架的关键后端组件，负责评估流程中的**语法验证**阶段。它解决了针对 Mathlib4 库的许多不同历史版本高效编译 Lean 代码补丁的挑战。

有关源代码，请参阅 `src/eleanstic/`；有关开发者的任何特定技术说明，请参阅 `src/eleanstic/README.md`。

## 设计理念

*   **问题**：Mathlib4 是一个快速发展的库。验证一个补丁（编辑）需要在任务来源的*确切*版本化环境（Mathlib 提交）中编译它。对基准测试中的数千个提交中的每一个都简单地重建 Mathlib 在计算上是不可行的（每次构建数小时，数 TB 的产物）。
*   **解决方案**：Eleanstic 将构建 Mathlib 的昂贵、有状态的过程与验证单个文件编辑的廉价、无状态的过程分离开来。它通过以下方式实现：
    *   **内容寻址存储 (CAS)**：来自所有相关提交的 Mathlib 构建产物（`.lake` 目录）中的每个唯一文件仅存储一次，通过其内容哈希 (SHA-256) 识别。
    *   **快照**：对于每个处理过的 Mathlib 提交，Eleanstic 都会创建一个紧凑的二进制快照。此快照记录了该提交构建环境中相对文件路径与其在 CAS 中内容哈希之间的映射。
    *   **快速恢复**：当需要针对特定任务（提交）验证补丁时，Eleanstic 使用相应的快照，通过从 CAS 中获取文件，在隔离的临时工作区中快速重建必要的 Lean 构建环境。

正如 APE-Bench I 论文所述，这种方法显著减少了存储（例如，从 15.6 TB 减少到 1.1 TB），并允许快速恢复环境（在 SSD 上不到一秒）。

## 关键功能

*   **批量提交预处理**：`src/eleanstic/main.py` 中的脚本或函数处理 Mathlib 提交列表的初始处理。对于每个提交：
    *   从本地 Mathlib4 git 仓库中检出。
    *   执行 `lake build`（可能使用 `lake exe cache get` 来加速单个构建）。
    *   遍历生成的 `.lake` 构建产物，对文件进行哈希处理，并将唯一内容添加到 CAS。
    *   生成快照文件。
    *   然后可以删除临时工作区中原始的大型 `.lake` 目录。
*   **弹性存储系统**：CAS (`src/eleanstic/core/`) 管理构建文件（常规文件和符号链接）的去重存储。
*   **工作区管理**：处理 Mathlib 构建环境的压缩（存储在 CAS 中）和扩展（从 CAS 恢复）。
*   **补丁验证服务**：在 APE-Bench 评估期间，当模型生成的任务补丁需要进行语法检查时：
    1.  `src/apebench/evaluation_pipelines/verification_manager.py` 脚本准备一个输入的 JSONL 文件。此文件中的每一行代表一个单独的验证任务，并且至少包含 Mathlib 的 `commit_hash` 和要验证的 Lean `code` 片段，以及其他元数据。
    2.  `verification_manager.py` 使用此 JSONL 文件调用 `src/eleanstic/main.py verify`。
    3.  对于输入文件中的每个任务，Eleanstic：
        a.  使用预先生成的快照从其 CAS 中恢复指定 `commit_hash` 的 Mathlib 构建环境。
        b.  将提供的 Lean `code` 片段写入此恢复环境中的临时文件。
        c.  在此临时文件上调用 Lean 编译器 (`lake env lean <temp_file.lean>`)。
        d.  捕获编译结果（成功/失败、错误、警告），并使用此 `verification_result` 增强原始输入任务数据。
    4.  Eleanstic 将这些增强的结果写入输出 JSONL 文件，通常每个处理过的提交一个文件。

## 配置

Eleanstic 通过 `src/eleanstic/config.yaml` 进行配置。关键设置包括：

```yaml
# 基本路径配置
paths:
  mathlib_repo: "/path/to/your/mathlib4_clone"  # 指向您的本地 Mathlib4 仓库的路径
  workspace_root: "verify_database"  # 所有 Eleanstic 数据的基础目录
  worktree_dir: "worktrees"  # 临时 Git 工作区的目录
  storage_dir: "storage"  # 内容寻址存储的目录
  cache_dir: "cache"  # Lake 缓存的目录
  log_dir: "logs"  # 日志文件的目录
  verify_results_dir: "./verify_results"  # 验证结果的目录

# 并发设置
concurrency:
  max_workers: 128  # 最大工作进程数
  max_concurrent_file_storage: 8  # 最大并行文件存储线程数
  max_concurrent_lean_verifications: 64  # 最大并行 Lean 验证线程数

# 存储设置
storage:
  hash_algorithm: "sha256"  # 哈希算法 (sha256/xxhash64)
  remove_worktree_after_build: true  # 构建后是否删除工作区

# 缓存、日志、验证的其他设置
# ...
```

在运行 Eleanstic 预处理步骤之前，正确配置这些路径至关重要。

## 用法

1.  **初始设置（预处理）**：
    *   确保 Mathlib4 已在本地克隆。
    *   如上所述配置 `src/eleanstic/config.yaml`。
    *   使用 `build` 命令运行 Eleanstic 预处理：
        ```bash
        python -m src.eleanstic.main build \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/commits_to_build.jsonl \
            --commit_id_key commit_hash \
            --max_workers <num_processes>
        ```

        输入文件应为 JSONL 格式，每行至少包含一个提交 ID 字段 (例如 `{"commit_hash": "abcdef123456..."}`）。如果每个提交需要特定的 Lean 工具链，请将其包含在 `toolchain_content` 键下。

        这是一个一次性的、可能耗时较长的过程，它将填充 CAS 并为 APE-Bench I 相关的所有 Mathlib 提交创建快照。

2.  **APE-Bench 评估期间（语法验证）**：
    *   一旦 Eleanstic 设置完成并经过预处理，它将由 `src/apebench/evaluation_pipelines/verification_manager.py` 脚本作为 APE-Bench 评估工作流的一部分被调用。
    *   **数据准备**：`verification_manager.py` 脚本首先调用 `src.apebench.evaluation_pipelines.gather_results --pipeline patch`。此工具收集补丁生成阶段（LLM 输出）的结果，并将其转换为 JSONL 文件（例如 `patches_for_verification_{timestamp}.jsonl`）。此文件中的每一行都是一个代表单个验证任务的 JSON 对象。为使 Eleanstic 能通过 APE-Bench 工作流正确处理它，每个 JSON 对象*必须*包含：
        *   一个用于提交哈希的字段。此字段的键通过 `--commit_id_key` 参数传递给 Eleanstic（APE-Bench 使用 `"commit_hash"`）。
        *   一个用于待验证 Lean 代码片段的字段。此字段的键通过 `--code_key` 参数传递给 Eleanstic（APE-Bench 使用 `"code"`）。
        *   `patches_for_verification_{timestamp}.jsonl` 中的示例行：
            ```json
            {"task_id": "unique_task_identifier", "commit_hash": "abcdef1234567890fedcba0987654321abcdef01", "code": "theorem example (n : Nat) : n = n := by rfl", "model_name": "some_model", "prompt_id": "p01"}
            ```
    *   **Eleanstic 调用**：然后 `verification_manager.py` 使用这个准备好的 JSONL 文件运行 `src/eleanstic/main.py verify`。典型的命令结构是：
        ```bash
        python -m src.eleanstic.main verify \
            --config src/eleanstic/config.yaml \
            --input_file /path/to/patches_for_verification_{timestamp}.jsonl \
            --commit_id_key "commit_hash" \
            --code_key "code" \
            --results_dir /path/to/output_verification_results_dir \
            --max_workers <number_of_parallel_workers>
        ```
    *   Eleanstic 处理每一行，执行"关键功能"下描述的验证，并输出包含原始数据以及每个任务的 `verification_result` 对象的 JSONL 文件。这些文件通常写入指定的 `--results_dir` 内的子目录中，每个提交一个文件。
    *   然后 `verification_manager.py` 脚本使用 `src.apebench.evaluation_pipelines.gather_results --pipeline verification` 将这些单独的 Eleanstic 输出文件聚合成一个统一的结果文件。

这阐明了 Eleanstic 在设置完毕后，由 APE-Bench 流水线透明地用于语法检查。在评估期间，通常不需要用户直接与 Eleanstic 的 `verify` 命令交互，因为 `verification_manager.py` 会处理它。

## 二次开发

*   **提高效率**：优化 `src/eleanstic/core/` 中的哈希、文件 I/O、CAS 结构或快照/恢复过程。
*   **支持 Lean/Lake 更新**：如果 Lean 或 Lake 的构建系统或产物结构发生重大变化，Eleanstic 可能需要更新才能正确解析和管理 `.lake` 目录。
*   **并发性和鲁棒性**：增强构建/快照阶段的并行提交处理或错误处理能力。
*   **自定义存储**：调整存储配置以针对特定硬件或环境进行优化。

---

下一节: [数据处理：任务与格式](./04_2_apebench_data.md) 