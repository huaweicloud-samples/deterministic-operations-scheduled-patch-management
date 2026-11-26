# -*- coding: utf-8 -*-
"""L3 同步调用验证：用 FunctionGraph SDK 同步触发 patch_orchestrator 函数。

用法（在已装 SDK 的 venv 中，且已 export HW_ACCESS_KEY/HW_SECRET_KEY）：
    python invoke_test.py --urn <function_urn> --region cn-north-4 --project <project_id> \
        [--event '{}']
"""
import argparse
import json
import os

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkfunctiongraph.v2 import (
    FunctionGraphClient,
    InvokeFunctionRequest,
)
from huaweicloudsdkfunctiongraph.v2.region.functiongraph_region import FunctionGraphRegion


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--urn", required=True, help="函数 URN（terraform output function_urn）")
    p.add_argument("--region", default="cn-north-4")
    p.add_argument("--project", required=True, help="cn-north-4 项目 ID（URN 中的 project 段）")
    p.add_argument("--event", default="{}", help="传给函数的事件 JSON 字符串")
    p.add_argument("--ak", default=os.environ.get("HW_ACCESS_KEY"))
    p.add_argument("--sk", default=os.environ.get("HW_SECRET_KEY"))
    args = p.parse_args()

    creds = BasicCredentials(args.ak, args.sk, args.project)
    client = (
        FunctionGraphClient.new_builder()
        .with_credentials(creds)
        .with_region(FunctionGraphRegion.value_of(args.region))
        .build()
    )

    req = InvokeFunctionRequest()
    req.function_urn = args.urn
    try:
        req.body = json.loads(args.event)
    except json.JSONDecodeError:
        req.body = {}
    # 同步调用结果在 raw_content（bytes），不在 body/status（FGS 同步响应）。
    req.x_cff_log_type = "tail"

    resp = client.invoke_function(req)
    print("=== INVOKE RESPONSE ===")
    # 同步调用带 x_cff_log_type=tail 时，日志与结果可能分别在 log / raw_content 字段。
    for attr in ("log", "logs", "raw_content", "body", "status"):
        val = getattr(resp, attr, None)
        if val is None:
            continue
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        if attr == "body":
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False, indent=2)
            else:
                val = repr(val)
        print(f"--- {attr} ---")
        print(val)


if __name__ == "__main__":
    main()
