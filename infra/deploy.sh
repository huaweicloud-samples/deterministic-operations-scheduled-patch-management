#!/usr/bin/env bash
# ============================================================================
# 一键部署：构建函数包 → terraform init → terraform apply
# ----------------------------------------------------------------------------
# 顺序很关键：必须先把 zip 构建出来（build_function.py 会建 venv + 装 SDK + 打包），
# 否则 function.tf 里的 code_url 指向的本地 zip 不存在，apply 会失败。
# 用法（在 infra/ 目录下，Git Bash / WSL / macOS 终端）：
#   bash deploy.sh
# 凭证通过环境变量注入（不落盘）：
#   export HW_ACCESS_KEY=<AK> HW_SECRET_KEY=<SK>
#   （terraform 与兜底上传脚本都从当前 shell 继承）
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

TF_BIN="${TERRAFORM_BIN:-terraform}"

echo ">> [1/3] 构建函数包（自动建 venv + 安装 SDK + 打包 zip）"
python build_function.py

echo ">> [2/3] terraform init"
"$TF_BIN" init -no-color

echo ">> [3/3] terraform apply"
echo "   提醒：apply 会创建若干用量型资源，确认资源清单符合预期后输入 yes 继续。"
"$TF_BIN" apply -no-color
