#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号发布接口 - 简化的发布函数
"""
from wechat_official_publisher import WechatOfficialPublisher


def publish_to_wechat(appid, appsecret, title, content, author, digest, content_source_url, thumb_image_path):
    """
    发布文章到微信公众号

    Args:
        appid: 微信公众号 AppID
        appsecret: 微信公众号 AppSecret
        title: 文章标题
        content: 文章正文（HTML 格式）
        author: 作者
        digest: 摘要
        content_source_url: 原文链接
        thumb_image_path: 封面图片路径

    Returns:
        str: publish_id，发布成功返回；失败返回 None
    """
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

        return result.get('publish_id')

    except Exception as e:
        print(f"  发布失败: {e}")
        return None
