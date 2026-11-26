# ============================================================================
# LTS 日志组/流
# ----------------------------------------------------------------------------
# FunctionGraph 的运行日志默认投递到 LTS。此处显式创建日志组/流，
# 作为函数日志的落地位置，便于集中查询与留存（ttl_in_days）。
# 注：FunctionGraph 日志投递由平台自动完成，无需在函数上显式绑定。
# ============================================================================

resource "huaweicloud_lts_group" "patch" {
  group_name  = "${var.project_name}-lts"
  ttl_in_days = 7
}

resource "huaweicloud_lts_stream" "patch" {
  group_id    = huaweicloud_lts_group.patch.id
  stream_name = "${var.project_name}-orchestrator"
  ttl_in_days = 7
}
