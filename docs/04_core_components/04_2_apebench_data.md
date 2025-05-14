[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 4.2 Data Handling: Tasks and Format

This section describes how APE-Bench I tasks are structured, where the data comes from, and how it's likely handled by the `src/apebench/data/` modules.

## Task Format

As detailed in the APE-Bench I paper (Section 3.1), each task in the benchmark is a triplet: `(Instruction, PreFile, Patch)`.

*   **`Instruction`**: A natural language string describing the intended modification to a Lean file. This serves as the main prompt for the LLM being evaluated.
    *   *Example*: "Refactor the proof of `theorem_xyz` to use `lemma_abc`." or "Add a new definition `new_function` with the following properties..."
*   **`PreFile`**: A string containing the complete Lean source code of the target file *before* the edit. This provides the full context for the LLM.
*   **`Patch`**: A string in the unified diff format that encodes the ground-truth edit. This patch, when applied to `PreFile`, should result in the desired post-edit state of the file.
    *   This is used as the reference for evaluating LLM-generated patches, although direct diff matching is not the primary success metric (semantic correctness is key).

Additional metadata associated with each task (especially in the test set) includes:
*   **Task ID**: A unique identifier for the task.
*   **Commit SHA**: The Mathlib4 commit from which the task was derived.
*   **File Path**: The path to the specific Lean file within the Mathlib commit.
*   **Task Category**: E.g., `Feature`, `Refactor`, `Bug Fix` (as per paper, Section 3.3).
*   **Difficulty Level**: E.g., `Easy`, `Medium`, `Hard` (as per paper, Section 3.3).

## Data Source

The APE-Bench I dataset is hosted on Hugging Face:
*   **URL**: [https://huggingface.co/datasets/HuajianXin/APE-Bench_I](https://huggingface.co/datasets/HuajianXin/APE-Bench_I)

During setup, you are instructed to clone this dataset into the `datasets/` directory within your project.
The dataset files are typically in a structured format like JSONL (JSON lines), where each line or entry corresponds to a single task and contains the fields mentioned above.

## Data Handling in `src/apebench/data/`

The modules within `src/apebench/data/` are responsible for:

*   **Loading Tasks**: Reading the benchmark data files (e.g., from `datasets/`) into memory.
*   **Parsing**: Extracting the `Instruction`, `PreFile`, `Patch`, and other metadata for each task.
*   **Data Representation**: Potentially converting the raw data into Python objects or dataclasses for easier use throughout the application (e.g., a `Task` object with attributes for each field).
*   **Splitting**: Handling different data splits (e.g., train, validation, test) if they are provided as separate files or indicated by a field within the data.
*   **Filtering/Selection**: Providing utilities to select specific tasks based on criteria like ID, category, or difficulty, which can be useful for targeted experiments or debugging.

**Example (Conceptual) Usage:**

```python
# Conceptual code that might be found or used with src/apebench/data/
# from apebench.data import load_tasks, Task

# benchmark_tasks = load_tasks("datasets/test.jsonl")

# for task in benchmark_tasks:
#     print(f"Task ID: {task.id}")
#     print(f"Instruction: {task.instruction}")
#     # model_input = task.pre_file
#     # reference_patch = task.patch
#     # ... use task data for LLM prompting and evaluation
```

## Secondary Development

*   **Supporting New Data Formats**: If future versions of APE-Bench or other custom datasets use different file formats (e.g., CSV, Parquet), the data loading and parsing logic in `src/apebench/data/` would need to be updated.
*   **Adding Data Augmentation**: For training purposes (though APE-Bench I is primarily an evaluation benchmark), one might add utilities here to augment existing tasks (e.g., paraphrasing instructions, synthesizing new PreFile contexts).
*   **Interfacing with Different Data Storage**: If tasks were stored in a database instead of flat files, these modules would need to be adapted.

Understanding the data structure is fundamental for anyone working with the benchmark, whether for running evaluations or for analyzing the dataset itself.

---
<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 4.2 数据处理：任务与格式

本节描述 APE-Bench I 任务的结构、数据来源以及 `src/apebench/data/` 模块可能如何处理这些数据。

## 任务格式

正如 APE-Bench I 论文（第 3.1 节）所述，基准测试中的每个任务都是一个三元组：`(Instruction, PreFile, Patch)`。

*   **`Instruction` (指令)**：一个自然语言字符串，描述对 Lean 文件的预期修改。这是被评估 LLM 的主要提示。
    *   *示例*："将 `theorem_xyz` 的证明重构为使用 `lemma_abc`。"或"添加一个具有以下属性的新定义 `new_function`..."
*   **`PreFile` (修改前文件)**：一个包含编辑前目标文件完整 Lean 源代码的字符串。这为 LLM 提供了完整的上下文。
*   **`Patch` (补丁)**：一个统一差异格式的字符串，编码了真实的编辑。当此补丁应用于 `PreFile` 时，应产生文件所需的编辑后状态。
    *   这被用作评估 LLM 生成补丁的参考，尽管直接的差异匹配不是主要的成功指标（语义正确性是关键）。

与每个任务（尤其是在测试集中）相关的其他元数据包括：
*   **Task ID (任务 ID)**：任务的唯一标识符。
*   **Commit SHA (提交 SHA)**：任务来源的 Mathlib4 提交的 SHA 值。
*   **File Path (文件路径)**：Mathlib 提交中特定 Lean 文件的路径。
*   **Task Category (任务类别)**：例如 `Feature` (功能)、`Refactor` (重构)、`Bug Fix` (错误修复) (根据论文第 3.3 节)。
*   **Difficulty Level (难度级别)**：例如 `Easy` (简单)、`Medium` (中等)、`Hard` (困难) (根据论文第 3.3 节)。

## 数据来源

APE-Bench I 数据集托管在 Hugging Face 上：
*   **URL**: [https://huggingface.co/datasets/HuajianXin/APE-Bench_I](https://huggingface.co/datasets/HuajianXin/APE-Bench_I)

在设置过程中，您需要将此数据集克隆到项目中的 `datasets/` 目录。
数据集文件通常采用结构化格式，如 JSONL（JSON 行），其中每行或每个条目对应一个任务，并包含上述字段。

## `src/apebench/data/` 中的数据处理

`src/apebench/data/` 中的模块负责：

*   **加载任务**：从内存中读取基准测试数据文件（例如，从 `datasets/`）。
*   **解析**：为每个任务提取 `Instruction`、`PreFile`、`Patch` 和其他元数据。
*   **数据表示**：可能将原始数据转换为 Python 对象或数据类，以便在整个应用程序中更轻松地使用（例如，一个具有每个字段属性的 `Task` 对象）。
*   **拆分**：处理不同的数据拆分（例如，训练集、验证集、测试集），如果它们作为单独的文件提供或由数据中的某个字段指示。
*   **筛选/选择**：提供根据 ID、类别或难度等标准选择特定任务的实用程序，这对于有针对性的实验或调试非常有用。

**示例 (概念性) 用法：**

```python
# 可能在 src/apebench/data/ 中找到或使用的概念性代码
# from apebench.data import load_tasks, Task

# benchmark_tasks = load_tasks("datasets/test.jsonl")

# for task in benchmark_tasks:
#     print(f"Task ID: {task.id}")
#     print(f"Instruction: {task.instruction}")
#     # model_input = task.pre_file
#     # reference_patch = task.patch
#     # ... 使用任务数据进行 LLM 提示和评估
```

## 二次开发

*   **支持新的数据格式**：如果 APE-Bench 的未来版本或其他自定义数据集使用不同的文件格式（例如 CSV、Parquet），则需要更新 `src/apebench/data/` 中的数据加载和解析逻辑。
*   **添加数据增强**：出于训练目的（尽管 APE-Bench I 主要是一个评估基准测试），可以在此处添加实用程序来增强现有任务（例如，释义指令、合成新的 PreFile 上下文）。
*   **与不同的数据存储对接**：如果任务存储在数据库而不是平面文件中，则需要调整这些模块。

无论是运行评估还是分析数据集本身，理解数据结构对于任何使用该基准测试的人来说都是至关重要的。

---

下一节: [LLM 推理与 DiffRepair](./04_3_apebench_inference.md) 