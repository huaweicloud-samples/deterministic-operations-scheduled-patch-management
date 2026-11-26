# ============================================================================
# 变量定义
# ============================================================================

variable "region" {
  description = "华为云区域（管理账号所在区域，也是默认补丁目标区域）"
  type        = string
  default     = "cn-north-4" # 北京四
}

variable "project_name" {
  description = "项目名称，用于资源命名前缀"
  type        = string
  default     = "central-patch"
}

variable "schedule_expression" {
  description = "FunctionGraph TIMER 触发器 Cron 表达式（6 段：秒 分 时 日 月 周）。默认周二 02:00（UTC）。"
  type        = string
  default     = "0 0 2 ? * TUE"
}

# ---- 补丁目标范围 ----
variable "target_regions" {
  description = "补丁目标区域列表（多区域）。默认仅管理账号所在区域。"
  type        = list(string)
  default     = []
}

variable "target_accounts" {
  description = "补丁目标账号 ID 列表（跨账号）。为空表示仅当前（管理）账号。跨账号需在目标账号内部署 modules/target-account-agency 并在函数内启用 agency token 交换（见 src 注释）。华为云 HSS 为按账号隔离的服务，跨账号无法直接用管理账号凭证调用，必须经目标账号的跨账号委托换取临时凭证。"
  type        = list(string)
  default     = []
}

# ---- 补丁操作 ----
variable "operation" {
  description = "补丁操作：Scan=仅扫描漏洞；Install=扫描并修复漏洞。"
  type        = string
  default     = "Scan"
  validation {
    condition     = contains(["Scan", "Install"], var.operation)
    error_message = "operation 只能是 Scan 或 Install。"
  }
}

variable "reboot_option" {
  description = "修复后重启行为（仅 Install 生效）。NoReboot=不重启；RebootIfNeeded=按需重启。注意：HSS 对 Windows/Linux Kernel 类漏洞修复后需重启才生效。"
  type        = string
  default     = "NoReboot"
  validation {
    condition     = contains(["NoReboot", "RebootIfNeeded"], var.reboot_option)
    error_message = "reboot_option 只能是 NoReboot 或 RebootIfNeeded。"
  }
}

variable "enterprise_project_id" {
  description = "企业项目 ID，用于圈定补丁目标主机范围。默认 '0' 表示所有企业项目（全部主机）。"
  type        = string
  default     = "0"
}

variable "max_concurrency" {
  description = "单区域内并发修复/扫描的主机比例或数量。"
  type        = string
  default     = "10%"
}

variable "max_errors" {
  description = "单区域内允许的错误阈值。"
  type        = string
  default     = "10%"
}

# ---- 可选组件开关 ----
variable "enable_obs" {
  description = "是否创建 OBS 桶用于存储每次补丁运行的汇总报告。"
  type        = bool
  default     = true
}

variable "obs_bucket_name" {
  description = "OBS 报告桶名（全局唯一）。仅在 enable_obs=true 时创建。"
  type        = string
  default     = "central-patch-reports"
}

variable "enable_smn" {
  description = "是否创建 SMN 主题用于补丁运行结果通知。"
  type        = bool
  default     = true
}

variable "smn_subscription_emails" {
  description = "SMN 邮件订阅地址列表（启用 SMN 后生效；订阅需收件人点击确认邮件才生效）。"
  type        = list(string)
  default     = []
}
