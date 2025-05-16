# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Prompt Templates Used in the Inference Process
"""

from .instruction_generation_prompts import (
    instruction_generation_system_prompt,
    instruction_generation_input_prompt,
    instruction_generation_input_prompt_without_lean_code
)

from .patch_generation_prompts import (
    patch_generation_system_prompt,
    patch_generation_reasoning_models_system_prompt,
    patch_generation_input_prompt,
    patch_generation_input_prompt_without_lean_code
)

from .judgement_generation_prompts import (
    judgement_generation_system_prompt,
    judgement_generation_input_prompt,
    judgement_generation_input_prompt_without_lean_code
)

__all__ = [
    'instruction_generation_system_prompt',
    'instruction_generation_input_prompt',
    'instruction_generation_input_prompt_without_lean_code',
    'patch_generation_system_prompt',
    'patch_generation_reasoning_models_system_prompt',
    'patch_generation_input_prompt',
    'patch_generation_input_prompt_without_lean_code',
    'judgement_generation_system_prompt',
    'judgement_generation_input_prompt',
    'judgement_generation_input_prompt_without_lean_code'
]
