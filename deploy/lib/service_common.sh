#!/usr/bin/env bash
# Shared helpers for Family Media Center install/restart scripts.

MEDIACENTER_HEALTH_PATH="${MEDIACENTER_HEALTH_PATH:-/health}"

_lsof() {
  if command -v lsof >/dev/null 2>&1; then
    command lsof "$@"
  elif [[ -x /usr/sbin/lsof ]]; then
    /usr/sbin/lsof "$@"
  else
    return 127
  fi
}

mediacenter_health_url() {
  local port="$1"
  echo "http://127.0.0.1:${port}${MEDIACENTER_HEALTH_PATH}"
}

mediacenter_health_ok() {
  local port="$1"
  curl -sf --max-time 2 "$(mediacenter_health_url "${port}")" >/dev/null 2>&1
}

is_port_listening() {
  local port="${1:-}"
  if [[ -z "${port}" ]]; then
    return 1
  fi
  if _lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi
  mediacenter_health_ok "${port}"
}

kill_port_listeners() {
  local port="$1"
  local pids
  pids="$(_lsof -ti tcp:"${port}" 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  echo "Stopping existing listeners on port ${port}: ${pids}"
  kill ${pids} 2>/dev/null || true
  sleep 1
  pids="$(_lsof -ti tcp:"${port}" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill -9 ${pids} 2>/dev/null || true
  fi
}

remove_legacy_launchd_labels() {
  local domain="gui/$(id -u)"
  local legacy plist
  for legacy in "$@"; do
    [[ -z "${legacy}" ]] && continue
    plist="${HOME}/Library/LaunchAgents/${legacy}.plist"
    if [[ -f "${plist}" ]]; then
      launchctl bootout "${domain}" "${plist}" 2>/dev/null || true
      rm -f "${plist}"
      echo "==> 已移除旧 launchd 标识: ${legacy}"
    fi
  done
}

show_listen_check() {
  local port="$1"
  if _lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null; then
    return 0
  fi
  if mediacenter_health_ok "${port}"; then
    echo "OK: $(mediacenter_health_url "${port}") (health check; lsof unavailable or no LISTEN line)"
    return 0
  fi
  if command -v lsof >/dev/null 2>&1 || [[ -x /usr/sbin/lsof ]]; then
    echo "No listener on port ${port}"
  else
    echo "lsof not found; health check failed for port ${port}"
  fi
}

get_primary_lan_ipv4() {
  python3 - <<'PY'
import socket

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("8.8.8.8", 80))
    ip = sock.getsockname()[0]
    sock.close()
    if not ip.startswith("127."):
        print(ip)
except OSError:
    pass
PY
}

show_service_logs() {
  local log_dir="${1:-}"
  echo ""
  echo "==> Service logs (${log_dir})"
  if [[ -f "${log_dir}/launchd.err.log" ]]; then
    echo "--- launchd.err.log (last 15 lines) ---"
    tail -n 15 "${log_dir}/launchd.err.log" 2>/dev/null || true
  elif [[ -f "${log_dir}/stderr.log" ]]; then
    echo "--- stderr.log (last 15 lines) ---"
    tail -n 15 "${log_dir}/stderr.log" 2>/dev/null || true
  else
    echo "(no error log)"
  fi
}

show_launchd_hint() {
  local label="${1:-com.family.smart.mediacenter}"
  local domain="gui/$(id -u)"
  echo ""
  echo "==> launchd status"
  if launchctl print "${domain}/${label}" &>/dev/null; then
    launchctl print "${domain}/${label}" | sed -n '1,20p'
  else
    echo "Service not loaded. Run: ./service.sh install"
  fi
}

verify_lan_access() {
  local port="$1"
  local bind="${2:-0.0.0.0}"
  local lan_ip
  local fail=0
  local health_url
  health_url="$(mediacenter_health_url "${port}")"

  echo ""
  echo "==> Verify listen / health (port ${port})"
  show_listen_check "${port}"

  if ! is_port_listening "${port}"; then
    echo "ERROR: nothing listening on port ${port}"
    echo "  Fix: ./service.sh install"
    echo "  Or:  ./service.sh restart --force"
    show_launchd_hint
    return 1
  fi

  if mediacenter_health_ok "${port}"; then
    echo "OK: ${health_url}"
  else
    echo "ERROR: health check failed: ${health_url}"
    fail=1
  fi

  if _lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | grep -qE '\*:'"${port}"'|0\.0\.0\.0:'"${port}"; then
    echo "OK: bind includes 0.0.0.0 / *"
  elif _lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | grep -q "127.0.0.1:${port}"; then
    echo "WARN: only 127.0.0.1:${port} — LAN devices cannot connect"
    echo "  Fix: ./service.sh stop && ./service.sh install"
    fail=1
  elif mediacenter_health_ok "${port}"; then
    echo "NOTE: bind check skipped (health OK; lsof unavailable or inconclusive)"
  else
    echo "WARN: could not confirm bind address for port ${port}"
    fail=1
  fi

  lan_ip="$(get_primary_lan_ipv4 || true)"
  if [[ -n "${lan_ip}" ]]; then
    if curl -sf --max-time 5 "http://${lan_ip}:${port}${MEDIACENTER_HEALTH_PATH}" >/dev/null 2>&1; then
      echo "OK: self-test LAN http://${lan_ip}:${port}${MEDIACENTER_HEALTH_PATH}"
    else
      echo "WARN: self-test LAN FAILED http://${lan_ip}:${port}${MEDIACENTER_HEALTH_PATH}"
      fail=1
    fi
  fi

  if [[ "${bind}" != "0.0.0.0" ]]; then
    echo "WARNING: configured bind=${bind}"
    fail=1
  fi

  return "${fail}"
}

print_access_urls() {
  local port="$1"
  local bind="${2:-0.0.0.0}"

  echo ""
  echo "Access URLs (port ${port}, bind ${bind}):"
  echo "  Local:  http://127.0.0.1:${port}/"
  echo "  Health: http://127.0.0.1:${port}${MEDIACENTER_HEALTH_PATH}"

  if [[ "${bind}" != "0.0.0.0" ]]; then
    echo "  WARNING: bind=${bind} — LAN disabled. Reinstall with: --bind 0.0.0.0"
    return 0
  fi

  local lan_ip
  lan_ip="$(get_primary_lan_ipv4 || true)"
  if [[ -n "${lan_ip}" ]]; then
    echo "  LAN:    http://${lan_ip}:${port}/"
  fi

  echo "  Diagnose: ./service.sh diagnose"
}

run_diagnose() {
  local port="${1:-18026}"
  local bind="${2:-0.0.0.0}"
  print_access_urls "${port}" "${bind}"
  verify_lan_access "${port}" "${bind}"
}
