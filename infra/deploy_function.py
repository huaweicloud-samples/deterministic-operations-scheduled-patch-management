#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 FunctionGraph SDK 兜底上传函数代码（解决 provider 本地 zip 上传在 Windows 不可靠的问题）。
由 infra/function.tf 的 null_resource 调用（使用 build/venv 的 python 运行）。

凭证取自环境变量（从运行 terraform 的 shell 继承，不落盘）：
    HW_ACCESS_KEY / HW_SECRET_KEY  （必填）
    HW_SECURITY_TOKEN              （可选，临时凭证场景）

用法：
    python deploy_function.py --urn <urn> --region <region> --zip <path.zip>
"""
import os
import sys
import argparse
import base64

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkfunctiongraph.v2 import (
    FunctionGraphClient,
    UpdateFunctionCodeRequest,
    UpdateFunctionCodeRequestBody,
    FuncCode,
)
from huaweicloudsdkcore.exceptions import exceptions


def parse_project_id(urn):
    # urn:fss:<region>:<project_id>:function:<group>:<name>:latest
    parts = urn.split(":")
    if len(parts) >= 4:
        return parts[3]
    raise SystemExit(f"无法从 URN 解析 project_id: {urn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urn", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--zip", required=True)
    args = ap.parse_args()

    ak = os.environ.get("HW_ACCESS_KEY")
    sk = os.environ.get("HW_SECRET_KEY")
    token = os.environ.get("HW_SECURITY_TOKEN")
    if not ak or not sk:
        raise SystemExit("ERROR: 缺少 HW_ACCESS_KEY / HW_SECRET_KEY 环境变量（请在运行 terraform 前 export）。")

    project_id = parse_project_id(args.urn)

    with open(args.zip, "rb") as f:
        data = f.read()

    creds = BasicCredentials(ak, sk, project_id)
    if token:
        creds = creds.with_security_token(token)

    client = (
        FunctionGraphClient.new_builder()
        .with_endpoint(f"https://functiongraph.{args.region}.myhuaweicloud.com")
        .with_credentials(creds)
        .build()
    )

    req = UpdateFunctionCodeRequest()
    req.function_urn = args.urn
    # 关键：请求体必须显式带 code_type="zip"，否则报 FSS.1006 Invalid function code type
    body = UpdateFunctionCodeRequestBody()
    body.code_type = "zip"
    body.func_code = FuncCode(file=base64.b64encode(data).decode("ascii"))
    req.body = body

    try:
        resp = client.update_function_code(req)
        print(f">> 代码上传成功: {args.urn}", flush=True)
        print(f"   last_modified: {getattr(resp, 'last_modified', 'n/a')}", flush=True)
    except exceptions.ClientRequestException as e:
        raise SystemExit(f"ERROR: 上传代码失败 {e.status_code} {e.error_code} {e.error_msg}")


if __name__ == "__main__":
    main()
