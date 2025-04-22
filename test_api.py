#!/usr/bin/env python3
"""
DeepSider API Proxy测试脚本

使用方法:
python test_api.py --token YOUR_DEEPSIDER_TOKEN --model claude-3.7-sonnet
"""

import requests
import argparse
import json
import sys

# 设置命令行参数
parser = argparse.ArgumentParser(description='测试DeepSider API代理')
parser.add_argument('--token', type=str, required=True, help='DeepSider Token')
parser.add_argument('--model', type=str, default='claude-3.7-sonnet', help='模型名称')
parser.add_argument('--host', type=str, default='http://localhost:7860', help='API代理地址')
parser.add_argument('--stream', action='store_true', help='是否使用流式响应')
args = parser.parse_args()

# 构建API请求
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {args.token}"
}

data = {
    "model": args.model,
    "messages": [{"role": "user", "content": "你好，请自我介绍一下"}],
    "stream": args.stream
}

# 发送请求
print(f"正在测试与 {args.host} 的连接...")
print(f"使用模型: {args.model}")
print(f"使用流式响应: {args.stream}")

try:
    # 先测试连接
    root_response = requests.get(f"{args.host}/")
    if root_response.status_code == 200:
        print("API连接成功!")
        print(f"支持的模型: {json.dumps(root_response.json().get('supported_models', []), ensure_ascii=False, indent=2)}")
    else:
        print(f"API连接失败: {root_response.status_code} - {root_response.text}")
        sys.exit(1)
        
    # 发送聊天请求
    print("\n正在发送聊天请求...")
    response = requests.post(
        f"{args.host}/v1/chat/completions",
        headers=headers,
        json=data,
        stream=args.stream
    )
    
    # 处理响应
    if response.status_code == 200:
        print("请求成功!")
        
        if args.stream:
            # 流式响应处理
            print("\n收到的回复:")
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: ') and not line.startswith('data: [DONE]'):
                        try:
                            data = json.loads(line[6:])
                            if 'choices' in data and len(data['choices']) > 0:
                                if 'delta' in data['choices'][0] and 'content' in data['choices'][0]['delta']:
                                    content = data['choices'][0]['delta']['content']
                                    print(content, end='', flush=True)
                        except json.JSONDecodeError:
                            pass
            print("\n")
        else:
            # 非流式响应处理
            try:
                response_data = response.json()
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    message = response_data['choices'][0]['message']
                    print("\n收到的回复:")
                    print(message.get('content', ''))
                    
                    # 检查是否有思维链内容
                    if 'reasoning_content' in message and message['reasoning_content']:
                        print("\n思维链内容:")
                        print(message['reasoning_content'])
            except json.JSONDecodeError:
                print(f"解析响应失败: {response.text}")
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")

except Exception as e:
    print(f"测试过程中出现错误: {str(e)}")

# 测试查询账户余额
try:
    print("\n正在查询账户余额...")
    balance_response = requests.get(
        f"{args.host}/admin/balance",
        headers=headers
    )
    
    if balance_response.status_code == 200:
        balance_data = balance_response.json()
        print(f"账户余额: 总额 {balance_data.get('total', 0)}, 可用 {balance_data.get('available', 0)}")
    else:
        print(f"查询余额失败: {balance_response.status_code} - {balance_response.text}")
        
except Exception as e:
    print(f"查询余额时出现错误: {str(e)}") 