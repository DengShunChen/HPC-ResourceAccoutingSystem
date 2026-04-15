"""
讀取 config.ini 的叢集容量設定。

支援：
- 多區段 `[cluster_<id>]`（例如 cluster_h6c1、cluster_h6c2），並以 `[clusters] active_cluster` 或環境變數
  `CLUSTER_ID` 選擇預設。
- 選用 `host_aliases`（逗號分隔）：以本機 hostname（短名，FQDN 取第一段）對應叢集；可寫多個別名
  （例如 h6dm1、h6ln1 都對應 h6c1）。含 `*`、`?` 時依 fnmatch 比對。
- 舊版單一 `[cluster]`（無任何 `cluster_*` 區段時仍可用）。
- 部署：`HPC_ACCOUNTING_CONFIG` 指定 ini 路徑；`LOG_DIRECTORY_PATH` 覆寫 `[data] log_directory_path`（可不手改 ini）。
"""
from __future__ import annotations

import fnmatch
import os
import re
import socket
from configparser import ConfigParser
from typing import List, Tuple

_CLUSTER_SECTION = re.compile(r"^cluster_(.+)$")


def apply_deployment_env_overrides(cfg: ConfigParser) -> None:
    """
    以環境變數覆寫 ini，便於 systemd / CI 只注入變數、同一套 repo 直接上線。
    """
    log_dir = (os.getenv("LOG_DIRECTORY_PATH") or "").strip()
    if log_dir:
        if not cfg.has_section("data"):
            cfg.add_section("data")
        cfg.set("data", "log_directory_path", log_dir)


def read_config(
    path: str | None = None, *, apply_env_overrides: bool = True
) -> ConfigParser:
    """
    讀取應用程式 ini。`path` 為 None 或空字串時依序：`HPC_ACCOUNTING_CONFIG` → `config.ini`。
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    cfg_path = (path or "").strip() or (os.getenv("HPC_ACCOUNTING_CONFIG") or "").strip() or "config.ini"
    cfg = ConfigParser()
    cfg.read(cfg_path)
    if apply_env_overrides:
        apply_deployment_env_overrides(cfg)
    return cfg


def list_cluster_profiles(config: ConfigParser) -> List[Tuple[str, str]]:
    """回傳 [(cluster_id, cluster_name), ...] 供 UI；cluster_id 為區段後綴（如 h6c1）。"""
    profiles: List[Tuple[str, str]] = []
    for sec in config.sections():
        m = _CLUSTER_SECTION.match(sec)
        if not m:
            continue
        cid = m.group(1)
        if not cid:
            continue
        name = config.get(sec, "cluster_name", fallback=cid)
        profiles.append((cid, name))
    profiles.sort(key=lambda x: x[0])
    if profiles:
        return profiles
    if config.has_section("cluster"):
        nm = config.get("cluster", "cluster_name", fallback="HPC")
        return [("default", nm)]
    return []


def section_to_profile_id(section: str) -> str | None:
    """`cluster_h6c1` → h6c1；舊版 `cluster` → default。"""
    if section == "cluster":
        return "default"
    m = _CLUSTER_SECTION.match(section)
    return m.group(1) if m else None


def _short_hostname() -> str:
    return (socket.gethostname() or "").split(".", 1)[0].strip()


def _host_alias_patterns(config: ConfigParser, section: str) -> List[str]:
    raw = config.get(section, "host_aliases", fallback="").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def cluster_id_from_hostname(config: ConfigParser, hostname: str | None = None) -> str | None:
    """
    若 hostname（預設本機短名）符合某個 [cluster_<id>] 的 host_aliases，回傳該 id；否則 None。
    比對：無萬用字元時大小寫不敏感 exact；含 * ? [ 時對短名做 fnmatch（大小寫不敏感）。
    多區段皆符合時，依區段名稱字串排序後取第一個（穩定、可預期）。
    """
    hn = (hostname if hostname is not None else _short_hostname()).strip()
    if not hn:
        return None
    hn_fold = hn.casefold()
    candidates: List[Tuple[str, str]] = []
    for sec in sorted(config.sections()):
        m = _CLUSTER_SECTION.match(sec)
        if not m or not m.group(1):
            continue
        cid = m.group(1)
        for pat in _host_alias_patterns(config, sec):
            p = pat.strip()
            if not p:
                continue
            if any(ch in p for ch in "*?["):
                if fnmatch.fnmatch(hn_fold, p.casefold()):
                    candidates.append((sec, cid))
                    break
            elif hn_fold == p.casefold():
                candidates.append((sec, cid))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def resolve_cluster_section(config: ConfigParser, cluster_id: str | None = None) -> str:
    """
    回傳要讀取的 ini 區段名稱，例如 `cluster_h6c1` 或舊版 `cluster`。
    cluster_id 若為 None，依序：環境 CLUSTER_ID → host_aliases 與本機 hostname 相符者
    → ini active_cluster → 第一個 cluster_* → cluster。
    """
    if cluster_id == "default" and config.has_section("cluster"):
        return "cluster"

    def _has_cluster_id(cid: str) -> bool:
        return bool(cid) and config.has_section(f"cluster_{cid}")

    if cluster_id and _has_cluster_id(cluster_id):
        return f"cluster_{cluster_id}"

    env_id = (os.getenv("CLUSTER_ID") or "").strip()
    if env_id and _has_cluster_id(env_id):
        return f"cluster_{env_id}"

    hid = cluster_id_from_hostname(config)
    if hid and _has_cluster_id(hid):
        return f"cluster_{hid}"

    if config.has_section("clusters"):
        active = config.get("clusters", "active_cluster", fallback="").strip()
        if active and _has_cluster_id(active):
            return f"cluster_{active}"

    for sec in sorted(config.sections()):
        m = _CLUSTER_SECTION.match(sec)
        if m and m.group(1):
            return sec

    if config.has_section("cluster"):
        return "cluster"

    return "cluster"


def get_cluster_capacity(
    config: ConfigParser, section: str | None = None, cluster_id: str | None = None
) -> Tuple[str, int, int]:
    """(cluster_name, total_cpu_nodes, total_gpu_cores)。"""
    sec = section if section else resolve_cluster_section(config, cluster_id)
    if not config.has_section(sec):
        return "HPC", 1, 1
    name = config.get(sec, "cluster_name", fallback="HPC")
    cpu = config.getint(sec, "total_cpu_nodes", fallback=1)
    gpu = config.getint(sec, "total_gpu_cores", fallback=1)
    return name, cpu, gpu
