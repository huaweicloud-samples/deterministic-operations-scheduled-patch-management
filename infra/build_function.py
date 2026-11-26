#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 FunctionGraph 部署包（patch_orchestrator.zip）
==================================================
解决「打包必须自带 SDK 依赖」问题：

1. 在独立 venv 中安装 huaweicloudsdk*，从其 site-packages 复制依赖（避免用到没装 SDK 的 Python）。
2. 只复制纯 Python 包，跳过原生扩展（.so/.pyd）；FGS 运行环境是 Linux x86_64，
   Windows 原生模块会静默崩（obs 是运行环境内置的，也不要自带）。
3. 过滤 __pycache__/*.pyc（本地 3.13 编译、运行时 3.9 会 magic number 不匹配静默崩）。
4. 两道护栏：缺 SDK 即报错退出；产物 < 200KB 即报错（带 SDK 应 > 2MB）。

用法：
    python infra/build_function.py
"""
import os
import sys
import shutil
import zipfile
import subprocess
import sysconfig

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC_DIR = os.path.join(REPO, "src", "functions", "patch_orchestrator")
BUILD_DIR = os.path.join(HERE, "build")
VENV_DIR = os.path.join(BUILD_DIR, "venv")
ZIP_PATH = os.path.join(BUILD_DIR, "patch_orchestrator.zip")

# 需要打进 zip 的纯 Python 包（核心 + HSS + SMN）。FunctionGraph SDK 仅部署脚本用，不入包。
BUNDLE_PACKAGES = [
    "huaweicloudsdkcore",
    "huaweicloudsdkhss",
    "huaweicloudsdksmn",
    # 上述 SDK 的纯 Python 依赖
    "requests", "urllib3", "certifi", "idna", "charset_normalizer",
    "six", "defusedxml",
]

SKIP_EXT = (".so", ".pyd", ".dll")
SKIP_DIRS = ("__pycache__", "tests", ".pytest_cache")


def site_packages():
    for root, dirs, _ in os.walk(os.path.join(VENV_DIR, "Lib")):
        if os.path.basename(root) == "site-packages":
            return root
    # Linux / 其他布局
    for root, dirs, _ in os.walk(VENV_DIR):
        if os.path.basename(root) == "site-packages":
            return root
    raise SystemExit("未找到 venv 的 site-packages")


def ensure_venv():
    if not os.path.isdir(VENV_DIR):
        print(">> 创建 venv:", VENV_DIR, flush=True)
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    py = os.path.join(VENV_DIR, "Scripts", "python.exe")
    if not os.path.exists(py):
        py = os.path.join(VENV_DIR, "bin", "python")
    # 安装 SDK 到 venv（版本以 requirements.txt 为准，避免小版本漂移导致方法名失效）
    req = os.path.join(REPO, "src", "functions", "patch_orchestrator", "requirements.txt")
    subprocess.check_call([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "--quiet", "-r", req])
    # 部署脚本（deploy_function.py）用的 functiongraph SDK，不入包，单独装
    subprocess.check_call([py, "-m", "pip", "install", "--quiet", "huaweicloudsdkfunctiongraph"])
    return py


def copy_package(sp_dir, name, zf):
    pkg_dir = os.path.join(sp_dir, name)
    # 兼容单文件模块（如 six.py），它们不是目录而是 .py 文件
    pkg_file = os.path.join(sp_dir, name + ".py")
    if not os.path.isdir(pkg_dir) and os.path.isfile(pkg_file):
        zf.write(pkg_file, name + ".py")
        return
    if not os.path.isdir(pkg_dir):
        raise SystemExit(f"缺失依赖包：{name}（venv 安装是否成功？）")
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(SKIP_EXT):
                continue
            if f.endswith(".pyc") or f.endswith(".dist-info") or f.endswith(".egg-info"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, sp_dir)
            zf.write(full, rel)


def build():
    py = ensure_venv()
    sp_dir = site_packages()

    # 护栏 1：缺核心 SDK 直接退出
    if not os.path.isdir(os.path.join(sp_dir, "huaweicloudsdkcore")):
        raise SystemExit("ERROR: venv 中未找到 huaweicloudsdkcore，打包中止。")

    # 直接用 "w" 模式打开会截断原文件，无需先 os.remove（避免无关删除拦截）。
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        # 业务代码放 zip 根目录
        for fname in ("index.py", "hss_patch_client.py"):
            src = os.path.join(SRC_DIR, fname)
            if not os.path.exists(src):
                raise SystemExit(f"ERROR: 找不到业务代码 {src}")
            zf.write(src, fname)
        # SDK 依赖
        for pkg in BUNDLE_PACKAGES:
            copy_package(sp_dir, pkg, zf)

    size = os.path.getsize(ZIP_PATH)
    # 护栏 2：体积护栏（带 SDK 应 > 2MB）
    if size < 200 * 1024:
        raise SystemExit(f"ERROR: 产物仅 {size/1024:.0f}KB，疑似未打入 SDK，打包中止。")

    print(f">> 构建完成: {ZIP_PATH} ({size/1024/1024:.1f} MB)", flush=True)
    print(">> 使用 venv 运行部署脚本: " + py, flush=True)


if __name__ == "__main__":
    build()
