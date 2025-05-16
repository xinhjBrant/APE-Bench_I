# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import openai
import logging
import time
import uuid
from typing import Dict, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random, wait_combine, retry_if_exception_type
from ..utils.chat_logger import ChatLogger
from ..utils.api_keys import *

# List of supported model categories
TOTAL_MODELS = (
    'o1', 'o3-mini', 'deepseek-r1-250120', 'aws_sdk_claude37_sonnet@thinking', 
    'gpt-4o-2024-08-06', 'gpt-4o-2024-11-20', 'aws_claude35_sdk_sonnet_v2', 
    'aws_sdk_claude37_sonnet', 'deepseek-v3-250324', 
    'deepseek-v3', 
    'doubao-1-5-pro-32k-250115',
    'gpt-4.5-preview-2025-02-27'
)

FORMAL_NAMES = {
    'o1': 'OpenAI o1',
    'o3-mini': 'OpenAI o3-mini',
    'deepseek-r1-250120': 'DeepSeek R1',
    'aws_sdk_claude37_sonnet@thinking': 'Claude 3.7 Sonnet (thinking)',
    'gpt-4o-2024-08-06': 'GPT-4o',
    'gpt-4o-2024-11-20': 'GPT-4o',
    'aws_claude35_sdk_sonnet_v2': 'Claude 3.5 Sonnet',
    'aws_sdk_claude37_sonnet': 'Claude 3.7 Sonnet',
    'deepseek-v3-250324': 'DeepSeek V3 (0324)',
    'deepseek-v3': 'DeepSeek V3',
    'doubao-1-5-pro-32k-250115': 'Doubao 1.5 Pro',
    'gpt-4.5-preview-2025-02-27': 'GPT-4.5',
}

REASONING_MODELS = (
    'o1', 'o3-mini', 'deepseek-r1-250120', 'aws_sdk_claude37_sonnet@thinking'
)

UNSUPPORT_TEMPERATURE_MODELS = (
    'o3-mini', 'aws_sdk_claude37_sonnet@thinking'
)

forbidden_params = {
    'o3-mini': ['temperature'],
    'aws_sdk_claude37_sonnet@thinking': ['temperature'],
}

def generate_logid() -> str:
    """
    Generate a unique log ID
    
    Returns:
        str: UUID format unique ID
    """
    return str(uuid.uuid4())


def create_client(model_name: str):
    """Create an appropriate client"""
    if 'deepseek' in model_name or 'doubao' in model_name:
        return openai.OpenAI(
            api_key=volces_api_key, 
            base_url=volces_base_url,
        )
    elif 'claude' in model_name:
        return openai.AzureOpenAI(
            azure_endpoint=aws_claude_base_url,
            api_version="2024-03-01-preview",
            api_key=aws_claude_api_key,
        )
    else:
        return openai.AzureOpenAI(
            azure_endpoint=openai_base_url,
            api_version="2024-03-01-preview",
            api_key=openai_api_key,
        )


def prepare_inference_params(
    client: openai.OpenAI,
    model_name: str,
    messages: list,
    logid: str,
    temperature: float = 0.0,
    max_tokens: int = 8000,
    thinking_budget_tokens: int = 16000,
    reasoning_effort: str = 'high'
) -> Dict[str, Any]:
    """Prepare parameters for completion request"""
    params = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "extra_headers": {"X-TT-LOGID": logid},
    }
    
    # Add thinking mode for Claude models
    if '@thinking' in model_name:
        params["model"] = model_name.replace('@thinking', '')
        params["temperature"] = 1.0
        params["extra_body"] = {
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens
            }
        }
        params["max_tokens"] += thinking_budget_tokens

    # Add reasoning effort for o1 models
    # if model_name == 'o3-mini':
    #     params["reasoning_effort"] = reasoning_effort

    if model_name in forbidden_params:
        for param in forbidden_params[model_name]:
            params.pop(param, None)
    return params


