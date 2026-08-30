#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI API 客户端封装
"""
import os
import json


class OpenAIClient:
    """OpenAI API 客户端"""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        # 延迟导入，避免在没有安装 openai 时就报错
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
            self.model = "gpt-4o-mini"  # 使用性价比高的模型
        except ImportError:
            raise ImportError("请安装 openai 库：pip install openai")

    def extract_structured_data(self, prompt, system_prompt=None):
        """
        提取结构化数据（JSON）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）

        Returns:
            dict: 解析后的 JSON 数据
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,  # 低温度，更确定性
                response_format={"type": "json_object"}  # 强制 JSON 输出
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            print(f"     [ERROR] OpenAI API 调用失败：{e}")
            return {}

    def summarize(self, text, max_length=200):
        """
        文本摘要

        Args:
            text: 输入文本
            max_length: 最大长度

        Returns:
            str: 摘要文本
        """
        try:
            prompt = f"请用不超过 {max_length} 字总结以下内容：\n\n{text}"

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=max_length * 2
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"     [ERROR] 摘要生成失败：{e}")
            return ""


# 测试函数
def test_client():
    """测试 OpenAI 客户端"""
    try:
        client = OpenAIClient()

        # 测试结构化数据提取
        system_prompt = "你是一个数据提取助手。返回 JSON 格式：{\"test\": \"value\"}"
        user_prompt = "请返回一个测试 JSON"

        result = client.extract_structured_data(user_prompt, system_prompt)
        print("结构化数据提取测试：")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 测试摘要
        text = "这是一段很长的文本，需要被总结成更短的内容。"
        summary = client.summarize(text, max_length=20)
        print(f"\n摘要测试：\n{summary}")

        print("\n[OK] OpenAI 客户端测试通过")

    except Exception as e:
        print(f"[ERROR] 测试失败：{e}")


if __name__ == "__main__":
    test_client()
