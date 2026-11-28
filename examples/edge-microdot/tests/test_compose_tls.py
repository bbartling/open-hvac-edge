"""Static checks for the Caddy / compose wiring (no Docker needed)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def _caddy() -> str:
    return (ROOT / "Caddyfile").read_text(encoding="utf-8")


def test_caddyfile_asks_before_on_demand_and_sets_csp():
    text = _caddy()
    assert "admin off" in text
    assert "ask http://127.0.0.1:8080/tls/allow" in text
    assert "on_demand" in text
    assert "{$EDGE_TLS_HOST::443}" in text
    assert "bind {$EDGE_TLS_BIND:0.0.0.0}" in text
    assert "Content-Security-Policy" in text
    assert "script-src 'self'" in text
    assert "wasm-unsafe-eval" not in text
    assert "reverse_proxy 127.0.0.1:8080" in text


def test_caddyfile_has_no_hard_coded_lan_ips():
    text = _caddy()
    ips = re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text)
    assert set(ips) <= {"127.0.0.1", "0.0.0.0"}


def test_niagara_port_is_loopback_only_and_container_listens_on_all_interfaces():
    svc = _compose()["services"]["edge-niagara"]
    assert svc["ports"] == ["127.0.0.1:8080:8080"]
    cmd = svc["command"]
    assert cmd[cmd.index("--host") + 1] == "0.0.0.0"


def test_bacnet_service_stays_on_loopback_with_host_network():
    svc = _compose()["services"]["edge-bacnet"]
    assert svc["network_mode"] == "host"
    cmd = svc["command"]
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"


def test_caddy_receives_tls_host_with_catch_all_default():
    env = _compose()["services"]["caddy"]["environment"]
    assert env["EDGE_TLS_HOST"] == "${EDGE_TLS_HOST:-:443}"
    assert env["EDGE_TLS_BIND"] == "${EDGE_TLS_BIND:-0.0.0.0}"


def test_services_are_read_only_non_root_and_bounded():
    services = _compose()["services"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER edge" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "python:3.14-slim@sha256:" in dockerfile
    assert services["caddy"]["image"].startswith("caddy:2@sha256:")
    for name in ("edge-bacnet", "edge-niagara", "caddy"):
        svc = services[name]
        assert svc["read_only"] is True
        assert svc["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in svc["security_opt"]
        assert svc["mem_limit"] == "512m"
        assert svc["stop_grace_period"] == "30s"
        if name == "caddy":
            assert "env_file" not in svc
        else:
            assert svc["env_file"] == [{"path": ".env", "required": False}]
    assert services["caddy"]["cap_add"] == ["NET_BIND_SERVICE"]
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "NIAGARA_INSECURE=0" in example
    assert "NIAGARA_CA_FILE" in example
    assert services["edge-niagara"]["environment"]["NIAGARA_INSECURE"] == '"${NIAGARA_INSECURE:-0}"' or (
        services["edge-niagara"]["environment"]["NIAGARA_INSECURE"] == "${NIAGARA_INSECURE:-0}"
    )
    assert "NIAGARA_CA_FILE" in services["edge-niagara"]["environment"]


def test_compose_passes_readme_variables():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    names: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1]
        if "NIAGARA_URL" in cell:
            names.update({"NIAGARA_URL", "NIAGARA_USER", "NIAGARA_PASS"})
        names.update(re.findall(r"`((?:EDGE|NIAGARA|BASK)_[A-Z0-9_]+)`", cell))
    services = _compose()["services"]
    present: set[str] = set()
    for svc in services.values():
        present.update(svc.get("environment") or {})
    missing = sorted(names - present)
    assert missing == []


def test_caddy_gets_only_its_own_variables():
    svc = _compose()["services"]["caddy"]
    assert "env_file" not in svc
    assert set(svc["environment"]) == {"EDGE_TLS_HOST", "EDGE_TLS_BIND"}


def test_var_init_hands_var_to_the_edge_user_before_edge_starts():
    services = _compose()["services"]
    init = services["var-init"]
    assert init["user"] == "0"
    assert init["entrypoint"] == ["chown", "-R", "1000:1000", "/var-data"]
    assert init["cap_drop"] == ["ALL"]
    assert "CHOWN" in init["cap_add"]
    assert init["volumes"] == ["./var:/var-data"]
    assert init["restart"] == "no"
    for name in ("edge-bacnet", "edge-niagara"):
        dep = services[name]["depends_on"]["var-init"]
        assert dep == {"condition": "service_completed_successfully"}
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--uid 1000" in dockerfile
