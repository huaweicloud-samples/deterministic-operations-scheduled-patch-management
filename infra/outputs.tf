# ============================================================================
# 输出
# ============================================================================

output "function_urn" {
  description = "编排函数 FunctionGraph URN（第 4 段为 project_id）"
  value       = huaweicloud_fgs_function.patch_orchestrator.id
}

output "trigger_id" {
  description = "TIMER 触发器 ID"
  value       = huaweicloud_fgs_trigger.patch_schedule.id
}

output "agency_name" {
  description = "FunctionGraph 委托名称"
  value       = huaweicloud_identity_agency.patch_orchestrator.name
}

output "obs_bucket" {
  description = "补丁报告桶（enable_obs=true 时）"
  value       = var.enable_obs ? huaweicloud_obs_bucket.patch_reports[0].bucket : ""
}

output "smn_topic_urn" {
  description = "补丁通知主题 URN（enable_smn=true 时）"
  value       = var.enable_smn ? huaweicloud_smn_topic.patch_notify[0].topic_urn : ""
}

output "lts_group_id" {
  description = "函数日志组 ID"
  value       = huaweicloud_lts_group.patch.id
}
