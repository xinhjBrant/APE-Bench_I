[English](#english-version) | [中文](#chinese-version)
<a name="english-version"></a>

# 6. Troubleshooting

This section lists common issues encountered during setup or execution and provides potential solutions.

## Eleanstic Setup Issues

*   **Issue**: Eleanstic preprocessing fails or takes an extremely long time.
    *   **Cause**: Insufficient disk space for Mathlib clones, `.lake` build artifacts (before Eleanstic processes them), or the Eleanstic CAS store.
    *   **Solution**: Ensure ample free disk space (hundreds of GB may be needed temporarily for many commits). Check paths in `src/eleanstic/config.yaml` are correct and writable.
    *   **Cause**: `lake build` errors for specific Mathlib commits (e.g., network issues during `lake exe cache get`, toolchain problems).
    *   **Solution**: Ensure Lean and Lake are correctly installed and in PATH. Check Eleanstic logs for specific errors from `lake`. The `src/eleanstic/README.md` mentions retry mechanisms for `lake exe cache get`; ensure these are active or consider increasing retry attempts/timeouts if configurable. Some older Mathlib commits might have unique build issues; Eleanstic should ideally be robust to a few failing commits or allow skipping them if they are not critical for the benchmark set.
    *   **Cause**: Incorrect `mathlib_repo_path` in `src/eleanstic/config.yaml`.
    *   **Solution**: Verify the path points to a valid, up-to-date clone of `leanprover-community/mathlib4`.

*   **Issue**: Eleanstic CAS store grows excessively large despite deduplication.
    *   **Cause**: If many binary files (e.g., compiled `.olean` files) have minor, non-semantic differences across commits that defeat simple content hashing.
    *   **Solution**: This is an inherent challenge. Eleanstic's design aims to mitigate this. Ensure Eleanstic is correctly identifying and hashing files. For extreme cases, one might investigate more advanced binary diffing/patching for storage, but this would be a significant R&D effort for Eleanstic itself.

## LLM Inference Issues

*   **Issue**: API errors from LLMs (e.g., authentication, rate limits, model not found).
    *   **Solution**: 
        *   **Authentication**: Double-check API keys are correctly set as environment variables or in `src/apebench/config/` model configuration files.
        *   **Rate Limits**: Implement or enhance retry logic (e.g., exponential backoff, as provided by the `tenacity` library in `requirements.txt`) in the API calling modules in `src/apebench/inference/`. Consider reducing batch sizes or running inference for fewer tasks at a time.
        *   **Model Not Found**: Ensure the model names in your configuration match the exact identifiers used by the LLM provider's API.

*   **Issue**: LLM outputs are not in the expected diff format.
    *   **Solution**: Review and refine the prompting strategy used in `src/apebench/inference/`. Ensure prompts clearly instruct the LLM to output a unified diff. `DiffRepair` can handle some noise, but if the output is entirely unstructured, prompting is the primary fix.

*   **Issue**: `DiffRepair` fails to repair a patch or significantly alters its meaning.
    *   **Cause**: The LLM-generated diff is too divergent from the `PreFile` context, or `DiffRepair`'s fuzzy matching thresholds are too strict/loose.
    *   **Solution**: 
        *   Inspect the problematic raw diff and `PreFile`. 
        *   Experiment with `DiffRepair` parameters (e.g., `strict_match_threshold`, `exact_match` flag when initializing `DiffRepair` in the inference pipeline).
        *   For systematic issues, this might indicate a need to improve `DiffRepair`'s algorithms (see [LLM Inference and DiffRepair - Secondary Development](./04_core_components/04_3_apebench_inference.md)).

## Evaluation Issues

*   **Issue**: Syntactic verification (Lean compile) fails for patches that seem correct.
    *   **Cause**: Eleanstic might not be restoring the *exact* correct versioned environment (e.g., wrong snapshot, issue during file restoration from CAS).
    *   **Solution**: Verify Eleanstic setup. Check logs from Eleanstic and the Lean compiler for specific errors. Ensure the task's commit SHA is correctly mapped to the Eleanstic snapshot.
    *   **Cause**: The patch, even if repaired, introduces subtle Lean errors not obvious at first glance.
    *   **Solution**: Manually apply the patch to the `PreFile` (from the correct Mathlib commit, checked out locally) and try to compile with `lake env lean <file.lean>` to debug the Lean error directly.

*   **Issue**: Semantic Judgement (LLM-as-a-Judge) gives unexpected results.
    *   **Cause**: Prompting issues for the judge LLM; instability in judge LLM responses.
    *   **Solution**: Review the semantic evaluation prompts. Ensure the `sample@4` voting is working as expected. The APE-Bench I paper uses Claude Sonnet 3.7 (thinking mode); using a different judge model might require re-calibrating expectations or prompts.

## General Issues

*   **Issue**: Python `ModuleNotFoundError` or `ImportError`.
    *   **Solution**: Ensure your virtual environment is activated (`source venv/bin/activate`). Verify all dependencies in `requirements.txt` are installed correctly (`pip install -r requirements.txt`). Check `PYTHONPATH` if using complex project structures, though this should generally not be needed if the project is structured as a proper Python package.

*   **Issue**: Slow performance.
    *   **Cause**: LLM API calls can be slow. Eleanstic preprocessing is intensive but one-time per commit. Disk I/O for Eleanstic CAS on slow drives.
    *   **Solution**: 
        *   Use faster LLM models if available (though this changes the experiment).
        *   Ensure Eleanstic CAS and snapshot directories are on fast storage (SSD recommended).
        *   For inference, consider parallelizing API calls across multiple tasks if your API quotas and local resources allow (scripts in `src/apebench/scripts/` might already do this).

If you encounter an issue not listed here, please check existing GitHub issues for the project (if available) or consider reporting a new one with detailed information: steps to reproduce, error messages, relevant configuration, and environment details.

---

Next: [Development and Contribution Guide](./07_development_contribution.md)

<a name="chinese-version"></a>

## 中文翻译 (Chinese Translation)

# 6. 故障排除

本节列出了在设置或执行过程中遇到的常见问题及其潜在的解决方案。

## Eleanstic 设置问题

*   **问题**：Eleanstic 预处理失败或耗时过长。
    *   **原因**：Mathlib 克隆、`.lake` 构建产物（在 Eleanstic 处理它们之前）或 Eleanstic CAS 存储的磁盘空间不足。
    *   **解决方案**：确保有足够的可用磁盘空间（对于许多提交，可能临时需要数百 GB）。检查 `src/eleanstic/config.yaml` 中的路径是否正确且可写。
    *   **原因**：特定 Mathlib 提交的 `lake build` 错误（例如，`lake exe cache get` 期间的网络问题，工具链问题）。
    *   **解决方案**：确保 Lean 和 Lake 已正确安装并在 PATH 中。检查 Eleanstic 日志以获取来自 `lake` 的特定错误。`src/eleanstic/README.md` 提到了 `lake exe cache get` 的重试机制；确保这些机制已激活，或者如果可配置，则考虑增加重试次数/超时。一些较旧的 Mathlib 提交可能存在独特的构建问题；理想情况下，Eleanstic 应该能够容忍少量失败的提交，或者如果它们对基准测试集不重要，则允许跳过它们。
    *   **原因**：`src/eleanstic/config.yaml` 中的 `mathlib_repo_path` 不正确。
    *   **解决方案**：验证该路径指向 `leanprover-community/mathlib4` 的有效、最新的克隆。

*   **问题**：尽管进行了重复数据删除，Eleanstic CAS 存储仍然过度增长。
    *   **原因**：如果许多二进制文件（例如，编译的 `.olean` 文件）在不同提交之间存在微小的、非语义的差异，从而破坏了简单的内容哈希。
    *   **解决方案**：这是一个固有的挑战。Eleanstic 的设计旨在缓解此问题。确保 Eleanstic 正确识别和哈希文件。对于极端情况，可以研究更高级的二进制差异/补丁存储方法，但这将是 Eleanstic 本身的重大研发工作。

## LLM 推理问题

*   **问题**：来自 LLM 的 API 错误（例如，身份验证、速率限制、模型未找到）。
    *   **解决方案**：
        *   **身份验证**：仔细检查 API 密钥是否已正确设置为环境变量或在 `src/apebench/config/` 模型配置文件中。
        *   **速率限制**：在 `src/apebench/inference/` 的 API 调用模块中实现或增强重试逻辑（例如，指数退避，如 `requirements.txt` 中的 `tenacity` 库所提供）。考虑减少批处理大小或一次运行较少任务的推理。
        *   **模型未找到**：确保配置中的模型名称与 LLM 提供商 API 使用的确切标识符匹配。

*   **问题**：LLM 输出未采用预期的差异格式。
    *   **解决方案**：审查并优化 `src/apebench/inference/` 中使用的提示策略。确保提示明确指示 LLM 输出统一差异格式。`DiffRepair` 可以处理一些噪音，但如果输出完全没有结构，则提示是主要的解决方法。

*   **问题**：`DiffRepair` 无法修复补丁或显著改变其含义。
    *   **原因**：LLM 生成的差异与 `PreFile` 上下文过于偏离，或者 `DiffRepair` 的模糊匹配阈值过于严格/宽松。
    *   **解决方案**：
        *   检查有问题的原始差异和 `PreFile`。
        *   试验 `DiffRepair` 参数（例如，在推理流程中初始化 `DiffRepair` 时的 `strict_match_threshold`、`exact_match` 标志）。
        *   对于系统性问题，这可能表明需要改进 `DiffRepair` 的算法（请参阅[LLM 推理与 DiffRepair - 二次开发](./04_core_components/04_3_apebench_inference.md)）。

## 评估问题

*   **问题**：对于看起来正确的补丁，语法验证（Lean 编译）失败。
    *   **原因**：Eleanstic 可能没有恢复*完全*正确的版本化环境（例如，错误的快照，从 CAS 恢复文件时出现问题）。
    *   **解决方案**：验证 Eleanstic 设置。检查 Eleanstic 和 Lean 编译器的日志以获取特定错误。确保任务的提交 SHA 正确映射到 Eleanstic 快照。
    *   **原因**：即使修复后，补丁仍引入了乍一看并不明显的细微 Lean 错误。
    *   **解决方案**：将补丁手动应用于 `PreFile`（来自正确的 Mathlib 提交，本地检出），并尝试使用 `lake env lean <file.lean>`进行编译以直接调试 Lean 错误。

*   **问题**：语义判断（作为裁判的 LLM）给出意外结果。
    *   **原因**：裁判 LLM 的提示问题；裁判 LLM 响应的不稳定性。
    *   **解决方案**：审查语义评估提示。确保 `sample@4` 投票按预期工作。APE-Bench I 论文使用 Claude Sonnet 3.7（思考模式）；使用不同的裁判模型可能需要重新校准期望或提示。

## 一般问题

*   **问题**：Python `ModuleNotFoundError` 或 `ImportError`。
    *   **解决方案**：确保您的虚拟环境已激活 (`source venv/bin/activate`)。验证 `requirements.txt` 中的所有依赖项均已正确安装 (`pip install -r requirements.txt`)。如果使用复杂的项目结构，请检查 `PYTHONPATH`，尽管如果项目结构为正确的 Python 包，则通常不需要这样做。

*   **问题**：性能缓慢。
    *   **原因**：LLM API 调用可能很慢。Eleanstic 预处理计算量大，但每个提交仅执行一次。慢速驱动器上 Eleanstic CAS 的磁盘 I/O。
    *   **解决方案**：
        *   如果可用，请使用更快的 LLM 模型（尽管这会改变实验）。
        *   确保 Eleanstic CAS 和快照目录位于快速存储设备上（建议使用 SSD）。
        *   对于推理，如果您的 API 配额和本地资源允许，请考虑跨多个任务并行化 API 调用（`src/apebench/scripts/` 中的脚本可能已经这样做了）。

如果您遇到此处未列出的问题，请检查项目的现有 GitHub 问题（如果可用），或考虑报告一个新问题并提供详细信息：重现步骤、错误消息、相关配置和环境详细信息。