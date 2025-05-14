[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 3. Project Structure

This document provides a high-level overview of the APE-Bench I project's directory structure.

```
ape-bench/
├── .git/               # Git repository data
├── .venv/              # Python virtual environment (recommended)
├── configs/            # General configuration files for experiments (if any)
├── datasets/           # Downloaded APE-Bench I dataset from Hugging Face
├── docs/               # This documentation
│   ├── README.md
│   ├── 01_introduction.md
│   ├── ... (other documentation files)
│   └── 04_core_components/
│       └── ... (component-specific docs)
├── paper.tex           # LaTeX source for the research paper
├── README.md           # Main project README (points to Hugging Face dataset)
├── requirements.txt    # Python dependencies
├── src/
│   ├── __init__.py
│   ├── apebench/       # Core logic for APE-Bench I framework
│   │   ├── __init__.py
│   │   ├── config/     # Configuration for APE-Bench components (models, paths)
│   │   ├── data/       # Data loading, processing, task representation
│   │   ├── evaluation_pipelines/ # Syntactic and semantic evaluation logic
│   │   ├── inference/  # LLM interaction, patch generation, DiffRepair
│   │   │   └── utils/  # Utilities for inference, e.g., diff_repair.py
│   │   └── scripts/    # Scripts for running experiments, analysis
│   │   └── utils/      # General utilities for apebench module
│   ├── eleanstic/      # Eleanstic: version-aware syntactic verification
│   │   ├── __init__.py
│   │   ├── config.yaml # Configuration for Eleanstic
│   │   ├── core/       # Core logic for Eleanstic (snapshotting, CAS)
│   │   ├── main.py     # Main script/entry point for Eleanstic operations
│   │   └── utils/      # Utilities specific to Eleanstic
│   └── utils/          # Shared utility functions (if any at src level)
└── ...                 # Other project files (e.g., .gitignore)
```

## Key Directories

*   **`configs/`**: May contain high-level configuration files for orchestrating different experimental setups. More specific configurations are often found within `src/apebench/config/` and `src/eleanstic/config.yaml`.

*   **`datasets/`**: This directory (created by you during setup) holds the actual benchmark data – the collection of (`Instruction`, `PreFile`, `Patch`) triplets.

*   **`docs/`**: Contains all the documentation files you are currently reading.

*   **`src/`**: The heart of the project, containing all source code.
    *   **`src/apebench/`**: Implements the core APE-Bench I framework. This is where most of the logic for running experiments, interacting with LLMs, and evaluating results resides.
        *   `config/`: Specific configurations for APE-Bench, such as model parameters, API endpoints, file paths relevant to benchmark runs.
        *   `data/`: Modules for loading, parsing, and managing the APE-Bench I tasks from the `datasets/` directory.
        *   `evaluation_pipelines/`: Contains the code for the two-stage evaluation process: syntactic verification (interfacing with Eleanstic) and semantic judgment (LLM-as-a-Judge).
        *   `inference/`: Handles the generation of patches by LLMs. This includes constructing prompts, making API calls to various models, and processing their outputs. The critical `DiffRepair` utility (`inference/utils/diff_repair.py`) is also part of this module.
        *   `scripts/`: Contains Python scripts that act as entry points for various operations, such as running a full evaluation pass for a model, generating specific analyses, or preparing data.
    *   **`src/eleanstic/`**: A self-contained module that implements the Eleanstic system. Its primary role is to provide efficient and version-aware syntactic verification of Lean code by managing Mathlib build artifacts.
        *   `config.yaml`: The main configuration file for Eleanstic, defining paths to Mathlib, storage locations, etc.
        *   `core/`: The core implementation of Eleanstic's content-addressable storage, snapshot management, and environment restoration logic.
        *   `main.py`: Often the main executable or entry point for Eleanstic operations like preprocessing Mathlib commits or servicing verification requests.

Understanding this structure will help you navigate the codebase when trying to understand specific functionalities or when planning secondary development.

---
<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 3. 项目结构

本文档提供了 APE-Bench I 项目目录结构的高级概述。

```
ape-bench/
├── .git/               # Git 仓库数据
├── .venv/              # Python 虚拟环境 (推荐)
├── configs/            # 实验的通用配置文件 (如果有)
├── datasets/           # 从 Hugging Face 下载的 APE-Bench I 数据集
├── docs/               # 本文档
│   ├── README.md
│   ├── 01_introduction.md
│   ├── ... (其他文档文件)
│   └── 04_core_components/
│       └── ... (组件特定文档)
├── paper.tex           # 研究论文的 LaTeX 源文件
├── README.md           # 项目主 README (指向 Hugging Face 数据集)
├── requirements.txt    # Python 依赖
├── src/
│   ├── __init__.py
│   ├── apebench/       # APE-Bench I 框架的核心逻辑
│   │   ├── __init__.py
│   │   ├── config/     # APE-Bench 组件的配置 (模型、路径)
│   │   ├── data/       # 数据加载、处理、任务表示
│   │   ├── evaluation_pipelines/ # 语法和语义评估逻辑
│   │   ├── inference/  # LLM 交互、补丁生成、DiffRepair
│   │   │   └── utils/  # 推理工具，例如 diff_repair.py
│   │   └── scripts/    # 运行实验、分析的脚本
│   │   └── utils/      # apebench 模块的通用工具
│   ├── eleanstic/      # Eleanstic：版本感知的语法验证
│   │   ├── __init__.py
│   │   ├── config.yaml # Eleanstic 的配置文件
│   │   ├── core/       # Eleanstic 的核心逻辑 (快照、CAS)
│   │   ├── main.py     # Eleanstic 操作的主脚本/入口点
│   │   └── utils/      # Eleanstic 特定的工具
│   └── utils/          # 共享的工具函数 (如果在 src 级别有的话)
└── ...                 # 其他项目文件 (例如 .gitignore)
```

## 关键目录

*   **`configs/`**: 可能包含用于编排不同实验设置的高级配置文件。更具体的配置通常位于 `src/apebench/config/` 和 `src/eleanstic/config.yaml` 中。

*   **`datasets/`**: 此目录（在设置过程中由您创建）包含实际的基准测试数据——(`指令`, `修改前文件`, `补丁`) 三元组的集合。

*   **`docs/`**: 包含您当前正在阅读的所有文档文件。

*   **`src/`**: 项目的核心，包含所有源代码。
    *   **`src/apebench/`**: 实现核心 APE-Bench I 框架。大部分运行实验、与 LLM 交互以及评估结果的逻辑都位于此处。
        *   `config/`: APE-Bench 的特定配置，例如模型参数、API 端点、与基准测试运行相关的文件路径。
        *   `data/`: 用于从 `datasets/` 目录加载、解析和管理 APE-Bench I 任务的模块。
        *   `evaluation_pipelines/`: 包含两阶段评估过程的代码：语法验证（与 Eleanstic 对接）和语义判断（作为裁判的 LLM）。
        *   `inference/`: 处理由 LLM 生成补丁。这包括构建提示、调用各种模型的 API 以及处理其输出。关键的 `DiffRepair` 工具 (`inference/utils/diff_repair.py`) 也是此模块的一部分。
        *   `scripts/`: 包含作为各种操作入口点的 Python 脚本，例如为模型运行完整的评估遍、生成特定分析或准备数据。
    *   **`src/eleanstic/`**: 一个独立的模块，实现 Eleanstic 系统。其主要作用是通过管理 Mathlib 构建产物来提供高效且版本感知的 Lean 代码语法验证。
        *   `config.yaml`: Eleanstic 的主配置文件，定义 Mathlib 的路径、存储位置等。
        *   `core/`: Eleanstic 内容寻址存储、快照管理和环境恢复逻辑的核心实现。
        *   `main.py`: 通常是 Eleanstic 操作（如预处理 Mathlib 提交或服务验证请求）的主要可执行文件或入口点。

理解此结构将有助于您在尝试理解特定功能或计划二次开发时浏览代码库。

---

下一节: [核心组件](./04_core_components/04_1_eleanstic.md) 