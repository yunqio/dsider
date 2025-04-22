import json
import time
import asyncio
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
import requests
from datetime import datetime
import logging
import os
import re
import base64
import io
from PIL import Image
from dotenv import load_dotenv
from PIL import ImageFilter

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("openai-proxy")

# 创建FastAPI应用
app = FastAPI(
    title="OpenAI API Proxy",
    description="将OpenAI API请求代理到DeepSider API",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置
DEEPSIDER_API_BASE = "https://api.chargpt.ai/api/v2"
TOKEN_INDEX = 0

# 模型映射表
MODEL_MAPPING = {
    "gpt-4o": "openai/gpt-4o",
    "gpt-4.1": "openai/gpt-4.1",
    "gpt-4o-image": "openai/gpt-4o-image",
    "claude-3.5-sonnet": "anthropic/claude-3.5-sonnet",
    "claude-3.7-sonnet": "anthropic/claude-3.7-sonnet",
    "o1": "openai/o1",
    "o3-mini": "openai/o3-mini",
    "gemini-2.0-flash": "google/gemini-2.0-flash",
    "grok-3": "x-ai/grok-3",
    "grok-3-reasoner": "x-ai/grok-3-reasoner",
    "deepseek-chat": "deepseek/deepseek-chat",
    "deepseek-r1": "deepseek/deepseek-r1",
    "qwq-32b": "qwen/qwq-32b",
    "qwen-max": "qwen/qwen-max"
}

# 请求头
def get_headers(api_key):
    global TOKEN_INDEX
    # 检查是否包含多个token（用逗号分隔）
    tokens = api_key.split(',')
    
    if len(tokens) > 0:
        # 轮询选择token
        current_token = tokens[TOKEN_INDEX % len(tokens)]
        TOKEN_INDEX = (TOKEN_INDEX + 1) % len(tokens)
    else:
        current_token = api_key
    
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "content-type": "application/json",
        "origin": "chrome-extension://client",
        "i-lang": "zh-CN",
        "i-version": "1.1.64",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "Windows",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "authorization": f"Bearer {current_token.strip()}"
    }

# OpenAI API请求模型
class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None
    reasoning_content: Optional[str] = None  # 添加思维链内容字段

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[List[str], str]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0
    frequency_penalty: Optional[float] = 0
    user: Optional[str] = None
    
