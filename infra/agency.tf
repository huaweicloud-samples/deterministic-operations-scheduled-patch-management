# ============================================================================
# IAM 委托（Agency）
# ----------------------------------------------------------------------------
# 本方案的编排函数经 IAM 委托访问 HSS / OBS / SMN。
# 华为云中「函数经委托访问其他服务」通过 agency 实现；委托服务名 op_svc_cff = FunctionGraph。
# 角色作用域：HSS/OBS 为全局服务（AX → domain_roles），SMN 为区域服务（XA → project_role）。
# 角色作用域选错（AX/XA）会导致 API 返回成功但权限不生效，请按服务级别配置。
# ============================================================================

resource "huaweicloud_identity_agency" "patch_orchestrator" {
  name                   = "${var.project_name}-fgs-agency"
  description            = "授予 FunctionGraph 编排函数调用 HSS（漏洞扫描/修复）、OBS（报告落地）、SMN（结果通知）的权限。"
  duration               = "FOREVER"
  delegated_service_name = "op_svc_cff" # FunctionGraph 的 IAM 服务主体

  # 全局服务级角色（AX）
  domain_roles = [
    "HSS Administrator", # 主机安全（漏洞管理）全局管理员
    "OBS OperateAccess", # OBS 数据面由桶策略放行，此处为控制面权限
  ]

  # 区域服务级角色（XA）
  project_role {
    project = var.region
    # HSS 主机类动作（hss:host:*）为项目级作用域，domain 角色无法覆盖，必须同时挂项目级角色
    roles   = ["HSS Administrator", "SMN FullAccess"]
  }
}
