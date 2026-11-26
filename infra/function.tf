# ============================================================================
# FunctionGraph 编排函数
# ----------------------------------------------------------------------------
# 编排函数实现要点：
#   - 由 TIMER 触发器按 Cron 唤起
#   - 读取环境变量中的目标区域/账号/操作，调用 HSS 在各区域执行漏洞扫描/修复
#   - 将运行汇总写入 OBS（可选）、结果推送 SMN（可选）
#
# 代码以 zip 包部署（code_type=zip），运行期依赖 huaweicloudsdkhss/smn 已打进 zip。
# 部署两步：
#   1) python infra/build_function.py   # 构建并校验 zip（含 SDK 依赖）
#   2) terraform apply                  # 建资源 + terraform_data 用 SDK 兜底上传代码
# 打包/上传要点详见 docs/deployment-guide.md。
# ============================================================================

resource "huaweicloud_fgs_function" "patch_orchestrator" {
  name        = "${var.project_name}-orchestrator"
  app         = "default"
  agency      = huaweicloud_identity_agency.patch_orchestrator.name
  handler     = "index.handler"
  runtime     = "Python3.9"
  memory_size = 256
  timeout     = 300

  # 本地 zip 包；provider 上传在 Windows 上不可靠，
  # 下方 terraform_data 通过 FunctionGraph SDK 兜底上传。
  code_type = "zip"
  code_url  = "${path.module}/build/patch_orchestrator.zip"

  user_data = jsonencode({
    OPERATION             = var.operation
    REBOOT_OPTION         = var.reboot_option
    ENTERPRISE_PROJECT_ID = var.enterprise_project_id
    ENABLE_OBS            = var.enable_obs ? "true" : "false"
    ENABLE_SMN            = var.enable_smn ? "true" : "false"
    OBS_BUCKET            = var.enable_obs ? huaweicloud_obs_bucket.patch_reports[0].bucket : ""
    SMN_TOPIC_URN         = var.enable_smn ? huaweicloud_smn_topic.patch_notify[0].topic_urn : ""
    EXECUTION_ROLE_NAME   = huaweicloud_identity_agency.patch_orchestrator.name
    MASTER_ACCOUNT_ID     = data.huaweicloud_account.current.id
  })

  lifecycle {
    # 代码运行期所有权让给部署脚本；避免每次 apply 触发 FSS.1012 重传
    ignore_changes = [code_url]
  }
}

# ---------------------------------------------------------------------------
# 兜底上传代码（解决 provider 本地 zip 上传在 Windows 不可靠的问题）
# 使用内置 terraform_data（无需 null provider）；凭证从运行 terraform 的 shell 环境继承
# （export HW_ACCESS_KEY / HW_SECRET_KEY）。函数重建或显式 -replace 本资源时重新上传。
# ---------------------------------------------------------------------------
resource "terraform_data" "deploy_function_code" {
  depends_on = [huaweicloud_fgs_function.patch_orchestrator]

  triggers_replace = [huaweicloud_fgs_function.patch_orchestrator.id]

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      VENV_PY="$(cd "${path.module}" && pwd)/build/venv/Scripts/python.exe"
      if [ ! -x "$VENV_PY" ]; then
        echo "ERROR: venv 未就绪，请先运行: python ${path.module}/build_function.py" >&2
        exit 1
      fi
      "$VENV_PY" "${path.module}/deploy_function.py" \
        --urn "${huaweicloud_fgs_function.patch_orchestrator.id}" \
        --region "${var.region}" \
        --zip "${path.module}/build/patch_orchestrator.zip"
    EOT
  }
}
