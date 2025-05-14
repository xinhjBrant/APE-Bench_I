[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 5. Workflow Guides

This section provides step-by-step guides for common workflows using the APE-Bench I framework.

## D. General APE-Bench Workflow

This guide outlines the standard method for running the APE-Bench pipeline, from setting up data to evaluating results. This is the recommended workflow for most users.

**Prerequisites:**

*   Ensure all steps in the [Setup and Installation](./02_setup.md) guide are completed. This includes:
    *   Python environment and dependencies.
    *   `mathlib4` repository cloned locally (e.g., to `./mathlib4`).
    *   APE-Bench I dataset downloaded (e.g., to `datasets/`). The specific dataset file (e.g., `datasets/ape_bench1_test.parquet`) will be used.
    *   API keys configured if using LLMs for generation or judgment.

**Workflow Steps:**

1.  **Initial Setup & Data Preparation**:
    *   Clone the `mathlib4` repository if you haven't already:
        ```bash
        git clone https://github.com/leanprover-community/mathlib4.git ./mathlib4
        ```
    *   Clone the APE-Bench I dataset from Hugging Face into a `datasets` directory:
        ```bash
        mkdir -p datasets
        git clone https://huggingface.co/datasets/HuajianXin/APE-Bench_I datasets
        ```

2.  **Eleanstic Build (Preprocessing Mathlib Commits)**:
    *   Eleanstic needs to preprocess all Mathlib commits that are referenced in your chosen APE-Bench dataset (e.g., `datasets/ape_bench1_test.parquet`).
    *   Configure `src/eleanstic/config.yaml` to point to your `mathlib4` clone and set other paths.
    *   Run the Eleanstic build command. It can directly take the APE-Bench `.parquet` dataset file as input:
        ```bash
        python -m src.eleanstic.main build \\
            --config src/eleanstic/config.yaml \\
            --input_file datasets/ape_bench1_test.parquet \\
            # --commit_id_key commit # Ensure this matches the commit hash column in your parquet
            # --max_workers <num_processes> # Optional: adjust based on your system
        ```
    *   This step ensures that Eleanstic has all necessary build artifacts for the commits involved in the benchmark tasks. It can be time-consuming for the first run on a dataset.

3.  **Configure APE-Bench**:
    *   Open the main configuration file (e.g., `configs/config.yaml`).
    *   Ensure the `input_file` parameter under the `project` (or relevant) section points to your chosen dataset:
        ```yaml
        # Example in configs/config.yaml
        project:
          input_file: "datasets/ape_bench1_test.parquet"
          # ... other project settings
        ```
    *   Configure other sections as needed (e.g., `generation` for models to test, `verification`, `judgement`).

4.  **Run the APE-Bench Pipeline Scripts**:
    Execute the following scripts sequentially, using your main configuration file.

    *   **Generate Patches**:
        ```bash
        python -m src.apebench.scripts.1_generate_patches --config configs/config.yaml
        ```
    *   **Verify Patches**:
        ```bash
        python -m src.apebench.scripts.2_verify_patches --config configs/config.yaml
        ```
    *   **Evaluate Patches (Semantic Judgement)**:
        ```bash
        python -m src.apebench.scripts.3_evaluate_patches --config configs/config.yaml
        ```

5.  **Analyze Results**:
    *   Results (generated patches, verification outcomes, evaluation scores, metrics) will be stored in the `outputs/` directory, typically organized by model and timestamp.

**Optional: Rebuilding Data from Scratch**

If you need to regenerate the APE-Bench dataset itself (e.g., by mining new commits from Mathlib, applying different filtering, or re-synthesizing instructions), you can use the `0_collect_data.py` script. This is an advanced step and not typically part of a standard benchmark run.

*   Inspect and configure parameters within `src/apebench/scripts/0_collect_data.py` or pass them as command-line arguments.
*   Run the script:
    ```bash
    python -m src.apebench.scripts.0_collect_data --config configs/config.yaml \\
        # --repo_path ./mathlib4 \\
        # --dataset_dir ./datasets/new_ape_bench_data \\
        # ... other parameters as needed
    ```
    This script includes steps for collecting commit data, filtering, using Eleanstic to build/verify, and generating instructions/judgements for the new dataset.

## A. Reproducing Paper Results

This workflow aims to reproduce the main results presented in the APE-Bench I paper (e.g., Table 2).

1.  **Complete Setup**: Ensure all steps in the [Setup and Installation](./02_setup.md) guide are completed. This includes:
    *   Python environment and dependencies.
    *   APE-Bench I dataset downloaded to `datasets/`.
    *   **Crucially, Eleanstic must be fully set up and all relevant Mathlib commits preprocessed.** This means:
        ```bash
        # Configure src/eleanstic/config.yaml with correct paths
        # Run Eleanstic preprocessing on all required commits
        python -m src.eleanstic.main build --config src/eleanstic/config.yaml --input_file /path/to/commits_to_build.jsonl --commit_id_key commit_hash
        ```
    *   API keys for all models evaluated in the paper must be configured. Refer to model configuration files in `src/apebench/config/`.

2.  **Run Patch Generation (Inference)**: 
    ```bash
    # Generate patches using the specified model(s)
    python -m src.apebench.inference.run_inference \
        --pipeline patch \
        --input_file /path/to/apebench_dataset.jsonl \
        --output_file ./outputs/patch_generation_results.jsonl \
        --model_name gpt-4o \  # Or other model
        --temperature 0.8 \
        --n_responses 20  # For pass@16 calculation
    ```
    This step can be repeated for each model you want to evaluate.

3.  **Run Syntactic Verification**:
    ```bash
    # Verify generated patches using Eleanstic
    python -m src.apebench.evaluation_pipelines.verification_manager \
        --config path/to/config.yaml \
        --generation_output_files ./outputs/patch_generation_results.jsonl
    ```
    The `verification_manager.py` will:
    * Collect patches using `gather_results.py --pipeline patch`
    * Call Eleanstic for verification
    * Gather and merge verification results
    * Calculate syntactic verification metrics

4.  **Run Semantic Evaluation**:
    ```bash
    # Evaluate syntactically valid patches using LLM-as-Judge
    python -m src.apebench.evaluation_pipelines.evaluation_manager \
        --config path/to/config.yaml \
        --merged_results_file ./outputs/merged_results_<timestamp>.jsonl
    ```
    The `evaluation_manager.py` will:
    * Filter and flatten syntactically verified patches
    * Run the judgment pipeline using the configured judge LLM
    * Collect judgment results
    * Calculate semantic evaluation metrics

5.  **Analyze Results**: Results are stored in multiple files:
    * Patch generation: `./outputs/patch_generation_results.jsonl`
    * Verification results: `./outputs/merged_results_<timestamp>.jsonl`
    * Verification metrics: `./outputs/verification_metrics_<timestamp>.json`
    * Judgment results: `./outputs/judgement_<timestamp>.jsonl` and `./outputs/filtered_judgement_<timestamp>.jsonl`
    * Judgment metrics: `./outputs/judgement_metrics_<timestamp>.json`

**Note**: Due to potential slight variations in LLM API responses over time, exact numerical matches might be difficult, but results should be broadly consistent with the paper's findings.

## B. Evaluating a New LLM

This workflow describes how to evaluate a new LLM (not covered in the original paper) on APE-Bench I.

1.  **Complete Setup**: Same as for reproducing results (Eleanstic and dataset are essential).

2.  **Integrate the New LLM**: 
    *   Add a new model adapter in `src/apebench/inference/` if the model uses an API format not already supported.
    *   Update model configuration in the appropriate config file, adding parameters such as API endpoint, authentication, and default parameters.

3.  **Run Patch Generation with the New LLM**:
    ```bash
    python -m src.apebench.inference.run_inference \
        --pipeline patch \
        --input_file /path/to/apebench_dataset.jsonl \
        --output_file ./outputs/your_new_model_results.jsonl \
        --model_name your_new_model_id \
        --temperature 0.8 \
        --n_responses 20
    ```

4.  **Run Verification and Evaluation**:
    ```bash
    # Verify patches
    python -m src.apebench.evaluation_pipelines.verification_manager \
        --config path/to/config.yaml \
        --generation_output_files ./outputs/your_new_model_results.jsonl

    # Evaluate semantically
    python -m src.apebench.evaluation_pipelines.evaluation_manager \
        --config path/to/config.yaml
    ```
    Note that `evaluation_manager.py` will automatically use the latest verification results if not explicitly provided.

5.  **Compare Results**: The metrics files generated in the process contain the pass@k metrics for both syntactic verification and semantic judgment. You can compare these with existing baselines from the paper.

## C. Running Custom Experiments

This could involve various scenarios, such as:
*   Testing a new prompting technique.
*   Evaluating on a subset of tasks (e.g., only 'Bug Fix' tasks or 'Hard' difficulty tasks).
*   Using a different LLM as the semantic judge.
*   Experimenting with `DiffRepair` parameters.

**General Steps**:

1.  **Customize the Configuration**: 
    *   Create a custom version of your config file, e.g., `custom_config.yaml`.
    *   Modify relevant parameters, such as:
        ```yaml
        # Example modifications in config.yaml
        judgement:
          model_name: "your-judge-model"
          temperature: 0.2
          n_responses: 4  # For sample@4 strategy
          
        diffrepair:
          enabled: true
          max_attempts: 3
          similarity_threshold: 0.8
        ```

2.  **Prepare a Task Subset** (if needed):
    *   Filter the dataset to create a task subset:
        ```bash
        python -m src.apebench.scripts.filter_dataset \
            --input_file /path/to/apebench_dataset.jsonl \
            --output_file ./outputs/custom_task_subset.jsonl \
            --filter_key "task_nature" \
            --filter_value "bug_fix"
        ```

3.  **Run the Experiment**:
    *   Use the same workflow as above, but with your custom configuration and potentially filtered dataset:
        ```bash
        # Inference
        python -m src.apebench.inference.run_inference \
            --pipeline patch \
            --input_file ./outputs/custom_task_subset.jsonl \
            --output_file ./outputs/custom_experiment_results.jsonl \
            --model_name model_name \
            --custom_config path/to/custom_config.yaml
            
        # Verification
        python -m src.apebench.evaluation_pipelines.verification_manager \
            --config path/to/custom_config.yaml \
            --generation_output_files ./outputs/custom_experiment_results.jsonl
            
        # Evaluation
        python -m src.apebench.evaluation_pipelines.evaluation_manager \
            --config path/to/custom_config.yaml
        ```

4.  **Analyze Custom Results**:
    *   Use standard output files or write custom analysis scripts to investigate specific aspects of your experiment.

Always ensure your changes are well-documented if you plan to share or integrate them later.

---

Next: [Troubleshooting](./06_troubleshooting.md)

<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 5. 工作流指南

本节提供使用 APE-Bench I 框架执行常见工作流的分步指南。

## D. APE-Bench 核心工作流程

本指南概述了运行 APE-Bench 流水线的标准方法，从设置数据到评估结果。这是推荐给大多数用户的工作流程。

**先决条件：**

*   确保[安装与设置](./02_setup.md)指南中的所有步骤均已完成。这包括：
    *   Python 环境和依赖项。
    *   `mathlib4` 代码仓库已在本地克隆（例如，克隆到 `./mathlib4`）。
    *   APE-Bench I 数据集已下载（例如，下载到 `datasets/`）。将使用特定的数据集文件（例如 `datasets/ape_bench1_test.parquet`）。
    *   如果使用 LLM 进行生成或判断，则需配置 API 密钥。

**工作流步骤：**

1.  **初始设置与数据准备**：
    *   如果尚未克隆 `mathlib4` 代码仓库，请克隆它：
        ```bash
        git clone https://github.com/leanprover-community/mathlib4.git ./mathlib4
        ```
    *   从 Hugging Face 克隆 APE-Bench I 数据集到 `datasets` 目录：
        ```bash
        mkdir -p datasets
        git clone https://huggingface.co/datasets/HuajianXin/APE-Bench_I datasets
        ```

2.  **Eleanstic 构建（预处理 Mathlib 提交）**：
    *   Eleanstic 需要预处理您选择的 APE-Bench 数据集（例如 `datasets/ape_bench1_test.parquet`）中引用的所有 Mathlib 提交。
    *   配置 `src/eleanstic/config.yaml` 使其指向您的 `mathlib4` 克隆并设置其他路径。
    *   运行 Eleanstic 构建命令。它可以直接将 APE-Bench `.parquet` 数据集文件作为输入：
        ```bash
        python -m src.eleanstic.main build \\
            --config src/eleanstic/config.yaml \\
            --input_file datasets/ape_bench1_test.parquet \\
            # --commit_id_key commit # 确保此项与 parquet 文件中的提交哈希列名匹配
            # --max_workers <进程数> # 可选：根据您的系统进行调整
        ```
    *   此步骤确保 Eleanstic 拥有基准测试任务所涉及提交的所有必要构建产物。对于首次在数据集上运行，此步骤可能非常耗时。

3.  **配置 APE-Bench**：
    *   打开主配置文件（例如 `configs/config.yaml`）。
    *   确保 `project`（或相关）部分下的 `input_file` 参数指向您选择的数据集：
        ```yaml
        # configs/config.yaml 中的示例
        project:
          input_file: "datasets/ape_bench1_test.parquet"
          # ... 其他项目设置
        ```
    *   根据需要配置其他部分（例如，`generation` 用于要测试的模型，`verification`，`judgement`）。

4.  **运行 APE-Bench 流水线脚本**：
    使用您的主配置文件依次执行以下脚本。

    *   **生成补丁**：
        ```bash
        python -m src.apebench.scripts.1_generate_patches --config configs/config.yaml
        ```
    *   **验证补丁**：
        ```bash
        python -m src.apebench.scripts.2_verify_patches --config configs/config.yaml
        ```
    *   **评估补丁（语义判断）**：
        ```bash
        python -m src.apebench.scripts.3_evaluate_patches --config configs/config.yaml
        ```

5.  **分析结果**：
    *   结果（生成的补丁、验证结果、评估分数、指标）将存储在 `outputs/` 目录中，通常按模型和时间戳组织。

**可选：从头开始重建数据**

如果您需要重新生成 APE-Bench 数据集本身（例如，通过从 Mathlib 挖掘新的提交、应用不同的筛选条件或重新合成指令），您可以使用 `0_collect_data.py` 脚本。这是一个高级步骤，通常不属于标准基准测试运行的一部分。

*   检查并配置 `src/apebench/scripts/0_collect_data.py` 中的参数，或将其作为命令行参数传递。
*   运行脚本：
    ```bash
    python -m src.apebench.scripts.0_collect_data --config configs/config.yaml \\
        # --repo_path ./mathlib4 \\
        # --dataset_dir ./datasets/new_ape_bench_data \\
        # ... 其他所需参数
    ```
    此脚本包括收集提交数据、筛选、使用 Eleanstic 构建/验证以及为新数据集生成指令/判断的步骤。

## A. 复现论文结果

此工作流旨在复现 APE-Bench I 论文中呈现的主要结果（例如表 2）。

1.  **完成设置**：确保[安装与设置](./02_setup.md)指南中的所有步骤均已完成。这包括：
    *   Python 环境和依赖项。
    *   APE-Bench I 数据集已下载到 `datasets/`。
    *   **至关重要的是，Eleanstic 必须完全设置完毕，并且所有相关的 Mathlib 提交都已预处理。** 这意味着：
        ```bash
        # 使用正确的路径配置 src/eleanstic/config.yaml
        # 对所有必需的提交运行 Eleanstic 预处理
        python -m src.eleanstic.main build --config src/eleanstic/config.yaml --input_file /path/to/commits_to_build.jsonl --commit_id_key commit_hash
        ```
    *   必须配置论文中评估的所有模型的 API 密钥。请参阅 `src/apebench/config/` 中的模型配置文件。

2.  **运行补丁生成（推理）**：
    ```bash
    # 使用指定的模型生成补丁
    python -m src.apebench.inference.run_inference \
        --pipeline patch \
        --input_file /path/to/apebench_dataset.jsonl \
        --output_file ./outputs/patch_generation_results.jsonl \
        --model_name gpt-4o \  # 或其他模型
        --temperature 0.8 \
        --n_responses 20  # 用于 pass@16 计算
    ```
    对于您要评估的每个模型，可以重复此步骤。

3.  **运行语法验证**：
    ```bash
    # 使用 Eleanstic 验证生成的补丁
    python -m src.apebench.evaluation_pipelines.verification_manager \
        --config path/to/config.yaml \
        --generation_output_files ./outputs/patch_generation_results.jsonl
    ```
    `verification_manager.py` 将会：
    * 使用 `gather_results.py --pipeline patch` 收集补丁
    * 调用 Eleanstic 进行验证
    * 收集并合并验证结果
    * 计算语法验证指标

4.  **运行语义评估**：
    ```bash
    # 使用作为裁判的 LLM 评估语法有效的补丁
    python -m src.apebench.evaluation_pipelines.evaluation_manager \
        --config path/to/config.yaml \
        --merged_results_file ./outputs/merged_results_<timestamp>.jsonl
    ```
    `evaluation_manager.py` 将会：
    * 筛选并扁平化语法验证通过的补丁
    * 使用配置的裁判 LLM 运行判断流程
    * 收集判断结果
    * 计算语义评估指标

5.  **分析结果**：结果存储在多个文件中：
    * 补丁生成：`./outputs/patch_generation_results.jsonl`
    * 验证结果：`./outputs/merged_results_<timestamp>.jsonl`
    * 验证指标：`./outputs/verification_metrics_<timestamp>.json`
    * 判断结果：`./outputs/judgement_<timestamp>.jsonl` 和 `./outputs/filtered_judgement_<timestamp>.jsonl`
    * 判断指标：`./outputs/judgement_metrics_<timestamp>.json`

**注意**：由于 LLM API 响应随时间可能存在细微差异，因此可能难以实现精确的数值匹配，但结果应与论文的发现大体一致。

## B. 评估新的 LLM

此工作流描述了如何在 APE-Bench I 上评估新的 LLM（原始论文未涵盖）。

1.  **完成设置**：与复现结果相同（Eleanstic 和数据集至关重要）。

2.  **集成新的 LLM**：
    *   如果模型使用的 API 格式尚不受支持，请在 `src/apebench/inference/` 中添加新的模型适配器。
    *   在相应的配置文件中更新模型配置，添加 API 端点、身份验证和默认参数等参数。

3.  **使用新的 LLM 运行补丁生成**：
    ```bash
    python -m src.apebench.inference.run_inference \
        --pipeline patch \
        --input_file /path/to/apebench_dataset.jsonl \
        --output_file ./outputs/your_new_model_results.jsonl \
        --model_name your_new_model_id \
        --temperature 0.8 \
        --n_responses 20
    ```

4.  **运行验证和评估**：
    ```bash
    # 验证补丁
    python -m src.apebench.evaluation_pipelines.verification_manager \
        --config path/to/config.yaml \
        --generation_output_files ./outputs/your_new_model_results.jsonl

    # 进行语义评估
    python -m src.apebench.evaluation_pipelines.evaluation_manager \
        --config path/to/config.yaml
    ```
    请注意，如果未明确提供，`evaluation_manager.py` 将自动使用最新的验证结果。

5.  **比较结果**：在此过程中生成的指标文件包含语法验证和语义判断的 pass@k 指标。您可以将这些指标与论文中的现有基线进行比较。

## C. 运行自定义实验

这可能涉及各种场景，例如：
*   测试新的提示技术。
*   在任务子集上进行评估（例如，仅"错误修复"任务或"困难"难度任务）。
*   使用不同的 LLM 作为语义裁判。
*   试验 `DiffRepair` 参数。

**一般步骤**：

1.  **自定义配置**：
    *   创建配置文件的自定义版本，例如 `custom_config.yaml`。
    *   修改相关参数，例如：
        ```yaml
        # config.yaml 中的示例修改
        judgement:
          model_name: "your-judge-model"
          temperature: 0.2
          n_responses: 4  # 用于 sample@4 策略
          
        diffrepair:
          enabled: true
          max_attempts: 3
          similarity_threshold: 0.8
        ```

2.  **准备任务子集**（如果需要）：
    *   筛选数据集以创建任务子集：
        ```bash
        python -m src.apebench.scripts.filter_dataset \
            --input_file /path/to/apebench_dataset.jsonl \
            --output_file ./outputs/custom_task_subset.jsonl \
            --filter_key "task_nature" \
            --filter_value "bug_fix"
        ```

3.  **运行实验**：
    *   使用与上述相同的工作流，但使用您的自定义配置和可能筛选过的数据集：
        ```bash
        # 推理
        python -m src.apebench.inference.run_inference \
            --pipeline patch \
            --input_file ./outputs/custom_task_subset.jsonl \
            --output_file ./outputs/custom_experiment_results.jsonl \
            --model_name model_name \
            --custom_config path/to/custom_config.yaml
            
        # 验证
        python -m src.apebench.evaluation_pipelines.verification_manager \
            --config path/to/custom_config.yaml \
            --generation_output_files ./outputs/custom_experiment_results.jsonl
            
        # 评估
        python -m src.apebench.evaluation_pipelines.evaluation_manager \
            --config path/to/custom_config.yaml
        ```

4.  **分析自定义结果**：
    *   使用标准输出文件或编写自定义分析脚本来调查实验的特定方面。

如果您计划稍后共享或集成您的更改，请始终确保对更改进行充分的文档记录。

---

Next: [Troubleshooting](./06_troubleshooting.md) 