[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 1. Introduction

Welcome to APE-Bench I, a project dedicated to advancing research in **Automated Proof Engineering (APE)** for formal mathematics libraries. This document provides an overview of the project, its motivations, and its connection to the accompanying research paper.

## Project Goals

The primary goal of the APE-Bench I project is to provide a robust framework and a realistic benchmark for evaluating and developing Large Language Models (LLMs) on tasks that mirror the complexities of real-world formal proof engineering. This involves:

*   **Moving Beyond Isolated Theorem Proving**: Shifting the focus from solving standalone mathematical problems to performing engineering tasks (feature addition, refactoring, bug fixing) within the context of large, evolving formal libraries like Lean's Mathlib4.
*   **Establishing a Realistic Benchmark**: APE-Bench I offers tasks derived from actual `Mathlib4` commit histories, ensuring that evaluations reflect genuine development challenges.
*   **Facilitating Reproducible Research**: Providing the necessary tools, codebase, and standardized evaluation protocols for consistent and comparable assessment of LLM capabilities.
*   **Driving Future Development**: Laying the groundwork for more sophisticated AI agents capable of complex, multi-step reasoning and interaction within formal systems.

## Relation to the APE-Bench Paper

This codebase is the official implementation accompanying the research paper: **"APE-Bench I: Towards File-level Automated Proof Engineering of Formal Math Libraries."**

The paper introduces:

*   The **Automated Proof Engineering (APE)** paradigm.
*   The **APE-Bench I** benchmark, including its construction methodology, task format (Instruction, PreFile, Patch), and dataset statistics.
*   **Eleanstic**: A scalable, version-aware infrastructure for efficient syntactic verification of Lean code across multiple Mathlib versions.
*   A **two-stage evaluation protocol**: Combining syntactic verification (via Eleanstic and the Lean compiler) with semantic judgment (via an LLM-as-a-Judge).
*   **DiffRepair**: A fault-tolerant patch recovery system for cleaning and applying noisy LLM-generated diffs.
*   An **empirical study** of leading LLMs on APE-Bench I, highlighting current capabilities and limitations.

This project provides all the necessary components to:

*   Understand the technical details behind the paper's contributions.
*   Reproduce the experimental results presented in the paper.
*   Utilize the APE-Bench I framework for evaluating new LLMs or developing novel proof engineering techniques.

The subsequent sections of this documentation will guide you through the setup, structure, and usage of this codebase in detail.

---

Next: [Setup and Installation](./02_setup.md)

---
<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 1. 引言

欢迎来到 APE-Bench I，这是一个致力于推动形式化数学库的 **自动证明工程 (Automated Proof Engineering, APE)**研究的项目。本文档概述了该项目及其动机，以及它与配套研究论文之间的联系。

## 项目目标

APE-Bench I 项目的主要目标是提供一个强大的框架和一个现实的基准测试，用于评估和开发大型语言模型 (LLM) 处理那些能反映真实世界形式化证明工程复杂性的任务的能力。这包括：

*   **超越孤立的定理证明**：将焦点从解决独立的数学问题转移到在大型、不断发展的形式化库（如 Lean 的 Mathlib4）的背景下执行工程任务（功能添加、重构、错误修复）。
*   **建立现实的基准测试**：APE-Bench I 提供源自实际 `Mathlib4` 提交历史的任务，确保评估能反映真实的开发挑战。
*   **促进可复现的研究**：提供必要的工具、代码库和标准化的评估协议，以便对 LLM 的能力进行一致且可比较的评估。
*   **推动未来发展**：为更复杂的人工智能代理奠定基础，使其能够在形式化系统中进行复杂的多步骤推理和交互。

## 与 APE-Bench 论文的关系

本代码库是研究论文 **《APE-Bench I：面向形式化数学库文件级自动证明工程》** 的官方实现。

该论文介绍了：

*   **自动证明工程 (APE)** 的范式。
*   **APE-Bench I** 基准测试，包括其构建方法、任务格式（指令、修改前文件、补丁）和数据集统计。
*   **Eleanstic**：一个可扩展的、版本感知的基础设施，用于跨多个 Mathlib 版本高效进行 Lean 代码的语法验证。
*   **两阶段评估协议**：结合语法验证（通过 Eleanstic 和 Lean 编译器）和语义判断（通过作为裁判的 LLM）。
*   **DiffRepair**：一个容错的补丁恢复系统，用于清理和应用 LLM 生成的含噪声的差异。
*   一项关于领先 LLM 在 APE-Bench I 上的**实证研究**，突出了当前的能力和局限性。

本项目提供了所有必要的组件，以便：

*   理解论文章贡献背后的技术细节。
*   复现论文中提出的实验结果。
*   利用 APE-Bench I 框架评估新的 LLM 或开发新颖的证明工程技术。

本文档的后续部分将详细指导您完成此代码库的设置、结构和使用。

---

下一节: [安装与设置](./02_setup.md) 