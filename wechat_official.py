#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号发布模块
功能：将日报内容自动发布到微信公众号
"""

import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime


# ----------------------------- 配置 -----------------------------
TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".wechat_token_cache.json")


# ----------------------------- Access Token 管理 -----------------------------
def get_access_token(appid, appsecret, force_refresh=False):
    """获取 access_token，优先从缓存读取，过期或强制刷新时重新获取。

    Args:
        appid: 公众号 AppID
        appsecret: 公众号 AppSecret
        force_refresh: 是否强制刷新（忽略缓存）

    Returns:
        access_token 字符串，失败时返回 None
    """
    # 尝试从缓存读取
    if not force_refresh and os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                token = cache.get("access_token")
                expires_at = cache.get("expires_at", 0)

                # 提前 5 分钟刷新，避免边界情况
                if token and time.time() < expires_at - 300:
                    print(f"     使用缓存的 access_token（剩余 {int((expires_at - time.time()) / 60)} 分钟）")
                    return token
        except Exception as e:
            print(f"     [!] 读取 token 缓存失败：{e!r}")

    # 重新获取 token
    url = (
        f"https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={appid}&secret={appsecret}"
    )

    try:
        print("     正在获取新的 access_token ...")
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if "access_token" in data:
            token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            expires_at = time.time() + expires_in

            # 写入缓存
            try:
                with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "access_token": token,
                        "expires_at": expires_at,
                        "updated_at": datetime.now().isoformat(),
                    }, f, indent=2, ensure_ascii=False)
                print(f"     已获取新 token（有效期 {expires_in} 秒）")
            except Exception as e:
                print(f"     [!] 缓存 token 失败：{e!r}")

            return token
        else:
            errcode = data.get("errcode", "unknown")
            errmsg = data.get("errmsg", "unknown error")
            print(f"     [!] 获取 access_token 失败：errcode={errcode}, errmsg={errmsg}")
            return None

    except Exception as e:
        print(f"     [!] 请求 access_token 异常：{e!r}")
        return None


# ----------------------------- 草稿和发布 -----------------------------
def create_draft(access_token, articles):
    """创建草稿（图文素材）。

    Args:
        access_token: 微信 access_token
        articles: 图文列表，每篇图文格式：
            {
                "title": "标题",
                "author": "作者",
                "digest": "摘要",
                "content": "正文HTML",
                "content_source_url": "阅读原文链接（选填）",
                "thumb_media_id": "封面图片 media_id（必填，需先上传）",
                "need_open_comment": 0,  # 是否打开评论，0 不打开，1 打开
                "only_fans_can_comment": 0  # 是否粉丝才可评论，0 所有人可评论，1 粉丝可评论
            }

    Returns:
        成功返回 media_id，失败返回 None
    """
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"

    payload = {"articles": articles}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if "media_id" in result:
            media_id = result["media_id"]
            print(f"     草稿创建成功，media_id: {media_id}")
            return media_id
        else:
            errcode = result.get("errcode", "unknown")
            errmsg = result.get("errmsg", "unknown error")
            print(f"     [!] 创建草稿失败：errcode={errcode}, errmsg={errmsg}")
            return None

    except Exception as e:
        print(f"     [!] 创建草稿异常：{e!r}")
        return None


def publish_draft(access_token, media_id):
    """发布草稿到公众号。

    Args:
        access_token: 微信 access_token
        media_id: 草稿的 media_id

    Returns:
        成功返回 publish_id，失败返回 None
    """
    url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}"

    payload = {"media_id": media_id}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if result.get("errcode", -1) == 0:
            publish_id = result.get("publish_id", "")
            msg_data_id = result.get("msg_data_id", "")
            print(f"     发布成功！publish_id: {publish_id}, msg_data_id: {msg_data_id}")
            return publish_id
        else:
            errcode = result.get("errcode", "unknown")
            errmsg = result.get("errmsg", "unknown error")
            print(f"     [!] 发布失败：errcode={errcode}, errmsg={errmsg}")
            return None

    except Exception as e:
        print(f"     [!] 发布异常：{e!r}")
        return None


def upload_permanent_material(access_token, image_path, material_type="image"):
    """上传永久素材（图片），用于草稿封面。

    注意：必须用永久素材接口 material/add_material，不能用 media/upload。
    后者传的是临时素材（3 天过期），draft/add 的 thumb_media_id 不接受，
    会报 invalid media_id (errcode 40007)。

    Args:
        access_token: 微信 access_token
        image_path: 图片文件路径
        material_type: 素材类型，默认 "image"

    Returns:
        成功返回 media_id，失败返回 None
    """
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type={material_type}"

    try:
        # 读取图片文件
        with open(image_path, "rb") as f:
            file_data = f.read()

        # 构造 multipart/form-data 请求
        boundary = "----WebKitFormBoundary" + "".join([str(int(time.time() * 1000000))])
        content_type = f"multipart/form-data; boundary={boundary}"

        filename = os.path.basename(image_path)
        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"media\"; filename=\"{filename}\"\r\n"
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if "media_id" in result:
            media_id = result["media_id"]
            print(f"     图片上传成功，media_id: {media_id}")
            return media_id
        else:
            errcode = result.get("errcode", "unknown")
            errmsg = result.get("errmsg", "unknown error")
            print(f"     [!] 上传图片失败：errcode={errcode}, errmsg={errmsg}")
            return None

    except Exception as e:
        print(f"     [!] 上传图片异常：{e!r}")
        return None


# ----------------------------- 主流程 -----------------------------
def publish_to_wechat(appid, appsecret, title, content, author="AI Daily Push",
                      digest="", content_source_url="", thumb_image_path=None):
    """将内容发布到微信公众号（完整流程）。

    Args:
        appid: 公众号 AppID
        appsecret: 公众号 AppSecret
        title: 文章标题
        content: 文章正文（HTML 格式）
        author: 作者名称
        digest: 文章摘要
        content_source_url: 阅读原文链接
        thumb_image_path: 封面图片路径（可选，如不提供则使用默认图）

    Returns:
        成功返回 publish_id，失败返回 None
    """
    print(f"\n开始发布到微信公众号：{title}")

    # 1. 获取 access_token
    token = get_access_token(appid, appsecret)
    if not token:
        return None

    # 2. 上传封面图片（如果提供了路径）
    thumb_media_id = None
    if thumb_image_path and os.path.exists(thumb_image_path):
        thumb_media_id = upload_permanent_material(token, thumb_image_path)

    # 如果没有封面图或上传失败，使用一个占位符（实际使用时需要提供真实图片）
    if not thumb_media_id:
        print("     [!] 未提供封面图或上传失败，草稿创建将失败")
        print("     提示：需要先上传封面图片才能创建草稿")
        return None

    # 3. 创建草稿
    articles = [{
        "title": title,
        "author": author,
        "digest": digest or title[:50],  # 摘要为空时使用标题前 50 字
        "content": content,
        "content_source_url": content_source_url,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }]

    media_id = create_draft(token, articles)
    if not media_id:
        return None

    # 4. 发布草稿
    publish_id = publish_draft(token, media_id)
    return publish_id


if __name__ == "__main__":
    # 测试代码
    import sys

    appid = os.environ.get("WECHAT_APPID", "")
    appsecret = os.environ.get("WECHAT_APPSECRET", "")

    if not appid or not appsecret:
        print("请设置环境变量：WECHAT_APPID 和 WECHAT_APPSECRET")
        sys.exit(1)

    # 测试获取 token
    token = get_access_token(appid, appsecret)
    if token:
        print(f"\n✓ Access Token 获取成功")
        print(f"  Token 前 20 字符: {token[:20]}...")
    else:
        print("\n✗ Access Token 获取失败")
