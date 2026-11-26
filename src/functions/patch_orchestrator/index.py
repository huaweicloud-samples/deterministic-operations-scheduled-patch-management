# -*- coding: utf-8 -*-
"""
集中式多账号 / 多区域补丁编排函数（FunctionGraph）
====================================================

编排流程：
  FunctionGraph TIMER 触发器按 Cron 唤起本函数 → 读取环境变量中的目标区域/账号/操作
  → 逐区域构建 HSS 客户端，调用 HSS 在各区域执行漏洞扫描或修复
  → 可选地将运行汇总写入 OBS、推送 SMN 通知

凭据：运行期由 FunctionGraph 委托（agency）经 context 注入，不落盘。
SDK 依赖（huaweicloudsdkcore / hss / smn）已随 zip 打包；obs 为 FGS 内置，勿自带。
"""
import os
import json
import traceback

# 代码版本号：写进入口日志 + 返回体，便于确认线上跑的是哪一版（避免旧 zip 未生效却反复 500）。
CODE_VERSION = "2026-08-12c-filter-unprotected"

# 入口日志先于任何 SDK import 打印：即便后续 import 失败也能在日志看到入口。
print(f"=== PATCH ORCHESTRATOR HANDLER ENTRY (code_version={CODE_VERSION}) ===", flush=True)


def _get_credentials(context):
    """从 FunctionGraph context 取委托临时凭证。"""
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    ak = sk = token = None
    if context is not None:
        try:
            ak = context.getSecurityAccessKey()
            sk = context.getSecuritySecretKey()
            token = context.getSecurityToken()
        except Exception:
            pass
    project_id = os.environ.get("HW_PROJECT_ID")
    if not ak or not sk:
        raise RuntimeError("函数未绑定委托或委托无凭证；请确认 agency 已挂 HSS Administrator 等权限。")
    return BasicCredentials(ak, sk, project_id).with_security_token(token)


def _cross_account_credentials(mgmt_creds, agency_name, target_account_id, region):
    """跨账号凭证交换（扩展能力）。

    华为云 HSS 按账号隔离，管理账号无法用自身凭证直接调目标账号 HSS。
    需在目标账号内部署 infra/modules/target-account-agency，再用 IAM agency token 交换
    获取目标账号的临时凭证。该路径依赖 huaweicloudsdkiam（未默认打包），且不同 SDK 版本
    字段名有差异，属『需按实际版本校验』的扩展实现；失败时调整为跳过该账号，不阻断整体。
    """
    try:
        from huaweicloudsdkiam.v3 import IamClient, IamRegion
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
    except ImportError:
        print("WARN: huaweicloudsdkiam 未打包，跨账号能力不可用；"
              "请在 infra/build_function.py 的 BUNDLE_PACKAGES 加入 huaweicloudsdkiam 后重试。", flush=True)
        return None
    try:
        iam = (IamClient.new_builder()
               .with_credentials(mgmt_creds)
               .with_region(IamRegion.CN_NORTH_4)
               .build())
        # 注：以下 agency token 交换请求体字段名需按 huaweicloudsdkiam 实际版本校验。
        # 交互为：用管理账号凭证，向 IAM 申请「以目标账号委托」作用域到目标账号项目的临时 token。
        from huaweicloudsdkiam.v3 import KeystoneCreateAgencyTokenRequest
        req = KeystoneCreateAgencyTokenRequest()
        # req.body = {...}  # 见 API Explorer: POST /v3.0/OS-AGENCY/tokens
        resp = iam.keystone_create_agency_token(req)
        tok = getattr(resp, "token", None)
        if not tok:
            print("WARN: 跨账号 token 交换未返回 token（需校验请求体），跳过该账号。", flush=True)
            return None
        return BasicCredentials(None, None, target_account_id).with_security_token(tok)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 跨账号凭证交换失败，跳过该账号: {e}", flush=True)
        return None


