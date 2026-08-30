#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号推送模块 - 自动发布图文消息到微信公众号
"""
import json
import time
import hashlib
import os
import urllib.request
import urllib.parse


class WechatOfficialPublisher:
    """微信公众号发布器"""

    def __init__(self, appid, appsecret):
        """
        初始化发布器

        Args:
            appid: 微信公众号 AppID
            appsecret: 微信公众号 AppSecret
        """
        self.appid = appid
        self.appsecret = appsecret
        self.access_token = None
        self.token_expires_at = 0
        self.base_url = "https://api.weixin.qq.com/cgi-bin"

    def get_access_token(self):
        """
        获取 access_token

        Returns:
            str: access_token

        Raises:
            Exception: 获取失败
        """
        # 检查缓存的 token 是否还有效（提前5分钟刷新）
        if self.access_token and time.time() < self.token_expires_at - 300:
            return self.access_token

        url = f"{self.base_url}/token?grant_type=client_credential&appid={self.appid}&secret={self.appsecret}"

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            if 'access_token' in data:
                self.access_token = data['access_token']
                expires_in = data.get('expires_in', 7200)
                self.token_expires_at = time.time() + expires_in
                print(f"     获取 access_token 成功，有效期 {expires_in} 秒")
                return self.access_token
            else:
                error_msg = data.get('errmsg', '未知错误')
                raise Exception(f"获取 access_token 失败: {error_msg}")

        except Exception as e:
            raise Exception(f"获取 access_token 异常: {e}")

    def upload_news_image(self, image_path):
        """
        上传图文消息封面图片

        Args:
            image_path: 图片文件路径

        Returns:
            str: 上传后的 media_id

        Raises:
            Exception: 上传失败
        """
        access_token = self.get_access_token()
        url = f"{self.base_url}/media/upload?access_token={access_token}&type=image"

        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()

            # 构建 multipart/form-data
            boundary = '----WebKitFormBoundary' + hashlib.md5(str(time.time()).encode()).hexdigest()
            body = []
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="media"; filename="{os.path.basename(image_path)}"'.encode())
            body.append(b'Content-Type: image/jpeg')
            body.append(b'')
            body.append(image_data)
            body.append(f'--{boundary}--'.encode())
            body.append(b'')

            data = b'\r\n'.join(body)

            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            if 'media_id' in result:
                print(f"     图片上传成功: {result['media_id']}")
                return result['media_id']
            else:
                error_msg = result.get('errmsg', '未知错误')
                raise Exception(f"图片上传失败: {error_msg}")

        except Exception as e:
            raise Exception(f"图片上传异常: {e}")

    def add_draft(self, title, author, digest, content, thumb_media_id, content_source_url=""):
        """
        新建草稿

        Args:
            title: 标题
            author: 作者
            digest: 摘要
            content: 正文（HTML 格式）
            thumb_media_id: 封面图片 media_id
            content_source_url: 原文链接

        Returns:
            str: 草稿 media_id

        Raises:
            Exception: 创建失败
        """
        access_token = self.get_access_token()
        url = f"{self.base_url}/draft/add?access_token={access_token}"

        articles = [{
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": content_source_url,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 0,
            "only_fans_can_comment": 0
        }]

        payload = {"articles": articles}

        try:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json; charset=utf-8'}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            if 'media_id' in result:
                print(f"     草稿创建成功: {result['media_id']}")
                return result['media_id']
            else:
                error_msg = result.get('errmsg', '未知错误')
                raise Exception(f"草稿创建失败: {error_msg}")

        except Exception as e:
            raise Exception(f"草稿创建异常: {e}")

    def publish_draft(self, media_id):
        """
        发布草稿

        Args:
            media_id: 草稿 media_id

        Returns:
            dict: 发布结果，包含 publish_id, msg_data_id, idx

        Raises:
            Exception: 发布失败
        """
        access_token = self.get_access_token()
        url = f"{self.base_url}/freepublish/submit?access_token={access_token}"

        payload = {"media_id": media_id}

        try:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json; charset=utf-8'}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            if 'publish_id' in result:
                print(f"     草稿发布成功: publish_id={result['publish_id']}")
                return result
            else:
                error_msg = result.get('errmsg', '未知错误')
                raise Exception(f"草稿发布失败: {error_msg}")

        except Exception as e:
            raise Exception(f"草稿发布异常: {e}")

    def get_publish_status(self, publish_id):
        """
        查询发布状态

        Args:
            publish_id: 发布任务 ID

        Returns:
            dict: 发布状态

        Raises:
            Exception: 查询失败
        """
        access_token = self.get_access_token()
        url = f"{self.base_url}/freepublish/get?access_token={access_token}"

        payload = {"publish_id": publish_id}

        try:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json; charset=utf-8'}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            if 'publish_status' in result:
                return result
            else:
                error_msg = result.get('errmsg', '未知错误')
                raise Exception(f"查询发布状态失败: {error_msg}")

        except Exception as e:
            raise Exception(f"查询发布状态异常: {e}")

    def publish_article(self, title, author, digest, content, thumb_image_path, content_source_url=""):
        """
        完整发布流程：上传图片 → 创建草稿 → 发布

        Args:
            title: 标题
            author: 作者
            digest: 摘要
            content: 正文（HTML 格式）
            thumb_image_path: 封面图片路径
            content_source_url: 原文链接

        Returns:
            dict: 发布结果

        Raises:
            Exception: 发布失败
        """
        print(f"  [1/3] 上传封面图片...")
        thumb_media_id = self.upload_news_image(thumb_image_path)

        print(f"  [2/3] 创建草稿...")
        media_id = self.add_draft(title, author, digest, content, thumb_media_id, content_source_url)

        print(f"  [3/3] 发布草稿...")
        result = self.publish_draft(media_id)

        return result


def publish_to_wechat_official(title, author, digest, content, thumb_image_path, content_source_url=""):
    """
    发布文章到微信公众号的便捷函数

    Args:
        title: 标题
        author: 作者
        digest: 摘要
        content: 正文（HTML 格式）
        thumb_image_path: 封面图片路径
        content_source_url: 原文链接

    Returns:
        bool: 是否发布成功
    """
    # 读取配置
    here = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(here, "push_config.json")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"  [WARN] 读取配置文件失败: {e}")
        return False

    wechat_config = config.get('wechat_official', {})

    # 检查是否启用
    if not wechat_config.get('enabled', False):
        print("  微信公众号推送未启用（配置文件 enabled=false）")
        return False

    # 获取 appid 和 appsecret（优先环境变量）
    appid = os.getenv('WECHAT_APPID') or wechat_config.get('appid', '')
    appsecret = os.getenv('WECHAT_APPSECRET') or wechat_config.get('appsecret', '')

    if not appid or not appsecret:
        print("  [WARN] 微信公众号 AppID 或 AppSecret 未配置")
        return False

    try:
        publisher = WechatOfficialPublisher(appid, appsecret)
        result = publisher.publish_article(
            title=title,
            author=author,
            digest=digest,
            content=content,
            thumb_image_path=thumb_image_path,
            content_source_url=content_source_url
        )

        print(f"  ✓ 微信公众号发布成功")
        print(f"    publish_id: {result.get('publish_id')}")
        print(f"    msg_data_id: {result.get('msg_data_id')}")

        return True

    except Exception as e:
        print(f"  [!] 微信公众号发布失败: {e}")
        return False


# 测试函数
if __name__ == "__main__":
    print("测试微信公众号发布...")

    # 测试配置
    test_title = "AI 日报测试"
    test_author = "AI 日报"
    test_digest = "这是一条测试消息"
    test_content = """
    <h1>测试标题</h1>
    <p>这是测试内容。</p>
    <p><b>粗体文本</b></p>
    <p><i>斜体文本</i></p>
    """
    test_thumb = "test_cover.jpg"  # 需要提供实际的图片文件

    success = publish_to_wechat_official(
        title=test_title,
        author=test_author,
        digest=test_digest,
        content=test_content,
        thumb_image_path=test_thumb,
        content_source_url="https://example.com"
    )

    print(f"\n发布结果: {'成功' if success else '失败'}")
