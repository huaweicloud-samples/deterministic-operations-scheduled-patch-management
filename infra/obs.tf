# ============================================================================
# OBS 报告桶
# ----------------------------------------------------------------------------
# 每次补丁运行汇总报告（JSON）落地 OBS，作为可审计的产物。
#
# OBS 数据面（Get/Put/DeleteObject）不认 agency/IAM 临时凭证，
# 必须靠桶策略放行。Principal 用 "domain/<domain_id>:agency/<agency_name>"。
# 不开版本控制，避免调试桶销毁困难。
# ============================================================================

resource "huaweicloud_obs_bucket" "patch_reports" {
  count         = var.enable_obs ? 1 : 0
  bucket        = var.obs_bucket_name
  acl           = "private"
  # 调试/报告桶：函数会写入对象；设为 true 以便 `terraform destroy` 自动清空并删除，
  # 避免「桶非空导致销毁失败」（生产重要数据桶勿开）。
  force_destroy = true
  versioning    = false

  tags = {
    project = var.project_name
  }
}

resource "huaweicloud_obs_bucket_policy" "patch_reports" {
  count  = var.enable_obs ? 1 : 0
  bucket = huaweicloud_obs_bucket.patch_reports[0].bucket

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowFgsAgencyReadWrite"
        Effect    = "Allow"
        # OBS 桶策略 Principal 必须是对象 {ID:[...]}，不是裸字符串
        Principal = {
          ID = ["domain/${data.huaweicloud_account.current.id}:agency/${huaweicloud_identity_agency.patch_orchestrator.name}"]
        }
        # OBS 桶策略的 action 字段为裸动作名（无 obs: 前缀）
        Action = [
          "GetObject",
          "PutObject",
          "DeleteObject",
          "ListBucket",
        ]
        # OBS 桶策略 Resource 直接用桶名（非 obs:*:*:object: ARN）
        Resource = [
          "${huaweicloud_obs_bucket.patch_reports[0].bucket}",
          "${huaweicloud_obs_bucket.patch_reports[0].bucket}/*",
        ]
      }
    ]
  })
}