def _collect_hosts(client, enterprise_project_id):
    """分页收集企业项目内的防护主机，返回 list[dict]{host_id, agent_id, host_name}。"""
    hosts = []
    offset = 0
    limit = 50
    while True:
        page = client.list_hosts(enterprise_project_id=enterprise_project_id,
                                 limit=limit, offset=offset)
        if not page:
            break
        hosts.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return hosts


def _write_obs_report(region, ak, sk, token, bucket, key, payload):
    """将运行汇总写入 OBS（FGS 内置 obs，勿自带）。"""
    from obs import ObsClient
    oc = ObsClient(
        access_key_id=ak,
        secret_access_key=sk,
        security_token=token,
        server=f"https://obs.{region}.myhuaweicloud.com",
    )
    try:
        r = oc.putObject(bucket, key, json.dumps(payload, ensure_ascii=False, indent=2))
        if r.status < 300:
            print(f">> 报告已写入 obs://{bucket}/{key}", flush=True)
        else:
            print(f"WARN: OBS 写入失败 status={r.status}", flush=True)
    finally:
        oc.close()


def _publish_smn(region, creds, topic_urn, text):
    """推送补丁运行汇总到 SMN 主题（message 放 body）。"""
    from huaweicloudsdksmn.v2 import SmnClient, PublishMessageRequest, PublishMessageRequestBody
    from huaweicloudsdksmn.v2.region.smn_region import SmnRegion
    client = (SmnClient.new_builder()
              .with_credentials(creds)
              .with_region(SmnRegion.value_of(region))
              .build())
    body = PublishMessageRequestBody(subject="集中补丁运行汇总", message=text)
    req = PublishMessageRequest()
    req.topic_urn = topic_urn
    req.body = body
    client.publish_message(req)
    print(">> 已推送 SMN 通知", flush=True)


