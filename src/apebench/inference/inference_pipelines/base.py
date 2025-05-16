# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import pandas as pd
import json
import os
import logging
import time
import traceback
from datetime import datetime
from abc import ABC, abstractmethod

from ..utils import process_with_retries
from ..utils import chat
from ....utils.file_utils import load_jsonl, convert_to_serializable
import random

class BasePipeline(ABC):
    """
    Base class for data processing pipelines that interact with AI models.
    
    This abstract class provides common functionality for:
    - Loading and processing input data
    - Handling results and errors
    - Logging and output management
    """
    
    def __init__(self, args):
        """Initialize with command-line arguments"""
        self.args = args
        # Set default timestamp if not provided
        if not hasattr(self.args, 'timestamp') or self.args.timestamp is None:
            self.args.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.setup_logging()
        self.print_script_configuration()

        self.system_prompt = None
    
    def setup_logging(self):
        """Configure logging based on arguments"""
        os.makedirs(self.args.log_dir, exist_ok=True)
        log_file = f'{self.args.log_dir}/{self.args.pipeline}/{self.args.timestamp}_{self.args.model_name}_{self.args.temperature}.log'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename=log_file
        )
        

    def print_script_configuration(self):
        print("\nScript Configuration:")
        print("---------------------")
        for arg, value in vars(self.args).items():
            print(f"{arg}: {value}")
        print("---------------------\n")
    
    def load_data(self):
        """
        Load data from input file with support for multiple formats
        
        Returns:
            pd.DataFrame: Loaded data
        """
        if self.args.input_file.endswith('.parquet'):
            data = pd.read_parquet(self.args.input_file)
        elif self.args.input_file.endswith('.json'):
            data = pd.read_json(self.args.input_file, orient='records', lines=True)
        elif self.args.input_file.endswith('.jsonl'):
            data = load_jsonl(self.args.input_file)
            data = pd.DataFrame(data)
        else:
            raise ValueError(f"Unsupported file type: {self.args.input_file}")
        
        return data
    
    @abstractmethod
    def get_input(self, row):
        """Get input text for a row"""
        pass

    def initialize_metadata(self, row):
        """Initialize metadata for a row"""
        return {}

    def update_metadata_per_response(self, metadata, parsed_response):
        """Update metadata with response"""
        return metadata

    def update_metadata_per_row(self, metadata, responses):
        """Update metadata with responses"""
        return metadata

    def early_stop(self, metadata, responses):
        """Early stop if the metadata is good or bad enough"""
        return False
    
    def parse_response(self, response, row):
        """Parse the response from the GPT model"""
        return {}
    
    def process_row(self, row):
        """
        Process a single row of data.
        
        Args:
            row (pd.Series): The row to process
            
        Returns:
            Dict or None: Processing result or None if processing failed
        """
        try:
            row_dict = row.to_dict()
            row_dict = convert_to_serializable(row_dict)
            row_dict['local_index'] = row.name
            input_text = self.get_input(row_dict)

            responses = []
            metadata = self.initialize_metadata(row_dict)
            for _ in range(self.args.n_responses):
                response = None
                try:
                    response = chat(
                        prompt=input_text, 
                        system_prompt=self.system_prompt, 
                        model_name=self.args.model_name,
                        temperature=self.args.temperature,
                        max_tokens=self.args.max_tokens,
                        thinking_budget_tokens=self.args.thinking_budget_tokens
                    )
                    parsed_response = self.parse_response(response['choices'][0]['message']['content'], row_dict)
                    if parsed_response is not None:
                        response['inference_params'].update({
                            'temperature': self.args.temperature,
                            'n_responses': self.args.n_responses
                        })
                        parsed_response.update({
                            'raw_response': response['choices'][0], 
                            'model': self.args.model_name,
                            'usage': response['usage'],
                            'inference_params': response['inference_params']
                        })
                    metadata = self.update_metadata_per_response(metadata, parsed_response)
                    responses.append(parsed_response)
                    if self.early_stop(metadata, responses):
                        break
                except Exception as e:
                    logging.error(f"Error processing row {row.name}: {traceback.format_exc()}")
                    responses.append(response)
                    time.sleep(random.randint(1, 5))
                    continue
            metadata = self.update_metadata_per_row(metadata, responses)
            return {
                **row_dict,
                **metadata,
                'responses': responses
            }
        except Exception as e:
            logging.error(f"Error processing row {row.name}: {traceback.format_exc()}")
            time.sleep(random.randint(1, 5))
            return None
        
    @property
    def special_config(self):
        return ''
    
    def process_data(self):
        """
        Process all data with automatic retries for failures
        
        Returns:
            Tuple[int, int, List]: (processed_count, error_count, failed_indices)
        """
        # Load data
        data = self.load_data()
        
        # Generate output file path if not provided
        if not hasattr(self.args, 'output_file') or self.args.output_file is None:
            _input_file_name = os.path.splitext(os.path.basename(self.args.input_file))[0]
            self.args.output_file = '/'.join([
                self.args.output_dir, 
                self.args.pipeline, 
                f'{self.args.timestamp}__{_input_file_name}__{self.args.model_name}__{self.args.temperature}{self.special_config}.jsonl'
                ])
        os.makedirs(os.path.dirname(self.args.output_file), exist_ok=True)

        print(f"Results will be saved to {self.args.output_file}")
        
        # Prepare configuration information dictionary
        config_info = {
            'model_name': self.args.model_name,
            'temperature': self.args.temperature,
            'n_responses': self.args.n_responses
        }
        
        # Process with automatic retries
        total_processed, total_errors, final_missing = process_with_retries(
            data=data,
            process_func=self.process_row,
            output_file=self.args.output_file,
            max_workers=self.args.max_workers,
            max_retries=self.args.max_retries,
            config_info=config_info
        )
        
        # Save permanently failed indices if any
        if final_missing:
            os.makedirs('temp', exist_ok=True)
            missing_file = f'temp/missing_{self.args.pipeline}_{self.args.model_name}_{self.args.timestamp}.json'
            with open(missing_file, 'w') as f:
                json.dump({'missing_indices': final_missing}, f)
            logging.info(f"Saved {len(final_missing)} permanently failed indices to {missing_file}")
        
        logging.info(f"Final processing statistics - Successfully processed: {total_processed}, Total errors: {total_errors}")
        
        return total_processed, total_errors, final_missing