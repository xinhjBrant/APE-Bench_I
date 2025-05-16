# Copyright (2025) Bytedance Ltd. and/or its affiliates.

from ..inference_pipelines.base import BasePipeline
import re
import logging
import json
from collections import Counter

class GenerateJudgementPipeline(BasePipeline):
    """
    Pipeline for generating judgements on the quality of generated patches.
    
    Assesses completeness, accuracy, scope, and coding style of implementations.
    """
    def __init__(self, args):
        super().__init__(args)
        from ..prompts import (
            judgement_generation_system_prompt, 
            judgement_generation_input_prompt, 
            judgement_generation_input_prompt_without_lean_code
        )
        self.system_prompt = judgement_generation_system_prompt
        self.input_prompt = judgement_generation_input_prompt
        self.input_prompt_without_lean_code = judgement_generation_input_prompt_without_lean_code
        self.criteria_list = ['unacceptable', 'poor', 'acceptable', 'good', 'excellent']
    
    def get_input(self, row):
        if not 'exercises' in row:
            assert len(row['responses']) == 1, f"Expected 1 response, got {len(row['responses'])}"
            row['exercises'] = row['responses'][0]['exercises']
        if not 'full_instruction' in row:
            exercises = row['exercises']
            instructions = [f"- Task {idx + 1}: {exercise['title']}\n\n{exercise['instruction']}" for idx, exercise in enumerate(exercises)]
            full_instruction = '\n\n\n'.join(instructions)
            row['full_instruction'] = full_instruction
        else:
            full_instruction = row['full_instruction']
            
        # Format input for verification
        if not row['content_before']:
            formatted_input = self.input_prompt_without_lean_code.format(
                instruction=full_instruction, 
                raw_patch=row[self.args.patch_key].strip()
            )
        else:
            formatted_input = self.input_prompt.format(
                instruction=full_instruction, 
                raw_patch=row[self.args.patch_key].strip(),
                lean_code=row['content_before'].strip(),
                filename=row['file_path_after']
            )
        return formatted_input
    
    def initialize_metadata(self, row):
        """Initialize metadata for a row using Counter"""
        return {
            'worst_judgement': None,
            'majority_judgement': None,
            'judgement_counter': Counter(),  # Use Counter instead of list
        }
    
    def update_metadata_per_response(self, metadata, parsed_response):
        """Update metadata with response using Counter"""
        if parsed_response is not None and 'TaskEvaluations' in parsed_response:
            key = 'judgement'
            worst_key = f'worst_{key}'
            majority_key = f'majority_{key}'
            counter_key = f'{key}_counter'
            for task_evaluation in parsed_response['TaskEvaluations'].values():
                value = task_evaluation.lower()
                if value in self.criteria_list:
                    if metadata[worst_key] is None or self.criteria_list.index(value) < self.criteria_list.index(metadata[worst_key]):
                        metadata[worst_key] = value
                    metadata[counter_key].update([value])
                    if metadata[counter_key]:
                        metadata[majority_key] = metadata[counter_key].most_common(1)[0][0]
        return metadata
    
    def update_metadata_per_row(self, metadata, responses):
        """Update metadata with responses"""
        counter_key = 'judgement_counter'
        majority_key = 'majority_judgement'
        if metadata[counter_key]:
            metadata[majority_key] = metadata[counter_key].most_common(1)[0][0]
        
        metadata.pop(counter_key)
        return metadata
    
    def parse_response(self, response, row):
        """Parse verification response into structured dictionary"""
        try:
            json_blocks = re.findall(r'```json(.*?)```', response, re.DOTALL)
            if len(json_blocks) == 0:
                json_blocks = re.findall(r'{.*"TaskEvaluations".*}', response, re.DOTALL)
                if len(json_blocks) == 0:
                    raise ValueError(f"Expected 1 JSON block, got {len(json_blocks)}")
                json_block = json_blocks[-1]
            else:
                json_block = json_blocks[-1]
            parsed_response = json.loads(json_block)
            return parsed_response
        except Exception as e:
            logging.error(f"Error parsing GPT response: {e}")
            return None
    
    