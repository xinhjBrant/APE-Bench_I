# Copyright (2025) Bytedance Ltd. and/or its affiliates.

instruction_generation_system_prompt = '''# Task Overview

Your goal is to transform given Lean code modifications (diffs) for a given Lean file into structured, precise, and self-contained Lean exercises suitable for practicing mathematical reasoning and proof engineering. Each generated exercise should be concise yet comprehensive enough for practitioners to reconstruct the exact changes based solely on the provided exercise.

You will complete the following three steps explicitly and systematically. Each step must clearly connect logically to the next, ensuring an integrated, coherent result.

---

Step 1: Diff Analysis

Instructions:
- Carefully examine each diff hunk in detail.
- For **each modified Lean declaration** (`def`, `lemma`, `theorem`, `class`, `instance`, etc.):
  - Clearly state the diff hunk span (e.g., `@@ -12,7 +12,7 @@`).
  - Precisely describe what was **added, removed, or changed** within the declaration.
  - Clearly outline the mathematical meaning or implication of each modification.
- Identify and summarize the overall mathematical context of the entire diff.

---

Step 2: Dependency and Hierarchy Analysis

Instructions:
- Analyze the relationships among declarations identified in Step 1.
- Explicitly classify declarations into:
  - **Core Contributions:** Declarations directly motivated by essential mathematical goals.
  - **Auxiliary Declarations:** Supporting or intermediate lemmas serving core contributions.
- Clearly outline dependencies and hierarchical relationships among these declarations.
- Explicitly state the core mathematical motivations and objectives driving the identified core contributions.

---

Step 3: Exercise Generation

Instructions:
- Based explicitly on the Core Contributions identified in Step 2, generate one structured, self-contained Lean exercise for each core declaration.
- Each exercise must:
  - Clearly reflect the overall mathematical context (from Step 1) and the core mathematical motivation (from Step 2).
  - Be formulated entirely in standard mathematical language in textbooks or academic literature, explicitly avoiding Lean-specific syntax or implementation details.
  - Allow practitioners to precisely reconstruct the intended modifications solely from your concise instructions.
  - Use imperative language for instructions ("Prove that…", "Define…", etc.).

Response Format for Step 3:
```
# Exercises in Lean

## Exercise 1: [Concise and Descriptive Title Reflecting Mathematical Content]
- **Diff Hunk Span:** `@@ -X,Y +X,Y @@`
- **Task Category:** [Feature | Bug Fix | Refactor | Chore | Testing | Documentation | Formatting]
- **Focus:** [Mathematical Concepts | Software Engineering]
- **Difficulty:** [Very Easy | Easy | Medium | Hard | Very Hard]
- **Task Nature:** [Substantial | Superficial]
- **Problem Statement (Natural Mathematical Language):** 
  Clearly state the mathematical statement to be proved or defined. Use concise, self-contained, textbook-style language understandable to mathematicians without referencing Lean-specific syntax. If the task involves modifying an existing statement (e.g., correcting an error or clarifying logic), precisely describe the intended conceptual adjustments in purely mathematical terms. Include LaTeX-formatted mathematical expressions as needed. Ensure that instructions are imperative (e.g., "Prove that...", "Define...") and explicitly indicate the logical or conceptual emphasis required by the modification.

*(Repeat explicitly for each core contribution.)*
```

---

Ensure your responses strictly follow the provided formats and clearly adhere to each instruction, thus creating structured, integrated, and high-quality proof engineering exercises.

'''

instruction_generation_input_prompt = '''# Lean Code Modification Analysis Request

## Original File: {filename}

```lean
{lean_code}
```

## Proposed Changes (Patch):

```diff
{raw_patch}
```

Please analyze these modifications according to the instructions provided.
'''

instruction_generation_input_prompt_without_lean_code = '''# Lean Code Modification Analysis Request

## Original File Status
This represents a new file creation - no pre-existing code.

## Proposed File Content (Patch):

```diff
{raw_patch}
```

Please analyze this new file according to the instructions provided.
'''