[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

<div align="center">
 👋 Hi, everyone! 
    <br>
    We are <b>ByteDance Seed team.</b>
</div>

<p align="center">
  You can get to know us better through the following channels👇
  <br>
  <a href="https://seed.bytedance.com/">
    <img src="https://img.shields.io/badge/Website-%231e37ff?style=for-the-badge&logo=bytedance&logoColor=white"></a>
  <a href="https://github.com/user-attachments/assets/5793e67c-79bb-4a59-811a-fcc7ed510bd4">
    <img src="https://img.shields.io/badge/WeChat-07C160?style=for-the-badge&logo=wechat&logoColor=white"></a>
 <a href="https://www.xiaohongshu.com/user/profile/668e7e15000000000303157d?xsec_token=ABl2-aqekpytY6A8TuxjrwnZskU-6BsMRE_ufQQaSAvjc%3D&xsec_source=pc_search">
    <img src="https://img.shields.io/badge/Xiaohongshu-%23FF2442?style=for-the-badge&logo=xiaohongshu&logoColor=white"></a>
  <a href="https://www.zhihu.com/org/dou-bao-da-mo-xing-tuan-dui/">
    <img src="https://img.shields.io/badge/zhihu-%230084FF?style=for-the-badge&logo=zhihu&logoColor=white"></a>
</p>

![seed logo](https://github.com/user-attachments/assets/c42e675e-497c-4508-8bb9-093ad4d1f216)

# APE-Bench I: An Automated Proof Engineering Benchmark

<p align="center">
  <a href="https://arxiv.org/abs/2504.19110">
    <img src="https://img.shields.io/badge/APE--Bench_I-Paper-red"></a>
  <a href="https://huggingface.co/datasets/HuajianXin/APE-Bench_I">
    <img src="https://img.shields.io/badge/APE--Bench_I-Hugging Face Dataset-orange"></a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue"></a>
  <a href="./docs/README.md">
    <img src="https://img.shields.io/badge/Documentation-View_Docs-green"></a>
  <a href="https://github.com/xinhjBrant/APE-Bench_I">
    <img src="https://img.shields.io/badge/GitHub-Repository-lightgrey"></a>
</p>

**APE-Bench I** is a comprehensive benchmark and accompanying codebase for evaluating the capabilities of Large Language Models (LLMs) in the domain of automated proof engineering within the Lean 4 theorem proving environment. This project is the official implementation for the research paper "[APE-Bench I: Towards File-level Automated Proof Engineering of Formal Math Libraries](https://arxiv.org/abs/2504.19110)".

The benchmark focuses on realistic proof engineering tasks, such as bug fixing, feature implementation, and refactoring within the context of the [Mathlib4](https://github.com/leanprover-community/mathlib4) library. A core component of this project is **Eleanstic**, an efficient, version-aware Lean/Mathlib environment designed to manage and verify Lean code against specific historical Mathlib commit states with significantly reduced computational and storage overhead.

Welcome to explore the codebase and contribute to the advancement of AI in formal mathematics!

## Table of Contents
* [Introduction](#introduction)
* [Key Features](#key-features)
* [Project Structure](#project-structure)
* [Getting Started](#getting-started)
* [Basic Workflow](#basic-workflow)
* [Documentation](#documentation)
* [License](#license)
* [Citation](#citation)
* [About ByteDance Seed Team](#about-bytedance-seed-team)

## Introduction

Automated proof engineering aims to leverage AI to assist mathematicians and developers in creating, maintaining, and verifying formal proofs. APE-Bench I provides a standardized set of tasks derived from real-world Mathlib4 development activities, enabling rigorous assessment of LLMs on their ability to generate correct and meaningful code patches.

This repository contains:
*   The **APE-Bench I dataset** specification.
*   The **Eleanstic** system for efficient, version-aware Lean verification.
*   The **APE-Bench core codebase** for task execution, patch generation via LLMs, the `DiffRepair` utility for patch normalization, and a two-stage evaluation pipeline (syntactic and semantic).
*   Scripts and configurations to reproduce paper results and run new experiments.
*   Comprehensive [documentation](./docs/README.md).

## Key Features

*   **Realistic Benchmark Tasks**: A curated set of tasks covering bug fixes, feature implementations, and refactoring in Lean 4, based on Mathlib4 history.
*   **Eleanstic**: A novel system for managing multiple Mathlib4 versions efficiently. It uses content-addressable storage (CAS) and snapshotting to enable rapid restoration and verification of Lean code against specific commit states, drastically reducing disk space and setup time.
*   **DiffRepair Utility**: A robust tool to parse, clean, and apply noisy, LLM-generated diff patches, significantly improving patch application success rates.
*   **Two-Stage Evaluation**:
    1.  **Syntactic Verification**: Uses Eleanstic to compile and check the patched Lean code against the correct Mathlib version.
    2.  **Semantic Judgement**: Employs an "LLM-as-a-Judge" approach to assess whether syntactically valid patches correctly fulfill the task's natural language instruction.
*   **Modular and Extensible Codebase**: Designed to facilitate the integration of new LLMs, custom datasets, and novel evaluation methodologies.
*   **Reproducibility**: Provides tools and configurations to replicate the experiments and results presented in the APE-Bench I paper.

## Project Structure

```
.
├── datasets/                 # Placeholder for APE-Bench I dataset files
├── docs/                     # Comprehensive project documentation
│   ├── 01_introduction.md
│   ├── 02_setup.md
│   ├── ...
│   └── 04_core_components/
│       ├── 04_1_eleanstic.md
│       └── ...
├── src/
│   ├── apebench/             # Core APE-Bench logic (inference, evaluation, etc.)
│   │   ├── config/
│   │   ├── data/
│   │   ├── evaluation_pipelines/
│   │   ├── inference/
│   │   └── scripts/
│   └── eleanstic/            # Eleanstic system for version-aware Lean verification
│       ├── core/
│       ├── utils/
│       └── main.py
├── README.md                 # This file
├── requirements.txt          # Python dependencies
└── ...                       # Other configuration and script files
```

## Getting Started

For detailed instructions on setting up the environment, installing dependencies, and downloading the dataset, please refer to [docs/02_setup.md](./docs/02_setup.md).

For a comprehensive guide on the main workflow, including running the benchmark pipeline (patch generation, verification, and evaluation), please see the **General APE-Bench Workflow** section in [docs/05_workflow_guides.md](./docs/05_workflow_guides.md).

## Basic Workflow

The typical workflow for using APE-Bench I involves:

1.  **Patch Generation**: Use an LLM to generate patches for tasks in the APE-Bench I dataset.
    ```bash
    python -m src.apebench.inference.run_inference --pipeline patch --config path/to/your_config.yaml ...
    ```
2.  **Syntactic Verification**: Verify the grammatical correctness and type-safety of generated patches using Eleanstic.
    ```bash
    python -m src.apebench.evaluation_pipelines.verification_manager --config path/to/your_config.yaml ...
    ```
3.  **Semantic Evaluation**: Assess whether syntactically correct patches fulfill the task's intent using an LLM-as-a-Judge.
    ```bash
    python -m src.apebench.evaluation_pipelines.evaluation_manager --config path/to/your_config.yaml ...
    ```

For detailed guides on reproducing paper results, evaluating new LLMs, or running custom experiments, please see the [**Workflow Guides (`docs/05_workflow_guides.md`)**](./docs/05_workflow_guides.md).

## Documentation

Comprehensive documentation for the APE-Bench I project, including detailed setup instructions, explanations of core components, workflow guides, and development information, can be found in the [**`./docs` directory**](./docs/README.md).

## License
This project is licensed under the **MIT License**. See the [LICENSE](./LICENSE) file for details.

## Citation
If you use APE-Bench I or Eleanstic in your research, please cite our paper:

```bibtex
@article{xin2025apebench,
    title={{APE-Bench I}: Towards File-level Automated Proof Engineering of Formal Math Libraries},
    author={Huajian Xin and Luming Li and Xiaoran Jin and Jacques Fleuriot and Wenda Li},
    year={2025},
    journal={arXiv preprint arXiv:2504.19110}
}
```

## About [ByteDance Seed Team](https://seed.bytedance.com/)

Founded in 2023, ByteDance Seed Team is dedicated to crafting the industry's most advanced AI foundation models. The team aspires to become a world-class research team and make significant contributions to the advancement of science and society.

---
<a name="chinese-version"></a>

<div align="center">
 👋 大家好！
    <br>
    我们是<b>字节跳动 Seed 团队。</b>
</div>

<p align="center">
  您可以通过以下渠道更好地了解我们👇
  <br>
  <a href="https://seed.bytedance.com/">
    <img src="https://img.shields.io/badge/Website-%231e37ff?style=for-the-badge&logo=bytedance&logoColor=white"></a>
  <a href="https://github.com/user-attachments/assets/5793e67c-79bb-4a59-811a-fcc7ed510bd4">
    <img src="https://img.shields.io/badge/WeChat-07C160?style=for-the-badge&logo=wechat&logoColor=white"></a>
 <a href="https://www.xiaohongshu.com/user/profile/668e7e15000000000303157d?xsec_token=ABl2-aqekpytY6A8TuxjrwnZskU-6BsMRE_ufQQaSAvjc%3D&xsec_source=pc_search">
    <img src="https://img.shields.io/badge/Xiaohongshu-%23FF2442?style=for-the-badge&logo=xiaohongshu&logoColor=white"></a>
  <a href="https://www.zhihu.com/org/dou-bao-da-mo-xing-tuan-dui/">
    <img src="https://img.shields.io/badge/zhihu-%230084FF?style=for-the-badge&logo=zhihu&logoColor=white"></a>
</p>

![seed logo](https://github.com/user-attachments/assets/c42e675e-497c-4508-8bb9-093ad4d1f216)

# APE-Bench I: 自动化证明工程基准测试

<p align="center">
  <a href="https://arxiv.org/abs/2504.19110">
    <img src="https://img.shields.io/badge/APE--Bench_I-Paper-red"></a>
  <a href="https://huggingface.co/datasets/HuajianXin/APE-Bench_I">
    <img src="https://img.shields.io/badge/APE--Bench_I-Hugging Face Dataset-orange"></a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue"></a>
  <a href="./docs/README.md">
    <img src="https://img.shields.io/badge/Documentation-View_Docs-green"></a>
  <a href="https://github.com/xinhjBrant/APE-Bench_I">
    <img src="https://img.shields.io/badge/GitHub-Repository-lightgrey"></a>
</p>

**APE-Bench I** 是一个全面的基准测试和配套代码库，用于评估大型语言模型 (LLM) 在 Lean 4 定理证明环境中自动化证明工程领域的能力。本项目是研究论文"[APE-Bench I: Towards File-level Automated Proof Engineering of Formal Math Libraries](https://arxiv.org/abs/2504.19110)"的官方实现。

该基准测试专注于真实的证明工程任务，例如在 [Mathlib4](https://github.com/leanprover-community/mathlib4) 库的上下文中进行错误修复、功能实现和重构。本项目的核心组件是 **Eleanstic**，这是一个高效的、版本感知的 Lean/Mathlib 环境，旨在以显著降低的计算和存储开销，管理和验证针对特定历史 Mathlib 提交状态的 Lean 代码。

欢迎探索代码库并为人工智能在形式数学领域的进步做出贡献！

## 目录
* [引言](#引言)
* [主要特性](#主要特性)
* [项目结构](#项目结构)
* [快速上手](#快速上手)
* [基本工作流](#基本工作流)
* [文档](#文档)
* [许可证](#许可证)
* [引用](#引用)
* [关于字节跳动 Seed 团队](#关于字节跳动-seed-团队)

## 引言

自动化证明工程旨在利用人工智能协助数学家和开发人员创建、维护和验证形式证明。APE-Bench I 提供了一套源自真实 Mathlib4 开发活动的标准化任务，从而能够严格评估 LLM 生成正确且有意义的代码补丁的能力。

此代码仓库包含：
*   **APE-Bench I 数据集**规范。
*   用于高效、版本感知的 Lean 验证的 **Eleanstic** 系统。
*   **APE-Bench 核心代码库**，用于任务执行、通过 LLM 生成补丁、用于补丁规范化的 `DiffRepair` 实用程序以及两阶段评估流程（语法和语义）。
*   用于复现论文结果和运行新实验的脚本和配置。
*   全面的[文档](./docs/README.md)。

## 主要特性

*   **真实的基准测试任务**：一组精选的任务，涵盖 Lean 4 中的错误修复、功能实现和重构，基于 Mathlib4 的历史记录。
*   **Eleanstic**：一个新颖的系统，用于高效管理多个 Mathlib4 版本。它使用内容寻址存储 (CAS) 和快照技术，可以快速恢复和验证针对特定提交状态的 Lean 代码，从而大大减少磁盘空间和设置时间。
*   **DiffRepair 实用程序**：一个强大的工具，用于解析、清理和应用 LLM 生成的嘈杂的差异补丁，显著提高补丁应用成功率。
*   **两阶段评估**：
    1.  **语法验证**：使用 Eleanstic 根据正确的 Mathlib 版本编译和检查修补后的 Lean 代码。
    2.  **语义判断**：采用"LLM 作为裁判"的方法来评估语法有效的补丁是否正确地满足了任务的自然语言指令。
*   **模块化和可扩展的代码库**：旨在促进新 LLM、自定义数据集和新颖评估方法的集成。
*   **可复现性**：提供工具和配置，以复制 APE-Bench I 论文中提出的实验和结果。

## 项目结构

```
.
├── datasets/                 # APE-Bench I 数据集文件占位符
├── docs/                     # 完整的项目文档
│   ├── 01_introduction.md
│   ├── 02_setup.md
│   ├── ...
│   └── 04_core_components/
│       ├── 04_1_eleanstic.md
│       └── ...
├── src/
│   ├── apebench/             # APE-Bench 核心逻辑 (推理、评估等)
│   │   ├── config/
│   │   ├── data/
│   │   ├── evaluation_pipelines/
│   │   ├── inference/
│   │   └── scripts/
│   └── eleanstic/            # 用于版本感知 Lean 验证的 Eleanstic 系统
│       ├── core/
│       ├── utils/
│       └── main.py
├── README.md                 # 此文件
├── requirements.txt          # Python 依赖项
└── ...                       # 其他配置和脚本文件
```

## 快速上手

有关设置环境、安装依赖项和下载数据集的详细说明，请参阅 [docs/02_setup.md](./docs/02_setup.md)。

有关主要工作流程的全面指南，包括运行基准测试流水线（补丁生成、验证和评估），请参阅 [docs/05_workflow_guides.md](./docs/05_workflow_guides.md) 中的 **APE-Bench 核心工作流程**部分。

## 基本工作流

使用 APE-Bench I 的典型工作流包括：

1.  **补丁生成**：使用 LLM 为 APE-Bench I 数据集中的任务生成补丁。
    ```bash
    python -m src.apebench.inference.run_inference --pipeline patch --config path/to/your_config.yaml ...
    ```
2.  **语法验证**：使用 Eleanstic 验证生成的补丁的语法正确性和类型安全性。
    ```bash
    python -m src.apebench.evaluation_pipelines.verification_manager --config path/to/your_config.yaml ...
    ```
3.  **语义评估**：使用"LLM 作为裁判"评估语法正确的补丁是否满足任务的意图。
    ```bash
    python -m src.apebench.evaluation_pipelines.evaluation_manager --config path/to/your_config.yaml ...
    ```

有关复现论文结果、评估新 LLM 或运行自定义实验的详细指南，请参阅[**工作流指南 (`docs/05_workflow_guides.md`)**](./docs/05_workflow_guides.md)。

## 文档

APE-Bench I 项目的完整文档，包括详细的设置说明、核心组件的解释、工作流指南和开发信息，可以在 [**`./docs` 目录**](./docs/README.md)中找到。

## 许可证
本项目根据 **MIT 许可证**授权。有关详细信息，请参阅 [LICENSE](./LICENSE) 文件。

## 引用
如果您在研究中使用 APE-Bench I 或 Eleanstic，请引用我们的论文：

```bibtex
@article{xin2025apebench,
    title={{APE-Bench I}: Towards File-level Automated Proof Engineering of Formal Math Libraries},
    author={Huajian Xin and Luming Li and Xiaoran Jin and Jacques Fleuriot and Wenda Li},
    year={2025},
    journal={arXiv preprint arXiv:2504.19110}
}
```

## 关于[字节跳动 Seed 团队](https://seed.bytedance.com/)

字节跳动 Seed 团队成立于 2023 年，致力于打造业界最先进的人工智能基础模型。团队渴望成为世界一流的研究团队，为科学和社会的进步做出重大贡献。