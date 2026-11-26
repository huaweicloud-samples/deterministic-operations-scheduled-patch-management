# 华为云集中式多区域主机补丁编排 · 部署指导书

## 1. 前置条件

- 华为云账号（推荐企业主账号或具备 IAM 管理权限的子账号），区域 `cn-north-4`（可改）。
- 本地安装：Terraform >= 1.5、Python >= 3.9（用于构建函数包）。
- 目标 ECS 主机已存在，并在目标企业项目内**开启 HSS 防护**（专业版/企业版/旗舰版才支持漏洞一键修复）。
- 凭证：准备 AK/SK（仅用于本地 `terraform` / 函数代码上传，**不写入任何文件**）：
```bash
export HW_ACCESS_KEY="<AK>"
export HW_SECRET_KEY="<SK>"
```

## 2. 快速开始

```bash
# 1) 构建函数部署包（含 huaweicloudsdk 依赖，带缺依赖/体积护栏）
python infra/build_function.py

# 2) 初始化并预览
terraform -chdir=infra init
terraform -chdir=infra plan

# 3) 应用（会自动用 SDK 兜底上传函数代码）
terraform -chdir=infra apply
```

> 默认 `enable_obs=true`、`enable_smn=true`。若不需要通知，部署前在 `terraform apply` 加
> `-var="enable_smn=false"`；邮件订阅需收件人点击确认邮件后才生效。

## 3. 分步说明

### 3.1 构建函数包
`infra/build_function.py` 会创建 `infra/build/venv`、安装 SDK、将 `src/functions/patch_orchestrator`
与纯 Python 依赖打进 `infra/build/patch_orchestrator.zip`，并校验体积（<200KB 视为未打入 SDK 报错退出）。
**每次修改函数代码后需重新构建**，并以 `terraform apply -replace=huaweicloud_fgs_function.patch_orchestrator` 触发重传。

### 3.2 部署资源
`terraform apply` 创建：IAM 委托、FunctionGraph 函数、TIMER 触发器、LTS 日志组/流、OBS 报告桶（含桶策略）、SMN 主题。
函数代码由 `null_resource` 经 FunctionGraph SDK 兜底上传（规避 provider 本地 zip 上传在 Windows 不可靠的坑）。

### 3.3 手动验证（L3 业务功能）
同步调用函数（绕过定时器）验证编排逻辑：
```bash
# 使用 FunctionGraph SDK 同步调用，x_cff_log_type=tail 可直取日志
python - <<'PY'
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkfunctiongraph.v2 import FunctionGraphClient, InvokeFunctionRequest
import os, json
creds = BasicCredentials(os.environ["HW_ACCESS_KEY"], os.environ["HW_SECRET_KEY"])
client = (FunctionGraphClient.new_builder()
.with_endpoint("https://functiongraph.cn-north-4.myhuaweicloud.com")
.with_credentials(creds).build())
req = InvokeFunctionRequest()
req.function_urn = "<functions.outputs.function_urn>"
req.body = "{}"
req.x_cff_log_type = "tail"
req.x_cff_request_version = "v1"
r = client.invoke_function(req)
print(r.status, r.result, r.log)
PY
```
预期：`status=200`，`result` 含 `{"statusCode":200,"body":{...}}`，且 `body.regions` 列出各区域主机数与操作。

### 3.4 验证定时触发
控制台「函数工作流 → 触发器」可见 `patch-schedule`（ACTIVE）；或在 LTS 日志组查看按 Cron 触发的运行日志。

## 4. 清理资源

```bash
terraform -chdir=infra destroy
```
> OBS 桶未开版本控制，`destroy` 可正常删除；销毁后建议到控制台确认无残留 EIP/函数/LTS。

## 5. 跨账号扩展（可选）

若需跨账号补丁：
1. 在每个目标账号下用独立 provider 部署 `infra/modules/target-account-agency`
（`management_account_domain_id` 取管理账号 `data.huaweicloud_account.current.id`）。
2. 部署时在 `terraform apply` 传入 `-var='target_accounts=["<目标账号ID>"]'`，并在
`infra/build_function.py` 的 `BUNDLE_PACKAGES` 加入 `huaweicloudsdkiam` 以支持凭证交换。
