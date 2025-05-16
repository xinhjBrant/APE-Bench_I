# Copyright (2025) Bytedance Ltd. and/or its affiliates.

patch_generation_system_prompt = """You are given a set of **Task Descriptions**, each specifying modifications to an existing Lean 4 codebase (which may be optional or only partially provided). Your goal is to generate a **unified diff patch** that implements **only** the specified changes in **Lean 4 syntax**, ensuring strict adherence to Lean 4 conventions.

Follow these steps:

### **Step 1: Identify Key Proving Strategies**
- For each Task Description, **analyze and summarize** the key strategies involved, such as:
  - Lemma rewriting
  - Data structure modification
  - Function renaming
  - Introducing new theorems or lemmas
  - Other conceptual or syntactical transformations
- Highlight any specialized proof techniques or high-level ideas guiding your modifications.

### **Step 2: Declaration Inventory**
- List all **relevant declarations** (definitions, lemmas, theorems, data types) to be **added, removed, or modified**.
- For new Lean 4 declarations:
  - Provide **concise, academic-style statements** or descriptions.
  - Explain how they integrate into the overall codebase.

### **Step 3: Determine Modification Locations**
- Identify **where each modification should be applied** within the given Lean 4 codebase.
- Quote relevant **original Lean code** where applicable, indicating:
  - **Insertion points** for new definitions, lemmas, or theorems.
  - **Lines to be modified**, specifying which parts require updates.
  - **Removals**, justifying why specific lines or declarations should be deleted.

### **Step 4: Unified Diff Patch (Lean 4)**
- Present the **final patch** in **unified diff format** with **at least three lines of context before and after** each modified hunk.
- Ensure the patch contains **only** the specified changes—no extraneous edits.
- **Strictly enforce Lean 4 syntax**:
  - Check that all modifications are **Lean 4-compliant** and follow best practices.
  - Avoid deprecated Lean 3 syntax or tactics.
  - Ensure consistency with **Lean 4's module system and proof style**.
- All code must be valid **Lean 4 syntax**, with **no** placeholders (`sorry`, `admit`).
- Do **not** interleave commentary within the diff—explanations belong in Steps 1–3.

### **Response Format**

#### **Step 1: Key Strategies**
[Summarize the main strategies for each Task Description.]

#### **Step 2: Declaration Inventory**
[List modified, removed, or added declarations, providing concise descriptions for new ones.]

#### **Step 3: Modification Locations**
[Identify and quote the relevant Lean code where changes should be made. Specify insertion points, modifications, and removals.]

#### **Step 4: Unified Diff Patch (Lean 4)**
- **Overall Explanation of the Changes:**
  - [Provide a structured natural-language overview of the modifications.]
- **Lean 4 Compliance Reminder:**
  - Clearly highlight how the diff strictly adheres to **Lean 4 syntax**, avoiding **Lean 3 syntax or tactics**.
  - Emphasize key changes in **Lean 4 module system, proof tactics, and syntax adaptations**.
- **Final Patch in Unified Diff Format:**
```diff
[Present the final patch in unified diff format, with at least three lines of context before and after each diff hunk. Ensure strict Lean 4 compliance.]
```

"""

patch_generation_reasoning_models_system_prompt = """You are given a set of **Task Descriptions**, each specifying modifications to an existing Lean 4 codebase (which may be optional or only partially provided). Your task is to generate a **unified diff patch** that implements **only** the specified changes in **Lean 4 syntax**, ensuring strict adherence to Lean 4 conventions.

Please provide the final patch in the following format:

```diff
[Present the final patch in unified diff format, with at least three lines of context before and after each diff hunk. Ensure strict Lean 4 compliance.]
```
"""

patch_generation_input_prompt = """# Lean4 Code Modification Task

## Task Requirements

{instructions}

## Source Codebase: {filename}

```lean
{lean_code}
```

Please generate a unified diff patch that implements all specified requirements while ensuring strict adherence to Lean4 syntax and conventions.
"""

patch_generation_input_prompt_without_lean_code = """# Lean4 Code Creation Task

## Task Requirements

{instructions}

## Source Codebase Status

This task requires creating a new file for {filename}. No existing code is provided.

Please generate a unified diff patch that creates this file with all specified requirements while ensuring strict adherence to Lean4 syntax and conventions.
"""