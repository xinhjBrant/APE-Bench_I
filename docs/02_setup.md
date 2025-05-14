[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 2. Setup and Installation

This section guides you through setting up the APE-Bench I project environment.

## Prerequisites

*   **Operating System**: Linux is recommended. macOS may work but is less tested. Windows is not officially supported.
*   **Git**: For cloning the repository and Mathlib4.
*   **Python**: Version 3.9 or higher.
*   **Lean 4 and Lake**: Required for Eleanstic setup and local Lean file verification. Follow the official [Lean installation guide](https://leanprover.github.io/lean4/doc/setup.html).
*   Sufficient disk space: Eleanstic's preprocessed data for Mathlib can be large (hundreds of GBs initially, but will be optimized by Eleanstic). The APE-Bench I dataset itself is smaller.

## 1. Clone the Repository

Clone this project repository to your local machine:

```bash
git clone https://github.com/xinhjBrant/APE-Bench_I
cd ape-bench # Or your chosen directory name
```

## 2. Python Environment and Dependencies

It is highly recommended to use a Python virtual environment.

```bash
python -m venv venv
source venv/bin/activate  # On Linux/macOS
# venv\Scripts\activate    # On Windows (if attempting)
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```

Key dependencies include `pandas`, `openai`, `tiktoken`, `pydantic`, etc. (refer to `requirements.txt` for the full list).

## 3. Download the APE-Bench I Dataset

The APE-Bench I dataset contains the tasks (Instruction, PreFile, Patch) used for evaluation. It is hosted on Hugging Face.

As indicated in the project's main `README.md`:

```bash
# Ensure you are in the root directory of the cloned ape-bench project
mkdir datasets
git clone https://huggingface.co/datasets/HuajianXin/APE-Bench_I datasets
```

This will download the dataset into the `datasets` directory within your project.

## 4. Setting up Eleanstic

Eleanstic is crucial for syntactic verification. It requires a one-time setup process to download and preprocess the versions of Mathlib4 relevant to the benchmark tasks. This step can be time-consuming and resource-intensive.

**Steps for Eleanstic Setup:**

1.  **Mathlib4 Clone**: Clone the `leanprover-community/mathlib4` repository locally. Eleanstic will access this repository to check out specific commits.

2.  **Configuration**: Configure Eleanstic by editing `src/eleanstic/config.yaml`. Key parameters include:
    ```yaml
    # Example (src/eleanstic/config.yaml)
    paths:
      mathlib_repo: "/path/to/your/mathlib4_clone"
      workspace_root: "verify_database"  # Base directory for Eleanstic data
      worktree_dir: "worktrees"  # For temporary Git worktrees
      storage_dir: "storage"     # For content-addressable storage
      cache_dir: "cache"         # For Lake cache
      log_dir: "logs"            # For log files
      verify_results_dir: "./verify_results"  # Results output

    concurrency:
      max_workers: 128  # Adjust based on your system's capability
      max_concurrent_file_storage: 8
      max_concurrent_lean_verifications: 64

    # ... other settings for storage, cache, logging, verification
    ```

3.  **Preprocessing Commits**: Run the Eleanstic build command to process the Mathlib commits used in APE-Bench I. Eleanstic needs to preprocess all Mathlib commits relevant to the tasks in your chosen APE-Bench dataset (e.g., `datasets/ape_bench1_test.parquet`).

    The `eleanstic.main build` command can directly take an APE-Bench `.parquet` dataset file as its `--input_file`. Eleanstic will parse this file to identify the unique commit hashes required for preprocessing. Alternatively, you can provide a JSONL file containing commit IDs.

    ```bash
    python -m src.eleanstic.main build \
        --config src/eleanstic/config.yaml \
        --input_file datasets/ape_bench1_test.parquet \
        --commit_id_key commit  # The column in the parquet file containing commit SHAs
    ```

    **Usage with a custom list of commits (JSONL):**
    ```bash
    python -m src.eleanstic.main build \
        --config src/eleanstic/config.yaml \
        --input_file /path/to/your_commits_to_build.jsonl \
        --commit_id_key commit_hash \
        --max_workers <num_processes>
    ```
    
    The input file (whether `.parquet` or `.jsonl`) should contain the necessary commit identifiers. If specific Lean toolchains are needed per commit and you are using a JSONL file, include them under a `toolchain_content` key.

    This build process will:
    - Check out each commit from your Mathlib repository
    - Build it with Lake
    - Store the build artifacts efficiently in the content-addressable storage
    - Create compact snapshots for quick restoration during verification

**Note**: This preprocessing step is resource-intensive but only needs to be done once. The paper mentions a significant storage reduction (from 15.6 TB to 1.1 TB) for thousands of commits through Eleanstic's deduplication technology.

## 5. API Keys (Optional - for running LLM inference)

If you plan to run inference with LLMs (e.g., OpenAI, Anthropic, Google models), you will need to set up your API keys. The primary way to configure these is by editing the file `src/apebench/inference/utils/api_keys.py`.

This file contains placeholders for various API providers. You should replace the placeholder strings (e.g., `"your-openai-api-key"`) with your actual API keys.

Example structure within `src/apebench/inference/utils/api_keys.py`:
```python
# OpenAI API credentials (GPT models)
openai_api_key = "your-openai-api-key" # Replace with your actual key
openai_base_url = "https://api.openai.com/v1"  # Or your Azure OpenAI endpoint

# Anthropic API credentials (Claude models)
aws_claude_api_key = "your-anthropic-api-key" # Replace with your actual key
aws_claude_base_url = "https://api.anthropic.com"  # Or your AWS Claude endpoint

# DeepSeek models
volces_api_key = "your-deepseek-api-key" # Replace with your actual key
volces_base_url = "https://api.deepseek.com"

# Google API credentials
google_api_key = "your-google-api-key" # Replace with your actual key
google_base_url = "https://generativelanguage.googleapis.com"

# Add additional API credentials as needed for other models
```

Ensure this file is correctly populated with your keys before running any inference tasks that require these LLMs. Some models or specific setups might also support or prioritize environment variables for API keys; refer to individual model integration details if direct configuration in `api_keys.py` doesn't seem to take effect.

After completing these steps, your environment should be ready for running experiments and utilizing the APE-Bench I framework.

---

Next: [Project Structure](./03_project_structure.md)

<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 2. 安装与设置

本节指导您完成 APE-Bench I 项目环境的设置。

## 先决条件

*   **操作系统**：推荐使用 Linux。macOS 可能也能工作，但测试较少。官方不支持 Windows。
*   **Git**：用于克隆代码仓库和 Mathlib4。
*   **Python**：版本 3.9 或更高。
*   **Lean 4 和 Lake**：Eleanstic 设置和本地 Lean 文件验证所必需。请遵循官方的 [Lean 安装指南](https://leanprover.github.io/lean4/doc/setup.html)。
*   足够的磁盘空间：Eleanstic 为 Mathlib 预处理的数据可能非常大（初始可能数百 GB，但 Eleanstic 会进行优化）。APE-Bench I 数据集本身较小。

## 1. 克隆代码仓库

将此项目代码仓库克隆到您的本地计算机：

```bash
git clone https://github.com/xinhjBrant/APE-Bench_I
cd ape-bench # 或您选择的目录名
```

## 2. Python 环境与依赖

强烈建议使用 Python 虚拟环境。

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate    # Windows (如果尝试的话)
```

安装所需的 Python 包：

```bash
pip install -r requirements.txt
```

主要依赖包括 `pandas`、`openai`、`tiktoken`、`pydantic` 等 (完整列表请参阅 `requirements.txt`)。

## 3. 下载 APE-Bench I 数据集

APE-Bench I 数据集包含用于评估的任务（指令、修改前文件、补丁）。它托管在 Hugging Face 上。

正如项目主 `README.md` 中所述：

```bash
# 确保您位于克隆的 ape-bench 项目的根目录中
mkdir datasets
git clone https://huggingface.co/datasets/HuajianXin/APE-Bench_I datasets
```

这会将数据集下载到您项目中的 `datasets` 目录。

## 4. 设置 Eleanstic

Eleanstic 对于语法验证至关重要。它需要一次性设置过程来下载和预处理与基准测试任务相关的 Mathlib4 版本。此步骤可能耗时且资源密集。

**Eleanstic 设置步骤：**

1.  **Mathlib4 克隆**：在本地克隆 `leanprover-community/mathlib4` 代码仓库。Eleanstic 将访问此仓库以检出特定的提交。

2.  **配置**：通过编辑 `src/eleanstic/config.yaml` 来配置 Eleanstic。关键参数包括：
    ```yaml
    # 示例 (src/eleanstic/config.yaml)
    paths:
      mathlib_repo: "/path/to/your/mathlib4_clone" # 指向您的 mathlib4 克隆路径
      workspace_root: "verify_database"  # Eleanstic 数据的基础目录
      worktree_dir: "worktrees"  # 用于临时 Git 工作区
      storage_dir: "storage"     # 用于内容寻址存储
      cache_dir: "cache"         # 用于 Lake 缓存
      log_dir: "logs"            # 用于日志文件
      verify_results_dir: "./verify_results"  # 结果输出

    concurrency:
      max_workers: 128  # 根据您的系统能力调整
      max_concurrent_file_storage: 8
      max_concurrent_lean_verifications: 64

    # ... 其他存储、缓存、日志、验证设置
    ```

3.  **预处理提交**：运行 Eleanstic 构建命令来处理 APE-Bench I 中使用的 Mathlib 提交。Eleanstic 需要预处理您选择的 APE-Bench 数据集（例如 `datasets/ape_bench1_test.parquet`）中涉及的所有 Mathlib 提交相关的任务。

    `eleanstic.main build` 命令可以直接将 APE-Bench `.parquet` 数据集文件作为其 `--input_file`。Eleanstic 将解析此文件以识别预处理所需的唯一提交哈希值。或者，您也可以提供一个包含提交 ID 的 JSONL 文件。

    ```bash
    python -m src.eleanstic.main build \
        --config src/eleanstic/config.yaml \
        --input_file datasets/ape_bench1_test.parquet \
        --commit_id_key commit  # 包含提交 SHA 的 parquet 文件中的列
    ```

    **使用自定义提交列表 (JSONL) 的用法：**
    ```bash
    python -m src.eleanstic.main build \
        --config src/eleanstic/config.yaml \
        --input_file /path/to/your_commits_to_build.jsonl \
        --commit_id_key commit_hash \
        --max_workers <进程数>
    ```
    
    输入文件（无论是 `.parquet` 还是 `.jsonl`）应包含必要的提交标识符。如果每个提交需要特定的 Lean 工具链并且您使用的是 JSONL 文件，请将其包含在 `toolchain_content` 键下。

    此构建过程将：
    - 从您的 Mathlib 代码仓库中检出每个提交
    - 使用 Lake 构建它
    - 将构建产物高效地存储在内容寻址存储中
    - 创建紧凑的快照以便在验证期间快速恢复

**注意**：此预处理步骤资源密集，但只需要执行一次。论文中提到，通过 Eleanstic 的去重技术，数千个提交的存储空间显著减少（从 15.6 TB 降至 1.1 TB）。

## 5. API 密钥 (可选 - 用于运行 LLM 推理)

如果您计划使用 LLM（例如 OpenAI、Anthropic、Google 模型）进行推理，则需要设置您的 API 密钥。配置这些密钥的主要方法是编辑文件 `src/apebench/inference/utils/api_keys.py`。

该文件包含各种 API 提供商的占位符。您应该将占位符字符串（例如 `"your-openai-api-key"`）替换为您的实际 API 密钥。

`src/apebench/inference/utils/api_keys.py` 中的示例结构：
```python
# OpenAI API 凭据 (GPT 模型)
openai_api_key = "your-openai-api-key" # 替换为您的实际密钥
openai_base_url = "https://api.openai.com/v1"  # 或您的 Azure OpenAI 端点

# Anthropic API 凭据 (Claude 模型)
aws_claude_api_key = "your-anthropic-api-key" # 替换为您的实际密钥
aws_claude_base_url = "https://api.anthropic.com"  # 或您的 AWS Claude 端点

# DeepSeek 模型
volces_api_key = "your-deepseek-api-key" # 替换为您的实际密钥
volces_base_url = "https://api.deepseek.com"

# Google API 凭据
google_api_key = "your-google-api-key" # 替换为您的实际密钥
google_base_url = "https://generativelanguage.googleapis.com"

# 根据需要为其他模型添加额外的 API 凭据
```

在运行任何需要这些 LLM 的推理任务之前，请确保此文件已正确填充您的密钥。某些模型或特定设置可能还支持或优先使用环境变量来设置 API 密钥；如果直接在 `api_keys.py` 中配置似乎不起作用，请参阅各个模型的集成详细信息。

完成这些步骤后，您的环境应该已准备好运行实验并利用 APE-Bench I 框架。

---

下一节: [项目结构](./03_project_structure.md) 