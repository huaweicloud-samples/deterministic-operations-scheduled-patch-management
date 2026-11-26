# ============================================================================
# 跨账号委托（部署在「目标账号」内）
# ----------------------------------------------------------------------------
# 场景：集中式补丁需要管理账号的编排函数跨账号调用目标账号的 HSS。
# 华为云 HSS 按账号隔离，管理账号无法用自身凭证直接调目标账号 HSS，
# 必须在每个目标账号内创建「信任管理账号」的委托，并授予 HSS 权限。
#
# 用法（在每个目标账号的 provider 下）：
#   module "target_account_agency" {
#     source                     = "./modules/target-account-agency"
#     management_account_domain_id = "<管理账号主域ID>"
#     project_name               = "central-patch"
#   }
#
# 随后管理账号函数通过 IAM agency token 交换获取目标账号临时凭证
# （见 src/functions/patch_orchestrator/index.py 的跨账号分支）。
# ============================================================================

variable "management_account_domain_id" {
  description = "管理账号的主域 ID（被信任方）。在管理账号执行 `data.huaweicloud_account.current.id` 获取。"
  type        = string
}

variable "project_name" {
  type    = string
  default = "central-patch"
}

variable "target_region" {
  description = "目标账号内部署 HSS 防护的区域（HSS 为区域服务，委托授予该区域的项目角色）。"
  type        = string
  default     = "cn-north-4"
}

resource "huaweicloud_identity_agency" "cross_account" {
  name                   = "${var.project_name}-mgmt-assume"
  description            = "允许管理账号的 FunctionGraph 编排函数跨账号调用本账号 HSS 执行集中补丁。"
  duration               = "FOREVER"
  delegated_domain_name = var.management_account_domain_id

  domain_roles = ["HSS Administrator"]
}

output "cross_account_agency_name" {
  value = huaweicloud_identity_agency.cross_account.name
}
