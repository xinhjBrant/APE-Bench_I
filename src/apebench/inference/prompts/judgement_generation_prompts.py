# Copyright (2025) Bytedance Ltd. and/or its affiliates.

judgement_generation_system_prompt = '''## Task
Analyze the provided Lean4 code patch comprehensively to determine whether it correctly, completely, and clearly implements the specified tasks. The patch has already been verified by Lean's type checker, thus types and tactics are assumed correct. Your goal is to provide a thorough yet contextually flexible evaluation, assessing how well the patch aligns with task requirements and integrates into the existing codebase.

Use the following steps and criteria **as references** to guide your analysis. **Do not mechanically adhere to these steps; instead, adapt their use according to the specific context and significance of each element in the provided code.** Aim for a comprehensive, flexible, and nuanced evaluation rather than a rigid checklist.

---

### Step 1: Task Understanding (Reference)
- Summarize core and implied requirements clearly.
- Identify any explicit or implicit constraints.
- Clarify expected outcomes and note any ambiguities.

---

### Step 2: Original Code Analysis (Reference)
- Provide a concise summary of the original code structure and purpose.
- Highlight key definitions, lemmas, theorems, proofs, assumptions, or dependencies relevant to the patch.
- Evaluate logical flow and proof structure as contextually appropriate.

---

### Step 3: Patch Examination (Reference)
- Clearly describe the elements added, modified, or removed.
- Evaluate the logical clarity, correctness, and efficacy of modifications.
- Consider appropriate use of Lean4-specific features (e.g., inductive types, macros, notations).

---

### Step 4: Requirement Fulfillment Analysis (Reference)
For each provided task, evaluate (as contextually relevant):
- Accuracy and completeness of achieving core objectives.
- Logical thoroughness and consideration of edge cases.
- Mathematical and type-theoretic correctness.
- Consistency with existing design patterns and coding standards.

---

### Step 5: Implementation Quality Analysis (Reference)
Evaluate implementation quality with respect to:
- Mathematical abstraction, modularity, and hierarchical structure.
- Clarity, naming conventions, and documentation effectiveness.
- Logical decomposition, proof readability, and maintainability.
- Software engineering principles (single responsibility, interface rationality).
- Appropriate use of Lean-specific techniques (metaprogramming, universes, computational vs. proof separation).
- Future-proofing, extensibility, and integration within mathlib standards.

---

### Step 6: Overall Judgement (Required)
Based on your comprehensive analysis, provide structured final grades **without additional justification**, strictly using the JSON format below for clear information extraction:

```json
{
  "TaskEvaluations": {
    "Task 1": "Excellent | Good | Acceptable | Poor | Unacceptable",
    "Task 2": "Excellent | Good | Acceptable | Poor | Unacceptable"
    // Add additional tasks as necessary
  },
  "FinalOverallGrade": "Excellent | Good | Acceptable | Poor | Unacceptable"
}
```

---

**Reminder:** Prioritize flexible, context-sensitive analysis. Reference provided steps and criteria only as guidelines, adapting your evaluation according to actual significance and context of the provided Lean4 code patch.
'''

judgement_generation_input_prompt = '''# Lean4 Code Evaluation Request

## Original Source Code: {filename}

```lean
{lean_code}
```

## Task Requirements

{instruction}

## Proposed Implementation

```diff
{raw_patch}
```

Please evaluate whether this implementation properly fulfills the task requirements.
'''

judgement_generation_input_prompt_without_lean_code = '''# Lean4 Code Evaluation Request

## Original Source Code Status

This is a new file creation with no pre-existing code.

## Task Requirements

{instruction}

## Proposed Implementation

```diff
{raw_patch}
```

Please evaluate whether this implementation properly fulfills the task requirements.
'''