def handler(event, context):
    try:
        env = os.environ
        target_regions = [r for r in env.get("TARGET_REGIONS", "").split(",") if r]
        target_accounts = [a for a in env.get("TARGET_ACCOUNTS", "").split(",") if a]
        operation = env.get("OPERATION", "Scan")
        reboot_option = env.get("REBOOT_OPTION", "NoReboot")
        eps = env.get("ENTERPRISE_PROJECT_ID", "0")
        enable_obs = env.get("ENABLE_OBS", "false") == "true"
        enable_smn = env.get("ENABLE_SMN", "false") == "true"
        obs_bucket = env.get("OBS_BUCKET", "")
        smn_topic = env.get("SMN_TOPIC_URN", "")

        if not target_regions:
            target_regions = [os.environ.get("HW_REGION", "cn-north-4")]

        mgmt_creds = _get_credentials(context)
        summary = {"code_version": CODE_VERSION, "operation": operation,
                   "regions": [], "errors": []}

        # 账号维度：空=仅管理账号；非空=逐账号跨账号调用
        accounts = target_accounts if target_accounts else [None]
        for account in accounts:
            ac_creds = mgmt_creds
            if account:
                ac_creds = _cross_account_credentials(mgmt_creds,
                                                      env.get("EXECUTION_ROLE_NAME", ""),
                                                      account, target_regions[0])
                if ac_creds is None:
                    summary["errors"].append(f"账号 {account} 跨账号凭证获取失败，已跳过")
                    continue

            for region in target_regions:
                from hss_patch_client import HssPatchClient
                client = HssPatchClient(region, ac_creds)
                hosts = _collect_hosts(client, eps)
                region_result = {"region": region, "account": account or "self",
                                 "host_count": len(hosts), "action": operation}

                if not hosts:
                    region_result["note"] = "无防护主机（请先在目标范围开启 HSS 防护）"
                    summary["regions"].append(region_result)
                    continue

                if operation == "Scan":
                    # 仅对「已开启防护且 agent 在线」的主机发起扫描；其余如实跳过（HSS.0010 根因：
                    # 防护关闭/离线的主机调 create_vulnerability_scan_task 会被拒）。
                    scannable, skipped = [], []
                    for h in hosts:
                        if h.get("agent_id") and HssPatchClient.is_scannable(h):
                            scannable.append(h)
                        else:
                            reasons = []
                            if not h.get("agent_id"):
                                reasons.append("无 agent_id")
                            if h.get("protect_status") != "open":
                                reasons.append(f"防护状态={h.get('protect_status')}")
                            if h.get("agent_status") != "online":
                                reasons.append(f"agent状态={h.get('agent_status')}")
                            skipped.append({"host_id": h.get("host_id"),
                                            "host_name": h.get("host_name"),
                                            "reason": "、".join(reasons) or "未知"})
                    agent_ids = [h["agent_id"] for h in scannable]
                    if agent_ids:
                        task_id = client.scan_vulnerabilities(agent_ids, vul_type="linux")
                        region_result["scan_task_id"] = task_id
                    region_result["scanned"] = len(agent_ids)
                    region_result["host_total"] = len(hosts)
                    region_result["scannable"] = len(scannable)
                    if skipped:
                        region_result["skipped"] = skipped
                    if not agent_ids:
                        region_result["note"] = ("无可扫描主机（需 HSS 防护已开启且 agent 在线；"
                                                "漏洞扫描另需企业版及以上防护）")
                else:
                    # Install：逐主机查漏洞并修复（HSS 按漏洞维度修复）
                    reboot = "yes" if reboot_option == "RebootIfNeeded" else "no"
                    fixed_total, vul_total = 0, 0
                    for h in hosts:
                        if not HssPatchClient.is_scannable(h):
                            continue  # 防护关闭/离线的主机无法修复，跳过（避免 HSS.0010）
                        hid = h["host_id"]
                        try:
                            vul_ids = client.list_host_vulnerabilities(
                                hid, enterprise_project_id=eps, vul_type="linux")
                            client.fix_vulnerabilities(
                                hid, vul_ids=vul_ids or None,
                                vul_type="linux", reboot=reboot)
                            fixed_total += 1
                            vul_total += len(vul_ids)
                        except Exception as e:  # noqa: BLE001
                            region_result.setdefault("host_errors", []).append(
                                {"host_id": hid, "error": str(e)})
                    region_result["fixed_hosts"] = fixed_total
                    region_result["vul_count"] = vul_total

                summary["regions"].append(region_result)
                print(f">> region={region} account={account or 'self'} "
                      f"hosts={len(hosts)} op={operation}", flush=True)

        # 可选：汇总报告落地 OBS（便于审计）
        if enable_obs and obs_bucket:
            ak = sk = token = None
            if context is not None:
                try:
                    ak = context.getSecurityAccessKey()
                    sk = context.getSecuritySecretKey()
                    token = context.getSecurityToken()
                except Exception:
                    pass
            ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y%m%d%H%M%S")
            key = f"patch-reports/{operation}-{ts}.json"
            _write_obs_report(target_regions[0], ak, sk, token, obs_bucket, key, summary)

        # 可选：SMN 通知
        if enable_smn and smn_topic:
            _publish_smn(target_regions[0], mgmt_creds, smn_topic, json.dumps(summary, ensure_ascii=False))

        print("=== PATCH ORCHESTRATOR DONE ===", flush=True)
        return {"statusCode": 200, "body": json.dumps(summary, ensure_ascii=False)}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        # 错误体也带版本号，便于确认线上跑的是哪版（无需靠 traceback 行号猜）。
        return {"statusCode": 500, "body": json.dumps(
            {"code_version": CODE_VERSION, "error": str(e)})}


if __name__ == "__main__":
    # 本地模拟 TIMER 事件（无 context）
    print(json.dumps(handler({}, None), ensure_ascii=False, indent=2))
