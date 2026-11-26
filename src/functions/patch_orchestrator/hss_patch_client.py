# -*- coding: utf-8 -*-
"""
HSS 漏洞扫描/修复适配器（封装华为云 HSS Python SDK，huaweicloudsdkhss 3.1.209）
============================================================================

提供 HSS 漏洞管理能力在多区域主机上的统一封装：
  - 主机枚举：按企业项目列出已开启 HSS 防护的主机及 agent 状态
  - 单主机漏洞枚举：列出指定主机的 CVE 漏洞清单
  - 触发漏洞扫描：对指定主机发起一轮漏洞扫描
  - 修复漏洞：按漏洞维度修复（支持按需重启）

> ⚠️ SDK 真实 API 说明（重要）：
> 本适配器最初假设的 `list_hosts` / `scan_vulnerabilities` / `fix_vulnerabilities`
> 在官方 huaweicloudsdkhss 3.1.209（PyPI 最新）中**均不存在**。已按真实 SDK 表面重写：
>   - 主机枚举        -> ``list_host_status``（返回 ``Host``，含 host_id / agent_id）
>   - 单主机漏洞枚举  -> ``list_host_vuls``（返回 ``HostVulInfo``，含 vul_id）
>   - 触发漏洞扫描    -> ``create_vulnerability_scan_task`` + ``ManualVulScanRequestInfo``
>   - 修复漏洞        -> SDK 无封装方法，改用 ``HssClient.do_http_request`` 调用
>                       文档化修复端点 POST /v5/{project_id}/vulnerabilities/hosts/{host_id}/fix
>
> 以下字段取值（修复端点 body 字段名）已标 ``# 待校验``；manual_scan_type / range_type 已于
> cn-north-4 真实联调确认（specific_host + linux_vul 列表，原 "host"/"all" 会触发 HSS.0002）。
> 修复端点（POST .../vulnerabilities/hosts/{host_id}/fix）仍待联调。
"""
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkhss.v5 import (
    HssClient,
    ListHostStatusRequest,
    ListHostVulsRequest,
    CreateVulnerabilityScanTaskRequest,
    ManualVulScanRequestInfo,
)
# HSS 区域枚举不在 v5 顶层导出，需从 region 子模块的 hss_region 导入（package __init__ 为空）。
from huaweicloudsdkhss.v5.region.hss_region import HssRegion

import json


def _client(region, credentials):
    return (
        HssClient.new_builder()
        .with_credentials(credentials)
        .with_region(HssRegion.value_of(region))
        .build()
    )


