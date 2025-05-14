[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 4.3 LLM Inference and DiffRepair

This section covers the process of generating patches using Large Language Models (LLMs) and the crucial `DiffRepair` utility that post-processes these patches. The relevant code is primarily located in `src/apebench/inference/` and its sub-modules like `src/apebench/inference/utils/diff_repair.py`.

## LLM Inference Process

The core task for an LLM in APE-Bench I is to generate a patch (in unified diff format) that transforms a given `PreFile` according to an `Instruction`.

1.  **Entry Point**: The main entry point for inference is `src/apebench/inference/run_inference.py`, which supports multiple pipelines including:
    *   `patch` pipeline: For generating patched code based on instructions
    *   `judgement` pipeline: For evaluating patches using LLM-as-Judge
    *   Both pipelines handle data preparation, model invocation, and result collection.

2.  **Prompt Construction**: For each task, a prompt is constructed for the target LLM. This typically includes:
    *   The `Instruction` (natural language command).
    *   The `PreFile` (the full Lean code before edits).
    *   Formatting instructions to guide the LLM to output correctly structured patches.
    *   The prompt templates are model-specific and are defined in the appropriate model adapter classes.

3.  **Model Invocation**: The inference framework supports various LLM providers:
    *   Each supported model has an adapter in `src/apebench/inference/models/`.
    *   These adapters handle API authentication, request formatting, and response parsing for different APIs.
    *   The `modelmap` dictionary in `src/apebench/inference/run_inference.py` maps model names to their respective adapter classes.
    *   Key parameters like `temperature`, `max_tokens`, and `n_responses` (for sampling multiple candidates) are passed to the appropriate API.

4.  **Output Processing**:
    *   The raw LLM output is parsed to extract the generated patches.
    *   For the `patch` pipeline, `DiffRepair` is typically applied to the extracted patches (see below).
    *   The processed outputs are saved to the specified output file in a structured format.

5.  **Parallelism**: Processing can be distributed across multiple workers (using `ProcessPoolExecutor`) to speed up inference for large datasets, controlled by the `--max_workers` parameter.

The command to run inference might look like:
```bash
python -m src.apebench.inference.run_inference \
    --pipeline patch \
    --input_file /path/to/tasks.jsonl \
    --output_file /path/to/results.jsonl \
    --model_name gpt-4o \
    --temperature 0.8 \
    --n_responses 20 \
    --max_workers 4
```

## DiffRepair: Fault-Tolerant Patch Recovery

LLM-generated diffs are often "noisy" – they might have incorrect line numbers, misaligned context lines, or formatting issues that prevent them from being applied cleanly using standard `patch` utilities. `DiffRepair` is a vital component designed to address this.

*   **Location**: `src/apebench/inference/utils/diff_repair.py`
*   **Purpose**: To transform noisy model-generated diffs into clean, structurally consistent, and applicable patches while preserving the original intent of the edit as much as possible.
*   **Mention in Paper**: Sections 5.1 (Patch Normalization) and Appendix A.

**DiffRepair Workflow (as described in Appendix A of the paper):**

1.  **Hunk Parsing**: The input diff text is parsed into individual "hunks" (segments of changes).
2.  **Intent Localization (Fuzzy Matching)**: For each hunk, `DiffRepair` attempts to find the correct region in the `PreFile` where the change was intended. This is a crucial step and involves:
    *   Comparing context lines from the hunk with lines in the `PreFile`.
    *   Using fuzzy matching algorithms (e.g., Levenshtein distance, sequence matching) to tolerate minor discrepancies.
    *   The `_find_candidate_region_exact` and `_find_best_region_with_dp` methods in `diff_repair.py` suggest sophisticated matching logic, including dynamic programming.
3.  **Patch Reconstruction**: Once the target region is localized, `DiffRepair` reconstructs a clean diff hunk:
    *   Re-aligning added and deleted lines to structurally valid positions relative to the correctly identified context from `PreFile`.
    *   Augmenting missing context lines to satisfy unified diff format constraints.
    *   Resolving line number offsets and potential hunk overlaps.
4.  **Final Diff Generation**: The repaired hunks are combined into a final, clean unified diff string.

**Key aspects of `DiffRepair` from the code (`diff_repair.py`):**
*   Handles both standard diffs with `@@ ... @@` headers and non-standard diffs.
*   Normalizes lines (stripping whitespace, lowercasing) for more robust matching.
*   Uses a combination of exact and fuzzy matching techniques.
*   The `repair()` method orchestrates the overall process for a given diff.
*   Can filter overlapping hunks based on the significance of changes.

The paper's Table 3, showing patch application success rates before and after repair, highlights the importance of `DiffRepair`.

## Usage

*   **LLM Inference**: The main interface is `run_inference.py`, which supports various command-line arguments:
    ```bash
    python -m src.apebench.inference.run_inference --help
    ```
    Common arguments include `--pipeline`, `--input_file`, `--output_file`, `--model_name`, `--temperature`, and `--n_responses`.

*   **DiffRepair Configuration**: DiffRepair's behavior can be configured through parameters in the APE-Bench configuration files:
    ```yaml
    # Example configuration for DiffRepair
    diffrepair:
      enabled: true  # Whether to apply DiffRepair
      exact_match: false  # Whether to use exact matching only
      strict_match_threshold: 0.8  # Threshold for fuzzy matching
    ```

## Secondary Development

*   **Integrating New LLMs**: 
    1.  Create a new model adapter class in `src/apebench/inference/models/` that implements the necessary API interaction.
    2.  Add the model to the `modelmap` dictionary in `run_inference.py`.
    3.  Configure the model in the appropriate configuration file, including any model-specific parameters.
    4.  Optionally, create custom prompt templates for the new model if the existing ones aren't suitable.

*   **Improving DiffRepair**:
    *   Enhance the fuzzy matching algorithms for better localization accuracy or speed.
    *   Improve hunk reconstruction logic to handle more complex or malformed diffs.
    *   Add support for different diff formats if needed.

*   **Adding New Pipelines**: Extend `run_inference.py` to support additional pipelines beyond `patch` and `judgement` for specialized tasks or experiments.

*   **Prompt Engineering**: Experiment with different prompt templates to improve LLM performance on specific types of proof engineering tasks. Prompt templates can be modified in the model adapter classes.

---

Next: [Evaluation Pipeline: Syntactic & Semantic Checks](./04_4_apebench_evaluation.md)

<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 4.3 LLM 推理与 DiffRepair

本节涵盖使用大型语言模型 (LLM) 生成补丁的过程以及对这些补丁进行后处理的关键 `DiffRepair` 实用程序。相关代码主要位于 `src/apebench/inference/` 及其子模块中，例如 `src/apebench/inference/utils/diff_repair.py`。

## LLM 推理过程

LLM 在 APE-Bench I 中的核心任务是根据 `Instruction` 生成一个补丁（统一差异格式），以转换给定的 `PreFile`。

1.  **入口点**：推理的主要入口点是 `src/apebench/inference/run_inference.py`，它支持多个流程，包括：
    *   `patch` 流程：根据指令生成修补后的代码
    *   `judgement` 流程：使用作为裁判的 LLM 评估补丁
    *   这两个流程都处理数据准备、模型调用和结果收集。

2.  **提示构建**：为每个任务构建目标 LLM 的提示。这通常包括：
    *   `Instruction` (自然语言命令)。
    *   `PreFile` (编辑前的完整 Lean 代码)。
    *   格式化指令，以指导 LLM 输出结构正确的补丁。
    *   提示模板是特定于模型的，并在相应的模型适配器类中定义。

3.  **模型调用**：推理框架支持各种 LLM 提供商：
    *   每个受支持的模型在 `src/apebench/inference/models/` 中都有一个适配器。
    *   这些适配器处理不同 API 的 API 身份验证、请求格式化和响应解析。
    *   `src/apebench/inference/run_inference.py` 中的 `modelmap` 字典将模型名称映射到其各自的适配器类。
    *   诸如 `temperature`、`max_tokens` 和 `n_responses`（用于对多个候选进行采样）等关键参数会传递给相应的 API。

4.  **输出处理**：
    *   解析原始 LLM 输出以提取生成的补丁。
    *   对于 `patch` 流程，通常会对提取的补丁应用 `DiffRepair`（见下文）。
    *   处理后的输出以结构化格式保存到指定的输出文件中。

5.  **并行性**：处理过程可以分布在多个工作进程中（使用 `ProcessPoolExecutor`）以加速大型数据集的推理，由 `--max_workers` 参数控制。

运行推理的命令可能如下所示：
```bash
python -m src.apebench.inference.run_inference \
    --pipeline patch \
    --input_file /path/to/tasks.jsonl \
    --output_file /path/to/results.jsonl \
    --model_name gpt-4o \
    --temperature 0.8 \
    --n_responses 20 \
    --max_workers 4
```

## DiffRepair：容错补丁恢复

LLM 生成的差异通常是"嘈杂的"——它们可能具有不正确的行号、未对齐的上下文行或格式问题，从而阻止使用标准 `patch` 实用程序将其干净地应用。`DiffRepair` 是为解决此问题而设计的至关重要的组件。

*   **位置**：`src/apebench/inference/utils/diff_repair.py`
*   **目的**：将模型生成的嘈杂差异转换为干净、结构一致且可应用的补丁，同时尽可能保留编辑的原始意图。
*   **论文提及**：第 5.1 节（补丁规范化）和附录 A。

**DiffRepair 工作流程（如论附录 A 所述）：**

1.  **Hunk 解析**：将输入的差异文本解析为单独的"Hunk"（更改段）。
2.  **意图定位（模糊匹配）**：对于每个 Hunk，`DiffRepair` 尝试在 `PreFile` 中找到更改意图的正确区域。这是一个关键步骤，涉及：
    *   比较 Hunk 中的上下文行与 `PreFile` 中的行。
    *   使用模糊匹配算法（例如，Levenshtein 距离、序列匹配）来容忍微小的差异。
    *   `diff_repair.py` 中的 `_find_candidate_region_exact` 和 `_find_best_region_with_dp` 方法表明了复杂的匹配逻辑，包括动态规划。
3.  **补丁重建**：一旦定位到目标区域，`DiffRepair` 会重建一个干净的差异 Hunk：
    *   相对于从 `PreFile` 中正确识别的上下文，将添加和删除的行重新对齐到结构有效的位置。
    *   扩充缺失的上下文行以满足统一差异格式的约束。
    *   解决行号偏移和潜在的 Hunk 重叠。
4.  **最终差异生成**：将修复后的 Hunk 组合成最终的、干净的统一差异字符串。

**代码中 `DiffRepair` (`diff_repair.py`) 的关键方面：**
*   处理带有 `@@ ... @@` 标头的标准差异和非标准差异。
*   规范化行（去除空白、小写化）以实现更稳健的匹配。
*   结合使用精确匹配和模糊匹配技术。
*   `repair()` 方法协调给定差异的整个过程。
*   可以根据更改的重要性筛选重叠的 Hunk。

论文的表 3 显示了修复前后补丁应用成功率，突出了 `DiffRepair` 的重要性。

## 用法

*   **LLM 推理**：主要接口是 `run_inference.py`，它支持各种命令行参数：
    ```bash
    python -m src.apebench.inference.run_inference --help
    ```
    常用参数包括 `--pipeline`、`--input_file`、`--output_file`、`--model_name`、`--temperature` 和 `--n_responses`。

*   **DiffRepair 配置**：可以通过 APE-Bench 配置文件中的参数来配置 DiffRepair 的行为：
    ```yaml
    # DiffRepair 的示例配置
    diffrepair:
      enabled: true  # 是否应用 DiffRepair
      exact_match: false  # 是否仅使用精确匹配
      strict_match_threshold: 0.8  # 模糊匹配的阈值
    ```

## 二次开发

*   **集成新的 LLM**：
    1.  在 `src/apebench/inference/models/` 中创建一个新的模型适配器类，实现必要的 API 交互。
    2.  将模型添加到 `run_inference.py` 中的 `modelmap` 字典中。
    3.  在适当的配置文件中配置模型，包括任何特定于模型的参数。
    4.  如果现有模板不适用，则可以选择为新模型创建自定义提示模板。

*   **改进 DiffRepair**：
    *   增强模糊匹配算法以获得更好的定位准确性或速度。
    *   改进 Hunk 重建逻辑以处理更复杂或格式错误的差异。
    *   如果需要，添加对不同差异格式的支持。

*   **添加新的流程**：扩展 `run_inference.py` 以支持除 `patch` 和 `judgement` 之外的其他流程，用于专门的任务或实验。

*   **提示工程**：尝试使用不同的提示模板来提高 LLM 在特定类型的证明工程任务上的性能。可以在模型适配器类中修改提示模板。

---

下一节: [评估流程：语法与语义检查](./04_4_apebench_evaluation.md) 