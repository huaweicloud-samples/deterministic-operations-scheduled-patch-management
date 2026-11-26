# ============================================================================
# 定时触发器（TIMER）
# ----------------------------------------------------------------------------
# 定时调度规则（ScheduleExpression）。
# 使用 huaweicloud_fgs_trigger + timer{} 块：timer 块属性为 ForceNew，
# 修改调度会重建触发器，规避 ACTIVE 触发器就地更新被拒（FSS.1153）的问题。
#
# Cron 为 6 段：秒 分 时 日 月 周；schedule_type 必须是 "Cron"（首字母大写）。
# 时区：FunctionGraph 定时器以 UTC 评估。
# ============================================================================

resource "huaweicloud_fgs_trigger" "patch_schedule" {
  function_urn = huaweicloud_fgs_function.patch_orchestrator.id
  type         = "TIMER"
  status       = "ACTIVE"

  timer {
    name          = "${var.project_name}-schedule"
    schedule_type = "Cron"
    schedule      = var.schedule_expression
  }
}
