#!/usr/bin/env bash
# Local-first audit (Linux): run the REAL app (Electron + Python engine) through the end-to-end scenario
# under strace and FAIL on any network activity that is not loopback. Needs: strace xvfb-run dbus-run-session.
#
#   scripts/audit-network.sh
#
# Covers what the scenario exercises (recording, fake STT/LLM, search, export). It cannot cover paths it
# does not run: real model download (explicit click) and a real Ollama (separate local process).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
for tool in strace xvfb-run dbus-run-session python3; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 2; }
done
trace="$(mktemp)"
trap 'rm -f "$trace"' EXIT

(cd "$root/app" && pnpm -s build >/dev/null)
cd "$root/app"
xvfb-run -a dbus-run-session -- \
  strace -f -qq -e trace=connect,sendto,sendmsg -s 300 -o "$trace" node e2e/smoke.cjs >/dev/null

python3 - "$trace" <<'PY'
import os, re, sys
ports = set()
for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    m = re.search(r":(\d+)$", os.environ.get(var, "").rstrip("/"))
    if m:
        ports.add(m.group(1))  # a proxy on loopback is still "the Internet"
bad, total = [], 0
for line in open(sys.argv[1], errors="replace"):
    if not re.search(r"\b(connect|sendto|sendmsg)\(", line):
        continue
    if "CONNECT " in line or re.search(r"(GET|POST|HEAD) https?://", line):
        bad.append("proxy request: " + line.strip()[:200])
    m = re.search(r'sa_family=AF_INET6?, sin6?_port=htons\((\d+)\).*?(?:inet_addr\("([^"]+)"\)|inet_pton\(AF_INET6, "([^"]+)")', line)
    if not m:
        continue
    total += 1
    port, v4, v6 = m.group(1), m.group(2), m.group(3)
    addr = v4 or v6
    loopback = addr.startswith("127.") or addr in ("::1", "0.0.0.0", "::")
    if not loopback:
        bad.append(f"non-loopback destination {addr}:{port}")
    elif port in ports:
        bad.append(f"connection to the proxy on port {port} (= going to the Internet)")
    if port == "53":
        bad.append("DNS query")
print(f"inspected {total} IP connections")
if bad:
    print("FAIL: outbound network activity detected:")
    for b in sorted(set(bad)):
        print("  -", b)
    sys.exit(1)
print("OK: every connection stayed on this machine (127.0.0.1) and nothing went through a proxy.")
PY
