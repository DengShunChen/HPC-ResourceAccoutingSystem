"""cluster_config：多區段 / 舊版 [cluster] / resolve 順序。"""
from __future__ import annotations

from pathlib import Path

from cluster_config import (
    apply_deployment_env_overrides,
    cluster_id_from_hostname,
    get_cluster_capacity,
    list_cluster_profiles,
    read_config,
    resolve_cluster_section,
    section_to_profile_id,
)
from configparser import ConfigParser


def _cfg_from_ini(text: str):
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write(text)
        p = f.name
    try:
        return read_config(p)
    finally:
        Path(p).unlink(missing_ok=True)


def test_list_profiles_multi_and_sort():
    cfg = _cfg_from_ini(
        """
[cluster_h6c2]
cluster_name = B
[cluster_h6c1]
cluster_name = A
"""
    )
    assert list_cluster_profiles(cfg) == [("h6c1", "A"), ("h6c2", "B")]


def test_list_profiles_legacy_cluster_only():
    cfg = _cfg_from_ini(
        """
[cluster]
cluster_name = Legacy
total_cpu_nodes = 10
"""
    )
    assert list_cluster_profiles(cfg) == [("default", "Legacy")]


def test_resolve_order_env_over_active(tmp_path, monkeypatch):
    ini = tmp_path / "c.ini"
    ini.write_text(
        """
[clusters]
active_cluster = h6c1
[cluster_h6c1]
cluster_name = a1
[cluster_h6c2]
cluster_name = a2
""",
        encoding="utf-8",
    )
    cfg = read_config(str(ini))
    monkeypatch.setenv("CLUSTER_ID", "h6c2")
    try:
        assert resolve_cluster_section(cfg) == "cluster_h6c2"
    finally:
        monkeypatch.delenv("CLUSTER_ID", raising=False)


def test_resolve_active_cluster_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CLUSTER_ID", raising=False)
    ini = tmp_path / "c.ini"
    ini.write_text(
        """
[clusters]
active_cluster = h6c2
[cluster_h6c1]
cluster_name = a1
[cluster_h6c2]
cluster_name = a2
""",
        encoding="utf-8",
    )
    cfg = read_config(str(ini))
    assert resolve_cluster_section(cfg) == "cluster_h6c2"


def test_section_to_profile_id():
    assert section_to_profile_id("cluster") == "default"
    assert section_to_profile_id("cluster_h6c1") == "h6c1"


def test_get_cluster_capacity_missing_section():
    cfg = _cfg_from_ini("[cluster_h6c1]\ncluster_name = X\n")
    name, cpu, gpu = get_cluster_capacity(cfg, section="cluster_nope")
    assert name == "HPC" and cpu == 1 and gpu == 1


def test_cluster_id_from_hostname_multiple_aliases():
    cfg = _cfg_from_ini(
        """
[cluster_h6c1]
host_aliases = h6dm1, h6ln1
[cluster_h6c2]
host_aliases = h6dm2, h6ln2
"""
    )
    assert cluster_id_from_hostname(cfg, "h6ln1") == "h6c1"
    assert cluster_id_from_hostname(cfg, "H6DM2") == "h6c2"
    assert cluster_id_from_hostname(cfg, "other") is None


def test_cluster_id_from_hostname_fnmatch():
    cfg = _cfg_from_ini(
        """
[cluster_h6c1]
host_aliases = h6dm*, h6ln*
"""
    )
    assert cluster_id_from_hostname(cfg, "h6dm12") == "h6c1"
    # fnmatch：h6ln* 亦匹配「僅 h6ln」（* 可為空字串）
    assert cluster_id_from_hostname(cfg, "h6ln") == "h6c1"
    assert cluster_id_from_hostname(cfg, "h6xx") is None


def test_resolve_hostname_before_active_cluster(tmp_path, monkeypatch):
    monkeypatch.delenv("CLUSTER_ID", raising=False)
    ini = tmp_path / "c.ini"
    ini.write_text(
        """
[clusters]
active_cluster = h6c2
[cluster_h6c1]
host_aliases = h6dm1
cluster_name = a1
[cluster_h6c2]
host_aliases = h6dm2
cluster_name = a2
""",
        encoding="utf-8",
    )
    cfg = read_config(str(ini))
    assert cluster_id_from_hostname(cfg, "h6dm1") == "h6c1"
    # 模擬跑在 h6dm1：無 CLUSTER_ID → hostname 優先於 active_cluster=h6c2
    monkeypatch.setattr(
        "cluster_config._short_hostname",
        lambda: "h6dm1",
    )
    assert resolve_cluster_section(cfg) == "cluster_h6c1"


def test_log_directory_path_env_override(monkeypatch):
    monkeypatch.setenv("LOG_DIRECTORY_PATH", "/env/logs/here")
    cfg = ConfigParser()
    cfg.read_dict({"data": {"log_directory_path": "/ini/placeholder"}})
    apply_deployment_env_overrides(cfg)
    assert cfg.get("data", "log_directory_path") == "/env/logs/here"


def test_read_config_respects_hpc_accounting_config(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_DIRECTORY_PATH", raising=False)
    ini = tmp_path / "custom.ini"
    ini.write_text(
        "[data]\nlog_directory_path = /from_custom_ini\n[log_schema]\ncolumn_names = A\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HPC_ACCOUNTING_CONFIG", str(ini))
    cfg = read_config()
    assert cfg.get("data", "log_directory_path") == "/from_custom_ini"


def test_cluster_id_env_overrides_hostname(tmp_path, monkeypatch):
    monkeypatch.setattr("cluster_config._short_hostname", lambda: "h6dm1")
    monkeypatch.setenv("CLUSTER_ID", "h6c2")
    ini = tmp_path / "c.ini"
    ini.write_text(
        """
[cluster_h6c1]
host_aliases = h6dm1
[cluster_h6c2]
host_aliases = h6dm2
""",
        encoding="utf-8",
    )
    cfg = read_config(str(ini))
    assert resolve_cluster_section(cfg) == "cluster_h6c2"
    monkeypatch.delenv("CLUSTER_ID", raising=False)
    assert resolve_cluster_section(cfg) == "cluster_h6c1"
