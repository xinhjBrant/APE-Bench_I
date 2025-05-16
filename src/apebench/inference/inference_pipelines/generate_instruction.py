# Copyright (2025) Bytedance Ltd. and/or its affiliates.

from ...inference.inference_pipelines.base import BasePipeline
import re
import logging
from collections import Counter

class GenerateInstructionPipeline(BasePipeline):
    """
    Pipeline for generating instructions from patches.
    
    This processor extracts structured information about code contributions and exercises.
    """

    def __init__(self, args):
        super().__init__(args)
        from ..prompts import (
            instruction_generation_system_prompt, 
            instruction_generation_input_prompt, 
            instruction_generation_input_prompt_without_lean_code
        )
        self.system_prompt = instruction_generation_system_prompt
        self.input_prompt = instruction_generation_input_prompt
        self.input_prompt_without_lean_code = instruction_generation_input_prompt_without_lean_code
        self.task_nature_list = ['superficial', 'substantial']
        self.difficulty_list = ['very easy', 'easy', 'medium', 'hard', 'very hard']
        self.task_category_list = ['bug fix', 'refactor', 'feature']
    
    def get_input(self, row):
        if not row['content_before']:
            formatted_input = self.input_prompt_without_lean_code.format(
                raw_patch=row[self.args.gold_diff_key].strip()
            )
        else:
            formatted_input = self.input_prompt.format(
                raw_patch=row[self.args.gold_diff_key].strip(),
                lean_code=row['content_before'].strip(),
                filename=row['file_path_before']
            )
        return formatted_input
    
    def initialize_metadata(self, row):
        """Initialize metadata for a row using Counter"""
        return {
            'worst_difficulty': None,
            'worst_task_nature': None,
            'majority_difficulty': None,
            'majority_task_nature': None,
            'majority_task_category': None,
            'difficulty_counter': Counter(),
            'task_nature_counter': Counter(),
            'task_category_counter': Counter(),
        }
    
    def update_metadata_per_response(self, metadata, parsed_response):
        """Update metadata with response using Counter"""
        if parsed_response is not None:
            for exercise in parsed_response['exercises']:
                for key, criteria in zip(
                    ('difficulty', 'task_nature', 'task_category'), 
                    (self.difficulty_list, self.task_nature_list, self.task_category_list), 
                ):
                    worst_key = f'worst_{key}'
                    majority_key = f'majority_{key}'
                    counter_key = f'{key}_counter'
                    value = exercise[key].lower()
                    if value in criteria:
                        if worst_key in metadata and (metadata[worst_key] is None or criteria.index(value) < criteria.index(metadata[worst_key])):
                            metadata[worst_key] = value
                        metadata[counter_key].update([value])
                        if metadata[counter_key]:
                            metadata[majority_key] = metadata[counter_key].most_common(1)[0][0]
        return metadata
    
    def update_metadata_per_row(self, metadata, responses):
        """Update metadata with responses"""
        for key in ('difficulty', 'task_nature'):
            counter_key = f'{key}_counter'
            majority_key = f'majority_{key}'
            if metadata[counter_key]:
                metadata[majority_key] = metadata[counter_key].most_common(1)[0][0]
        
        metadata.pop('difficulty_counter')
        metadata.pop('task_nature_counter')
        return metadata
    
    def _extract_exercises(self, exercise_text):
        # Extract Exercises
        split_pos = exercise_text.find('Exercises in Lean')
        assert split_pos != -1
        exercise_text = exercise_text[split_pos:].strip(' \n-')
        exercises = []
        exercise_pattern = r'Exercise[\*\s:]*(\d+)[\*\s]*:[\*\s:]*(.*?)[-\*\s]*Diff Hunk Span.*?@@(.*?)@@.*?[-\*\s]*Task Category[-\*\s:]*(.*?)[-\*\s]*Focus[-\*\s:]*(.*?)[-\*\s]*Difficulty[-\*\s:]*(.*?)[-\*\s]*Task Nature[-\*\s:]*(.*?)[-\*\s]*Problem Statement.*?[-\*:]+(.*?)(?=[-\*#\s]*Exercise|$)'
        exercise_blocks = re.findall(exercise_pattern, exercise_text, re.DOTALL)
        for num, title, hunk_span, category, focus, difficulty, nature, instruction in exercise_blocks:
            exercises.append({
                'num': int(num),
                'title': title.strip().strip(),
                'hunk_span': hunk_span.strip(),
                'focus': focus.strip(),
                'difficulty': difficulty.strip(),
                'task_category': category.strip(),
                'task_nature': nature.strip(),
                'instruction': instruction.strip()
            })
        return exercises
    
    def parse_response(self, response, row):
        """Parse structured data from GPT response"""
        try:
            if '(Continue similarly' in response:
                return None

            exercises = self._extract_exercises(response)
            
            assert len(exercises) > 0
            return {"exercises": exercises}
        except Exception as e:
            logging.error(f"Error parsing GPT response: {e}")
            return None