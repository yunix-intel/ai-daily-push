#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Workflow 互斥锁检查
防止手动触发和定时触发同时运行
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOCK_FILE = Path(__file__).parent / ".workflow_lock"
LOCK_TIMEOUT = 3600  # 1小时超时

def check_lock():
    """检查是否有其他实例正在运行"""
    if LOCK_FILE.exists():
        # 读取锁文件
        lock_time_str = LOCK_FILE.read_text().strip()
        try:
            lock_time = datetime.fromisoformat(lock_time_str)
            elapsed = (datetime.now(timezone.utc) - lock_time).total_seconds()

            if elapsed < LOCK_TIMEOUT:
                print(f"[WARNING] 检测到另一个实例正在运行（{int(elapsed/60)}分钟前开始）")
                print(f"为避免重复推送，本次运行终止")
                return False
            else:
                print(f"[WARNING] 发现过期锁文件（{int(elapsed/3600)}小时前），清除")
                LOCK_FILE.unlink()
        except Exception as e:
            print(f"[WARNING] 锁文件格式错误，清除：{e}")
            LOCK_FILE.unlink()

    # 创建锁文件
    LOCK_FILE.write_text(datetime.now(timezone.utc).isoformat())
    return True

def release_lock():
    """释放锁"""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "release":
        release_lock()
        print("[OK] 锁已释放")
    else:
        if check_lock():
            print("[OK] 锁已获取，可以继续")
            sys.exit(0)
        else:
            sys.exit(1)
