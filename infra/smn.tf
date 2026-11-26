# ============================================================================
# SMN 通知（主题订阅，集中告警能力）
# ----------------------------------------------------------------------------
# 函数每次运行结束后将汇总（扫描/修复主机数、漏洞数、失败项）推送到该主题。
# 邮件订阅需收件人点击确认邮件后 status=1 才生效。
# ============================================================================

resource "huaweicloud_smn_topic" "patch_notify" {
  count        = var.enable_smn ? 1 : 0
  name         = "${var.project_name}-patch-notify"
  display_name = "Centralized patch notifications"
}

resource "huaweicloud_smn_subscription" "email" {
  count     = var.enable_smn ? length(var.smn_subscription_emails) : 0
  topic_urn = huaweicloud_smn_topic.patch_notify[0].topic_urn
  protocol  = "email"
  endpoint  = var.smn_subscription_emails[count.index]
}
