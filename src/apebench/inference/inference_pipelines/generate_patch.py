from ..inference_pipelines.base import BasePipeline
from ..utils.diff_repair import DiffRepair, apply_diff, generate_diff
from ..utils.call_api import REASONING_MODELS
import re
import logging

class GeneratePatchPipeline(BasePipeline):
    """
    Pipeline for generating patches based on task descriptions.
    
    Supports multiple prompt types and model configurations.
    """
    def __init__(self, args):
        super().__init__(args)
        from ..prompts import (
            patch_generation_system_prompt, 
            patch_generation_reasoning_models_system_prompt, 
            patch_generation_input_prompt, 
            patch_generation_input_prompt_without_lean_code
        )
        self.system_prompt = patch_generation_system_prompt if self.args.model_name not in REASONING_MODELS else patch_generation_reasoning_models_system_prompt
        assert not self.args.force_reasoning_prompt or not self.args.force_complete_prompt, "force_reasoning_prompt and force_complete_prompt cannot be both True"
        if self.args.force_reasoning_prompt:
            self.system_prompt = patch_generation_reasoning_models_system_prompt
        if self.args.force_complete_prompt:
            self.system_prompt = patch_generation_system_prompt
        self.input_prompt = patch_generation_input_prompt
        self.input_prompt_without_lean_code = patch_generation_input_prompt_without_lean_code
        self.strict_match_threshold = 0.5
        self.max_context_lines = 3

    @property
    def special_config(self):
        if self.args.force_complete_prompt:
            return '_force_complete_prompt'
        elif self.args.force_reasoning_prompt:
            return '_force_reasoning_prompt'
        else:
            return ''
        
    def parse_response(self, response, row):
        try:
            result = {
                'gen_patch': None,
                'gen_content_from_scratch': None,
                'gen_patch_after_exact_repair': None,
                'gen_content_after_exact_repair': None,
                'gen_patch_after_robust_repair': None,
                'gen_content_after_robust_repair': None
                }
            patch_match = re.search(r'```diff(.*?)```', response, re.DOTALL)
            best_gen_patch = None
            best_gen_content = None
            if patch_match:
                patch = patch_match.group(1).strip()
                result['gen_patch'] = patch
                if not row['content_before']:
                    try:
                        result['gen_content_from_scratch'] = apply_diff(row['content_before'], patch)
                        best_gen_content = result['gen_content_from_scratch']
                    except Exception as e:
                        pass
                else:
                    try:
                        repairer = DiffRepair(row['content_before'], patch, strict_match_threshold=self.strict_match_threshold, max_context_lines=self.max_context_lines, exact_match=True)
                        repaired_patch = repairer.repair()
                        
                        # Apply the repaired patch to get the content
                        repaired_content = apply_diff(row['content_before'], repaired_patch)
                        result['gen_content_after_exact_repair'] = repaired_content
                        
                        # Generate actual diff between original and repaired content
                        actual_diff = generate_diff(row['content_before'], repaired_content)
                        result['gen_patch_after_exact_repair'] = actual_diff
                        
                        best_gen_patch = actual_diff
                        best_gen_content = repaired_content
                    except Exception as e:
                        pass
                    try:
                        repairer = DiffRepair(row['content_before'], patch, strict_match_threshold=self.strict_match_threshold, max_context_lines=self.max_context_lines, exact_match=False)
                        repaired_patch = repairer.repair()
                        
                        # Apply the repaired patch to get the content
                        repaired_content = apply_diff(row['content_before'], repaired_patch)
                        result['gen_content_after_robust_repair'] = repaired_content
                        
                        # Generate actual diff between original and repaired content
                        actual_diff = generate_diff(row['content_before'], repaired_content)
                        result['gen_patch_after_robust_repair'] = actual_diff
                        
                        best_gen_patch = actual_diff
                        best_gen_content = repaired_content
                    except Exception as e:
                        pass
            result['best_gen_content'] = best_gen_content
            result['best_gen_patch'] = best_gen_patch
            return result
        except Exception as e:
            logging.error(f"Error parsing GPT response: {e}")
            return None

    def get_input(self, row):
        """Generate prompt input for a row"""
        
        lean_code = row['content_before']
        filename = row['file_path_after']
        if not 'full_instruction' in row:
            instructions = '\n\n\n'.join([f"- Task {idx + 1}: {exercise['title']}\n\n{exercise['instruction']}" for idx, exercise in enumerate(row['instructions']['exercises'])])
            row['full_instruction'] = instructions
        else:
            instructions = row['full_instruction']
        
        if filename and lean_code:
            return self.input_prompt.format(
                lean_code=lean_code, 
                instructions=instructions, 
                filename=filename
                )
        else:
            return self.input_prompt_without_lean_code.format(
                instructions=instructions,
                filename=filename
                )