class HssPatchClient:
    """围绕 HSS 漏洞管理的最小封装。"""

    def __init__(self, region, credentials, project_id=None):
        self.region = region
        self._creds = credentials
        # project_id 用于修复端点的路径拼接；优先取凭据中的 project_id。
        self._project_id = project_id or getattr(credentials, "project_id", None)
        self._cli = _client(region, credentials)

    def list_hosts(self, enterprise_project_id="0", limit=50, offset=0):
        """列出企业项目范围内的防护主机。

        返回 list[dict]，每项含 host_id / agent_id / host_name / protect_status / agent_status。
        HSS 扫描接口按 agent_id 维度，修复接口按 host_id 维度，二者都保留。
        protect_status='open' 且 agent_status='online' 才是可扫描/修复的目标（见 index.py 过滤逻辑）。
        """
        req = ListHostStatusRequest()
        req.enterprise_project_id = enterprise_project_id
        req.limit = limit
        req.offset = offset
        resp = self._cli.list_host_status(req)
        hosts = getattr(resp, "data_list", None) or []
        out = []
        for h in hosts:
            hid = getattr(h, "host_id", None)
            if not hid:
                continue
            out.append({
                "host_id": hid,
                "agent_id": getattr(h, "agent_id", None),
                "host_name": getattr(h, "host_name", None),
                "protect_status": getattr(h, "protect_status", None),
                "agent_status": getattr(h, "agent_status", None),
            })
        return out

    @staticmethod
    def is_scannable(host):
        """判断主机是否可扫描/修复：必须已开启 HSS 防护且 agent 在线。

        protect_status='open' + agent_status='online' 才满足；否则 HSS 会拒绝对
        create_vulnerability_scan_task / fix 的调用（典型报错 HSS.0010 Access denied /
        HSS.0002）。HSS 漏洞扫描功能还要求主机开启企业版及以上防护（基础版不含）。
        """
        return (host.get("protect_status") == "open"
                and host.get("agent_status") == "online")

    def list_host_vulnerabilities(self, host_id, enterprise_project_id="0",
                                  vul_type="linux", limit=50, offset=0):
        """查询单台主机的漏洞列表，返回 vul_id 列表。"""
        req = ListHostVulsRequest()
        req.enterprise_project_id = enterprise_project_id
        req.host_id = host_id
        req.type = vul_type
        req.limit = limit
        req.offset = offset
        resp = self._cli.list_host_vuls(req)
        items = getattr(resp, "data_list", None) or []
        return [getattr(v, "vul_id", None) for v in items if getattr(v, "vul_id", None)]

    def scan_vulnerabilities(self, agent_ids, vul_type="linux"):
        """手动触发漏洞扫描。

        agent_ids: 主机 agent_id 列表（来自 list_hosts 的 agent_id）。
        range_type: specific_host=扫描指定主机（配合 agent_id_list）；
                     all_host=扫描全部主机（无需 agent_id_list）。
        manual_scan_type: 漏洞类型列表（必填，list[str]，1-200 项），取值同 HSS 漏洞类型枚举
                         linux_vul / windows_vul / web_cms / app_vul / urgent_vul。
                         经验证：原 "host"/"all" 均为非法值，会触发 HSS.0002 请求解析失败。
        """
        _type_map = {"linux": "linux_vul", "windows": "windows_vul"}
        scan_type = _type_map.get(vul_type, vul_type)
        body = ManualVulScanRequestInfo()
        body.range_type = "specific_host"
        body.agent_id_list = list(agent_ids)
        body.manual_scan_type = [scan_type]
        body.batch_flag = True
        req = CreateVulnerabilityScanTaskRequest()
        req.body = body
        # 探针：真实发出前打印请求体，便于在日志里核对字段与服务版本（HSS.0002 排查用）。
        print(">> HSS create_vulnerability_scan_task body="
              + json.dumps(body.to_dict(), ensure_ascii=False), flush=True)
        try:
            resp = self._cli.create_vulnerability_scan_task(req)
        except Exception as e:  # noqa: BLE001
            # 把诊断信息塞进异常，便于同步调用返回体直接看到（无需查日志）。
            diag = {
                "agent_count": len(body.agent_id_list or []),
                "agent_sample": (body.agent_id_list or [])[:2],
                "project_id": self._project_id,
                "body": body.to_dict(),
                "orig": str(e),
            }
            raise RuntimeError("HSS_SCAN_DIAG " + json.dumps(diag, ensure_ascii=False)) from e
        return getattr(resp, "task_id", None)

    def fix_vulnerabilities(self, host_id, vul_ids=None, vul_type="linux", reboot="no"):
        """修复漏洞。

        SDK 未封装修复方法，故复用 HssClient 内置的 do_http_request 调用文档化端点：
            POST /v5/{project_id}/vulnerabilities/hosts/{host_id}/fix
        body 字段（type / vul_id / reboot）待 API Explorer 校验。
        vul_ids 为空时修复该主机全部可修复漏洞（按端点默认行为）。
        """
        if not self._project_id:
            raise RuntimeError("修复漏洞需要 project_id（请确认凭据/环境变量 HW_PROJECT_ID 已设置）。")
        path = f"/v5/{self._project_id}/vulnerabilities/hosts/{host_id}/fix"
        payload = {"type": vul_type, "reboot": reboot}
        if vul_ids:
            payload["vul_id"] = list(vul_ids)
        r = self._cli.do_http_request(
            "POST", path,
            body=json.dumps(payload),
            header_params={"Content-Type": "application/json"},
        )
        if getattr(r, "status", 0) >= 300:
            raise RuntimeError(f"HSS 修复请求失败 status={getattr(r, 'status', '?')}")
        return getattr(r, "status", 0)
