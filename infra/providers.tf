# ============================================================================
# 华为云 Provider 与数据源
# ============================================================================
# 认证从环境变量读取（不硬编码）：
#   export HW_ACCESS_KEY="<AK>"
#   export HW_SECRET_KEY="<SK>"
#   export HW_REGION_NAME="cn-north-4"（可选，默认取 var.region）
# 函数运行期凭证由 FunctionGraph 委托（agency）经 context 注入，不落地。

terraform {
  required_version = ">= 1.5"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = "~> 1.70"
    }
  }

  # 生产环境建议将状态文件存入 OBS（取消注释并填桶名）
  # backend "s3" {
  #   endpoint = "https://obs.cn-north-4.myhuaweicloud.com"
  #   bucket   = "your-tfstate-bucket"
  #   key      = "central-patch/terraform.tfstate"
  #   region   = "cn-north-4"
  # }
  backend "local" {}
}

provider "huaweicloud" {
  region = var.region
}

# 当前账号主域 ID（用于 OBS 桶策略 Principal 与多账号场景）
data "huaweicloud_account" "current" {}
