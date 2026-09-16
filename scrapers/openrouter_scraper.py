#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenRouter 数据爬虫 - 抓取模型使用量排名和趋势
增强版：使用公开 API 获取模型数据和价格信息
"""
import re
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper


class OpenRouterScraper(BaseScraper):
    """OpenRouter Rankings 数据爬虫（增强版）"""

    def __init__(self):
        super().__init__()
        self.base_url = "https://openrouter.ai"
        self.api_base = "https://openrouter.ai/api/v1"

    def fetch_rankings(self):
        """抓取完整的 OpenRouter 数据（增强版）"""
        print("  抓取 OpenRouter 数据...")

        # 先尝试加载缓存；旧代码快照缺 token 用量时视为过期（AA 同款逻辑），
        # 否则当日产物永远沿用旧快照、Token 块永久隐藏（2026-09-16 线上实证）。
        cached = self.load_cache("openrouter")
        if cached:
            if not (cached.get("token_usage")
                    and cached.get("total_weekly_tokens")):
                print("     [WARN] 当日缓存缺 token 用量（旧代码快照），忽略并重新直抓")
            else:
                return cached

        try:
            # 1. 从 API 获取模型列表和价格
            models_data = self._fetch_models_api()

            # 2. 尝试从网页获取排名数据（如果可用）
            rankings_data = self._fetch_rankings_page()

            # 3. 整合数据
            result = self._merge_data(models_data, rankings_data)

            # 保存缓存
            self.save_cache("openrouter", result)
            return result

        except Exception as e:
            print(f"     [WARN] OpenRouter 抓取失败：{e}")
            # 尝试加载昨天的缓存
            return self._load_fallback_cache()

    def _fetch_models_api(self):
        """从 API 获取模型列表和价格数据"""
        try:
            url = f"{self.api_base}/models"
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))

            models = data.get("data", [])
            print(f"     [OK] 获取到 {len(models)} 个模型数据")

            # 提取价格和基本信息
            pricing = []
            for model in models[:50]:  # 只取前50个
                pricing_info = model.get("pricing", {})
                prompt_price = float(pricing_info.get("prompt", 0))
                completion_price = float(pricing_info.get("completion", 0))

                # 计算平均价格（每百万 token）
                avg_price = (prompt_price + completion_price) / 2 * 1_000_000

                pricing.append({
                    "model": model.get("name", "Unknown"),
                    "id": model.get("id", ""),
                    "price_per_1m_tokens": round(avg_price, 4),
                    "context_length": model.get("context_length", 0),
                    "created": model.get("created", 0)
                })

            return {
                "total_models": len(models),
                "pricing": pricing
            }

        except Exception as e:
            print(f"     [WARN] API 获取失败：{e}")
            return {"total_models": 0, "pricing": []}

    def _fetch_rankings_page(self):
        """抓取 Rankings 页面数据（保留原有逻辑）"""
        try:
            # 抓取页面
            url = f"{self.base_url}/rankings"
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html = response.read().decode('utf-8')

            soup = BeautifulSoup(html, 'html.parser')

            # 尝试从页面提取描述信息
            description = "Live LLM rankings by real-world usage"
            meta_desc = soup.find('meta', {'name': 'description'})
            if meta_desc:
                description = meta_desc.get('content', description)

            return {
                "description": description,
                "detected_models": self._extract_model_names(soup),
                # 直抓：近一周各模型 token 数 + 环比（网关口径，不依赖新闻 LLM 抽取）
                "token_usage": self._parse_token_usage(html)
            }

        except Exception as e:
            print(f"     [WARN] Rankings 页面抓取失败：{e}")
            return {
                "description": "Live LLM rankings by real-world usage",
                "detected_models": [],
                "token_usage": []
            }

    def _extract_model_names(self, soup):
        """从 HTML 中提取模型名称（降级方案）"""
        detected = []
        text = soup.get_text()

        # 常见模型名称关键词
        keywords = [
            "GPT-4", "GPT-3.5", "Claude", "Sonnet", "Opus", "Haiku",
            "Gemini", "Flash", "Pro", "Llama", "Mistral", "Qwen"
        ]

        for keyword in keywords:
            if keyword in text and keyword not in detected:
                detected.append(keyword)

        return detected[:10]  # 最多10个

    @staticmethod
    def _tokens_to_number(value, unit):
        """17.4T / 800M / 12K -> 绝对 token 数，用于加总和份额计算。"""
        try:
            return float(value) * {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}.get(unit, 1)
        except (TypeError, ValueError):
            return 0

    def _parse_token_usage(self, html):
        """解析 Rankings 表格：模型名 + 近一周 token 数 + 环比变化。

        口径：流经 OpenRouter 网关的调用量，非全网真实总量。
        页面是服务端直出的 <table>（无 __NEXT_DATA__），按 <tr> 切分提取。
        """
        usage = []
        try:
            for chunk in html.split("<tr")[1:]:
                seg = chunk[:6000]
                m = re.search(
                    r'href="/[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.\-]+"[^>]*>([^<]{2,60})</a>',
                    seg)
                t = re.search(r"<div>([\d.]+)([TBMK]) tokens</div>", seg)
                if not (m and t):
                    continue
                d = re.search(r"text-(positive|negative)-text", seg)
                p = re.search(r"([+-]?[\d.]+%)", seg)
                usage.append({
                    "model": m.group(1).strip(),
                    "weekly_tokens_display": t.group(1) + t.group(2),
                    "weekly_tokens": self._tokens_to_number(t.group(1), t.group(2)),
                    "wow_direction": (d.group(1) if d else "flat"),
                    "wow_change": (p.group(1) if p else "N/A"),
                })
        except Exception as e:
            print(f"     [WARN] Token 用量解析失败：{e}")
        return usage

    def _merge_data(self, models_data, rankings_data):
        """整合 API 数据和页面数据"""
        # 直抓的周 token 用量：加总 + Top-N 内份额（网关口径，非全网总量）
        token_usage = rankings_data.get("token_usage", []) or []
        total_weekly = sum(u.get("weekly_tokens", 0) for u in token_usage)
        for u in token_usage:
            u["market_share"] = round(u["weekly_tokens"] / total_weekly * 100, 1) if total_weekly else 0

        result = {
            "source": "openrouter",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_models": models_data.get("total_models", 0),
            "description": rankings_data.get("description", ""),
            "detected_models": rankings_data.get("detected_models", []),
            "pricing": models_data.get("pricing", []),
            "token_usage": token_usage,
            "total_weekly_tokens": total_weekly,
            "token_usage_note": "OpenRouter 网关口径：流经该网关的近一周 token 加总，非全网真实总量",

            # 保留向后兼容字段
            "top_models": rankings_data.get("detected_models", [])[:10],
            "rankings": self._build_rankings(models_data.get("pricing", []))
        }

        return result

    def _build_rankings(self, pricing_data):
        """从价格数据构建排名列表"""
        rankings = []

        for item in pricing_data[:20]:  # Top 20
            rankings.append({
                "model": item.get("model", "Unknown"),
                "id": item.get("id", ""),
                "price_per_1m_tokens": item.get("price_per_1m_tokens", 0),
                "context_length": item.get("context_length", 0),
                "tokens_weekly": "N/A",  # API 不提供使用量数据
                "market_share": 0,
                "trend": "N/A"
            })

        return rankings
        print("  抓取 OpenRouter Rankings 数据...")

        # 先尝试加载缓存
        cached = self.load_cache("openrouter")
        if cached:
            return cached

        try:
            # 抓取页面
            url = f"{self.base_url}/rankings"
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html = response.read().decode('utf-8')

            soup = BeautifulSoup(html, 'html.parser')

            # 查找 Next.js 内联的数据
            # Next.js 通常会在 <script id="__NEXT_DATA__"> 中存储页面数据
            next_data_script = soup.find('script', id='__NEXT_DATA__')

            result = {
                "source": "openrouter",
                "date": None,
                "top_models": [],
                "raw_html_available": bool(next_data_script)
            }

            if next_data_script:
                try:
                    data = json.loads(next_data_script.string)
                    # 解析 Next.js 数据结构
                    result = self._parse_next_data(data)
                except Exception as e:
                    print(f"     [WARN] 解析 Next.js 数据失败：{e}")

            # 如果 Next.js 数据解析失败，尝试从 HTML 中提取文本信息
            if not result.get("top_models"):
                result = self._parse_html_fallback(soup)

            # 保存缓存
            self.save_cache("openrouter", result)
            return result

        except Exception as e:
            print(f"     [WARN] OpenRouter 抓取失败：{e}")
            # 尝试加载昨天的缓存
            return self._load_fallback_cache()

    def _parse_next_data(self, data):
        """解析 Next.js 页面数据"""
        result = {
            "source": "openrouter",
            "date": None,
            "top_models": [],
            "usage_data_through": None
        }

        try:
            # Next.js 数据通常在 props.pageProps 中
            page_props = data.get('props', {}).get('pageProps', {})

            # 提取日期
            if 'date' in page_props:
                result['date'] = page_props['date']

            # 提取模型排名数据
            if 'rankings' in page_props:
                rankings = page_props['rankings']
                for rank_data in rankings[:10]:  # 只取前10
                    result['top_models'].append({
                        'name': rank_data.get('name', ''),
                        'rank': rank_data.get('rank'),
                        'tokens': rank_data.get('tokens'),
                        'market_share': rank_data.get('marketShare')
                    })

        except Exception as e:
            print(f"     [WARN] 解析 Next.js 结构失败：{e}")

        return result

    def _parse_html_fallback(self, soup):
        """从 HTML 中提取文本信息作为降级方案"""
        result = {
            "source": "openrouter",
            "date": None,
            "top_models": [],
            "description": ""
        }

        try:
            # 查找页面描述
            desc_elem = soup.find(string=re.compile(r"Live LLM rankings"))
            if desc_elem:
                result['description'] = desc_elem.strip()

            # 查找日期信息
            date_elem = soup.find(string=re.compile(r"Usage data through"))
            if date_elem:
                match = re.search(r"through\s+([A-Za-z]+\s+\d+,\s+\d{4})", date_elem)
                if match:
                    result['usage_data_through'] = match.group(1)

            # 尝试提取模型名称（从页面文本中）
            # 这是最基本的降级方案，可能不太准确
            model_names = []
            common_models = [
                "Claude", "GPT-4", "Gemini", "Llama", "Mistral",
                "Opus", "Sonnet", "Haiku", "Flash", "Pro"
            ]

            page_text = soup.get_text()
            for model in common_models:
                if model in page_text:
                    model_names.append(model)

            if model_names:
                result['detected_models'] = list(set(model_names))

        except Exception as e:
            print(f"     [WARN] HTML 降级解析失败：{e}")

        return result

    def _load_fallback_cache(self):
        """加载前一天的缓存作为降级"""
        import glob
        cache_files = sorted(glob.glob(str(self.cache_dir / "openrouter_*.json")), reverse=True)

        for cache_file in cache_files[:3]:  # 尝试最近3天
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"     [INFO] 使用历史缓存：{Path(cache_file).name}")
                data['is_fallback'] = True
                return data
            except:
                continue

        return {"source": "openrouter", "error": "无法获取数据", "top_models": []}


def fetch_openrouter_data():
    """对外接口：获取 OpenRouter 数据"""
    scraper = OpenRouterScraper()
    return scraper.fetch_rankings()


if __name__ == "__main__":
    # 测试
    data = fetch_openrouter_data()
    print(json.dumps(data, indent=2, ensure_ascii=False))