@retry(
    stop=stop_after_attempt(5),  # Retry up to 5 times
    wait=wait_combine(
        wait_exponential(multiplier=1, min=1, max=60),  # Base exponential backoff: 1s, 2s, 4s, 8s, 16s
        wait_random(0, 2)  # Add random jitter between 0-2 seconds
    ),
    retry=retry_if_exception_type((Exception,)),  # Retry all exceptions
    reraise=True  # Re-raise the exception at the end
)
def execute_completion(client: openai.OpenAI, params: Dict[str, Any]):
    """Execute request with retry logic and jitter"""
    try:
        return client.chat.completions.create(**params)
    except Exception as e:
        logging.error(f"API call failed: {str(e)}")
        raise


def chat(
    prompt: str, 
    system_prompt: Optional[str] = None, 
    model_name: str = 'gpt-4o-2024-08-06', 
    print_result: bool = False, 
    temperature: float = 0.0,
    n: int = 1, 
    max_tokens: int = 8000,
    thinking_budget_tokens: int = 6000,
    logid: Optional[str] = None,
    log_chat: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate conversational responses using specified model
    
    Parameters:
        prompt: User prompt text
        system_prompt: System prompt text (optional)
        model_name: Model name
        print_result: Whether to print results
        temperature: Sampling temperature
        n: Must be 1, otherwise throws an error
        max_tokens: Maximum tokens to generate
        logid: Custom log ID, automatically generated if None
        
    Returns:
        Dict: Model response result
    """
    # Validate n parameter
    if n != 1:
        raise ValueError("This implementation only supports n=1, multiple sampling has been removed to simplify code")
    
    # Generate or use provided logid
    if logid is None:
        logid = generate_logid()
    
    # Initialize chat logger and timing
    chat_logger = ChatLogger()
    start_time = time.time()
    
    # Create message list
    messages = [{"role": "user", "content": prompt}]
    if system_prompt:
        if model_name.startswith('o'):
            messages = [{"role": "user", "content": system_prompt + "\n\n\n\n" + prompt}]
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})
    
    # Create appropriate client
    client = create_client(model_name)
    
    # Prepare API call parameters
    params = prepare_inference_params(client, model_name, messages, logid, temperature, max_tokens, thinking_budget_tokens)
    
    # Execute API call (with automatic retry)
    try:
        completion = execute_completion(client, params)
        result = completion.model_dump()
        result['inference_params'] = params
        
        # Calculate response time
        response_time = time.time() - start_time
        
    except Exception as e:
        logging.error(f"Request failed [logid: {logid}]: {str(e)}")
        raise
    
    # Print results (if needed)
    if print_result:
        print(f"LogID: {logid}")
        print(completion.model_dump_json())
        print('\n\n--------------------------------\n\n')
        print(completion.choices[0].message.content)
        print('\n--------------------------------\n')
        print(f"Time taken: {response_time:.2f} seconds")
    
    # Log chat interaction
    if log_chat:
        chat_logger.log_chat(
            prompt=prompt,
            completion=result,
            model_name=model_name,
            system_prompt=system_prompt
        )
    
    return result


if __name__ == "__main__":
    system_prompt = None
    prompt = "What is the capital of France?"
    # model_name = "deepseek-r1-250120"
    # model_name = "gemini-2.5-pro-preview-03-25"
    model_name = "o3-mini"

    # Using automatically generated logid
    result = chat(
        prompt=prompt, 
        system_prompt=system_prompt, 
        model_name=model_name, 
        print_result=True, 
        n=1
    )
    
    # Or using custom logid
    # custom_logid = f"api_call_{int(time.time())}"
    # result = chat(
    #     prompt=prompt, 
    #     system_prompt=system_prompt, 
    #     model_name=model_name, 
    #     print_result=True, 
    #     n=1,
    #     logid=custom_logid
    # )