# 账户余额查询函数
async def check_account_balance(api_key, token_index=None):
    """检查账户余额信息"""
    tokens = api_key.split(',')
    
    # 如果提供了token_index并且有效，则使用指定的token
    if token_index is not None and len(tokens) > token_index:
        current_token = tokens[token_index].strip()
    else:
        # 否则使用第一个token
        current_token = tokens[0].strip() if tokens else api_key
        
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "authorization": f"Bearer {current_token}"
    }
    
    try:
        # 获取账户余额信息
        response = requests.get(
            f"{DEEPSIDER_API_BASE.replace('/v2', '')}/quota/retrieve",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 0:
                quota_list = data.get('data', {}).get('list', [])
                
                # 解析余额信息
                quota_info = {}
                for item in quota_list:
                    item_type = item.get('type', '')
                    available = item.get('available', 0)
                    
                    quota_info[item_type] = {
                        "total": item.get('total', 0),
                        "available": available,
                        "title": item.get('title', '')
                    }
                
                return True, quota_info
        
        return False, {}
            
    except Exception as e:
        logger.warning(f"检查账户余额出错：{str(e)}")
        return False, {}

# 工具函数
def verify_api_key(api_key: str = Header(..., alias="Authorization")):
    """验证API密钥"""
    if not api_key.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API key format")
    
    # 直接使用用户提供的令牌作为DeepSider Token
    provided_key = api_key.replace("Bearer ", "").strip()
    
    # 检查令牌是否为空
    if not provided_key:
        raise HTTPException(status_code=401, detail="API key cannot be empty")
    
    # 直接返回用户提供的令牌
    return provided_key

def map_openai_to_deepsider_model(model: str) -> str:
    """将OpenAI模型名称映射到DeepSider模型名称"""
    return MODEL_MAPPING.get(model, "anthropic/claude-3.7-sonnet")

def format_messages_for_deepsider(messages: List[ChatMessage]) -> str:
    """格式化消息列表为DeepSider API所需的提示格式"""
    prompt = ""
    for msg in messages:
        role = msg.role
        # 将OpenAI的角色映射到DeepSider能理解的格式
        if role == "system":
            # 系统消息放在开头 作为指导
            prompt = f"{msg.content}\n\n" + prompt
        elif role == "user":
            prompt += f"Human: {msg.content}\n\n"
        elif role == "assistant":
            prompt += f"Assistant: {msg.content}\n\n"
        else:
            # 其他角色按用户处理
            prompt += f"Human ({role}): {msg.content}\n\n"
    
    # 如果最后一个消息不是用户的 添加一个Human前缀引导模型回答
    if messages and messages[-1].role != "user":
        prompt += "Human: "
    
    return prompt.strip()

async def generate_openai_response(full_response: str, request_id: str, model: str, reasoning_content: str = None) -> Dict:
    """生成符合OpenAI API响应格式的完整响应"""
    timestamp = int(time.time())
    response_data = {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": timestamp,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_response
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }
    
    # 如果有思维链内容，添加到响应中
    if reasoning_content:
        response_data["choices"][0]["message"]["reasoning_content"] = reasoning_content
        
    return response_data

# 验证码处理函数
def extract_captcha_image(content: str) -> Optional[str]:
    """从内容中提取Base64编码的验证码图片"""
    # 匹配 markdown 格式的图片 ![](data:image/png;base64,...)
    pattern = r'!\[\]\(data:image\/[^;]+;base64,([^)]+)\)'
    match = re.search(pattern, content)
    if match:
        return match.group(1)
    return None

# 修改流式响应处理
async def stream_openai_response(response, request_id: str, model: str, api_key, token_index, deepsider_model: str, is_post_captcha: bool = False):
    """流式返回OpenAI API格式的响应"""
    timestamp = int(time.time())
    full_response = ""
    full_reasoning = ""  # 添加思维链内容累积变量
    conversation_id = None  # 会话ID
    captcha_base64 = None  # 验证码图片
    captcha_detected = False  # 验证码检测标志
    captcha_content = ""  # 验证码响应内容
    
    try:
        # 使用iter_content替代iter_lines
        buffer = bytearray()
        for chunk in response.iter_content(chunk_size=None):
            if chunk:
                buffer.extend(chunk)
                try:
                    text = buffer.decode('utf-8')
                    lines = text.split('\n')
                    
                    for line in lines[:-1]:
                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])
                                logger.debug(f"Received data: {data}")
                                
                                # 获取会话ID (所有流都可能包含)
                                if data.get('code') == 201:
                                    conversation_id = data.get('data', {}).get('clId')
                                    logger.info(f"会话ID: {conversation_id}")
                                
                                if data.get('code') == 202 and data.get('data', {}).get('type') == "chat":
                                    content = data.get('data', {}).get('content', '')
                                    reasoning_content = data.get('data', {}).get('reasoning_content', '')
                                    
                                    # 检测是否含有验证码
                                    if "验证码提示" in content and "![](data:image" in content and "系统检测到您当前存在异常" in content:
                                        captcha_detected = True
                                        captcha_content = content
                                        logger.info("检测到验证码响应")
                                        captcha_base64 = extract_captcha_image(content)
                                    
                                    # 累积非验证码响应内容
                                    if not captcha_detected:
                                        full_response += content
                                    
                                    # 处理思维链内容
                                    if reasoning_content:
                                        full_reasoning += reasoning_content
                                        
                                # 当整个响应结束时处理验证码
                                elif data.get('code') == 203:
                                    # 如果检测到验证码，进行验证码处理
                                    if captcha_detected and captcha_base64 and conversation_id:
                                        # 向客户端发送验证码响应
                                        original_captcha_message = {
                                            "id": f"chatcmpl-{request_id}",
                                            "object": "chat.completion.chunk",
                                            "created": timestamp,
                                            "model": model,
                                            "choices": [
                                                {
                                                    "index": 0,
                                                    "delta": {
                                                        "content": captcha_content
                                                    },
                                                    "finish_reason": None
                                                }
                                            ]
                                        }
                                        yield f"data: {json.dumps(original_captcha_message)}\n\n"
                                        
                                        # 显示验证码提示信息
                                        captcha_message = {
                                            "id": f"chatcmpl-{request_id}",
                                            "object": "chat.completion.chunk",
                                            "created": timestamp,
                                            "model": model,
                                            "choices": [
                                                {
                                                    "index": 0,
                                                    "delta": {
                                                        "content": "\n[系统检测到验证码，请手动查看并处理验证码]"
                                                    },
                                                    "finish_reason": "stop"
                                                }
                                            ]
                                        }
                                        yield f"data: {json.dumps(captcha_message)}\n\n"
                                        yield "data: [DONE]\n\n"
                                        return
                                    
                                    # 非验证码响应，直接流式输出到目前为止收集的内容
                                    if not captcha_detected:
                                        # 流式输出响应内容
                                        if full_response:
                                            content_chunk = {
                                                "id": f"chatcmpl-{request_id}",
                                                "object": "chat.completion.chunk",
                                                "created": timestamp,
                                                "model": model,
                                                "choices": [
                                                    {
                                                        "index": 0,
                                                        "delta": {
                                                            "content": full_response
                                                        },
                                                        "finish_reason": None
                                                    }
                                                ]
                                            }
                                            yield f"data: {json.dumps(content_chunk)}\n\n"
                                        
                                        # 流式输出思维链内容（如果有）
                                        if full_reasoning:
                                            reasoning_chunk = {
                                                "id": f"chatcmpl-{request_id}",
                                                "object": "chat.completion.chunk",
                                                "created": timestamp,
                                                "model": model,
                                                "choices": [
                                                    {
                                                        "index": 0,
                                                        "delta": {
                                                            "reasoning_content": full_reasoning
                                                        },
                                                        "finish_reason": None
                                                    }
                                                ]
                                            }
                                            yield f"data: {json.dumps(reasoning_chunk)}\n\n"
                                        
                                        # 发送完成信号
                                        final_chunk = {
                                            "id": f"chatcmpl-{request_id}",
                                            "object": "chat.completion.chunk",
                                            "created": timestamp,
                                            "model": model,
                                            "choices": [
                                                {
                                                    "index": 0,
                                                    "delta": {},
                                                    "finish_reason": "stop"
                                                }
                                            ]
                                        }
                                        yield f"data: {json.dumps(final_chunk)}\n\n"
                                        yield "data: [DONE]\n\n"
                                    
                            except json.JSONDecodeError as e:
                                logger.warning(f"JSON解析失败: {line}, 错误: {str(e)}")
                                continue
                                
                    buffer = bytearray(lines[-1].encode('utf-8'))
                    
                except UnicodeDecodeError:
                    continue

    except Exception as e:
        logger.error(f"流式响应处理出错: {str(e)}")
        
        # 返回错误信息
        error_msg = "\n\n[处理响应时出错: {str(e)}]"
        error_chunk = {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion.chunk",
            "created": timestamp,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": error_msg
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

# 路由定义
@app.get("/")
async def root():
    return {
        "message": "OpenAI API Proxy服务已启动 连接至DeepSider API",
        "instructions": "在Authorization头部直接使用Bearer YOUR_DEEPSIDER_TOKEN进行认证",
        "multiple_tokens": "支持多token轮询，请在Authorization头中使用英文逗号分隔多个token",
        "supported_models": list(MODEL_MAPPING.keys())
    }

@app.get("/v1/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """列出可用的模型"""
    models = []
    for openai_model, _ in MODEL_MAPPING.items():
        models.append({
            "id": openai_model,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "openai-proxy"
        })
    
    return {
        "object": "list",
        "data": models
    }

@app.post("/v1/chat/completions")
async def create_chat_completion(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """创建聊天完成API - 支持普通请求和流式请求"""
    # 解析请求体
    body = await request.json()
    chat_request = ChatCompletionRequest(**body)
    
    # 生成唯一请求ID
    request_id = datetime.now().strftime("%Y%m%d%H%M%S") + str(time.time_ns())[-6:]
    
    # 映射模型
    deepsider_model = map_openai_to_deepsider_model(chat_request.model)
    
    # 准备DeepSider API所需的提示
    prompt = format_messages_for_deepsider(chat_request.messages)
    
    # 准备请求体
    payload = {
        "model": deepsider_model,
        "prompt": prompt,
        "webAccess": "close",
        "timezone": "Asia/Shanghai"
    }
    
    # 添加其他可选参数
    if chat_request.temperature is not None:
        payload["temperature"] = chat_request.temperature
    if chat_request.top_p is not None:
        payload["top_p"] = chat_request.top_p
    if chat_request.max_tokens is not None:
        payload["max_tokens"] = chat_request.max_tokens
    
    # 获取请求头
    headers = get_headers(api_key)
    
    try:
        response = requests.post(
            f"{DEEPSIDER_API_BASE}/chat/conversation",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30
        )
        
        # 新增调试日志
        logger.info(f"请求头: {headers}")
        logger.info(f"请求体: {payload}")
        logger.info(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            # 新增详细错误日志
            logger.error(f"DeepSider API错误响应头: {response.headers}")
            logger.error(f"错误响应体: {response.text}")
            
            error_msg = f"DeepSider API请求失败: {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data.get('message', '')}"
            except:
                error_msg += f" - {response.text}"
                
            logger.error(error_msg)
            raise HTTPException(status_code=response.status_code, detail=error_msg)
        
        # 处理流式或非流式响应
        if chat_request.stream:
            # 返回流式响应 - 初始调用 is_post_captcha 默认为 False
            return StreamingResponse(
                stream_openai_response(response, request_id, chat_request.model, api_key, TOKEN_INDEX, deepsider_model),
                media_type="text/event-stream"
            )
        else:
            # 收集完整响应
            full_response = ""
            full_reasoning = ""  # 思维链内容累积变量
            
            for line in response.iter_lines():
                if not line:
                    continue
                    
                if line.startswith(b'data: '):
                    try:
                        data = json.loads(line[6:].decode('utf-8'))
                        
                        if data.get('code') == 202 and data.get('data', {}).get('type') == "chat":
                            content = data.get('data', {}).get('content', '')
                            reasoning_content = data.get('data', {}).get('reasoning_content', '')
                            
                            if content:
                                full_response += content
                            
                            # 收集思维链内容
                            if reasoning_content:
                                full_reasoning += reasoning_content
                                
                    except json.JSONDecodeError:
                        pass
            
            # 返回OpenAI格式的完整响应
            return await generate_openai_response(full_response, request_id, chat_request.model, full_reasoning)
            
    except requests.Timeout as e:
        logger.error(f"请求超时: {str(e)}")
        raise HTTPException(status_code=504, detail="上游服务响应超时")
        
    except requests.RequestException as e:
        logger.error(f"网络请求异常: {str(e)}")
        raise HTTPException(status_code=502, detail="网关错误")

@app.get("/admin/balance")
async def get_account_balance(api_key: str = Depends(verify_api_key)):
    """查看账户余额"""
    tokens = api_key.split(',')
    
    total_quota = {
        "total": 0,
        "available": 0
    }
    
    # 获取所有token的余额信息并计算总和
    for i, token in enumerate(tokens):
        success, quota_info = await check_account_balance(api_key, i)
        if success:
            for quota_type, info in quota_info.items():
                total_quota["total"] += info.get("total", 0)
                total_quota["available"] += info.get("available", 0)
    
    return total_quota

# 错误处理器
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": {
            "message": f"未找到资源: {request.url.path}",
            "type": "not_found_error",
            "code": "not_found"
        }
    }, 404

# 启动事件
@app.on_event("startup")
async def startup_event():
    """服务启动时初始化"""
    logger.info(f"OpenAI API代理服务已启动，可以接受请求")
    logger.info(f"用户可以直接在Authorization头中提供DeepSider Token")
    logger.info(f"支持多token轮询，请在Authorization头中使用英文逗号分隔多个token")

# 主程序
if __name__ == "__main__":
    # 启动服务器
    port = int(os.getenv("PORT", "7860"))
    logger.info(f"启动OpenAI API代理服务 端口: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)