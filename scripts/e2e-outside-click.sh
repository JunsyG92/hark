#!/usr/bin/env bash
# Real clicks under a real window manager (Openbox): the side panel must hide when you click another
# window, but NOT when you open a dropdown of its own, and NOT when it is pinned.
#   xvfb-run -a -s "-screen 0 1600x1000x24" scripts/e2e-outside-click.sh
# Needs: openbox xdotool xterm (and a built app: pnpm --filter @hark/app build).
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
electron="$root/app/node_modules/electron/dist/electron"
flags=(); [ "$(id -u)" = 0 ] && flags=(--no-sandbox)
for t in openbox xdotool xterm; do command -v "$t" >/dev/null || { echo "$t is required" >&2; exit 2; }; done

fails=0
openbox >/dev/null 2>&1 & wm=$!
xterm -geometry 60x20+20+20 -e sleep 600 >/dev/null 2>&1 & term=$!
cleanup() { kill "$wm" "$term" 2>/dev/null; pkill -f "$electron" 2>/dev/null; }
trap cleanup EXIT
sleep 1

panel_visible() { [ -n "$(xdotool search --onlyvisible --name '^Hark$' 2>/dev/null | head -1)" ]; }

launch() { # $1 = settings.json content ('' for defaults)
  home="$(mktemp -d)"
  if [ -n "$1" ]; then mkdir -p "$home/.config/Hark"; echo "$1" > "$home/.config/Hark/settings.json"; fi
  env -u XDG_CONFIG_HOME HOME="$home" HARK_DATA_DIR="$home/data" HARK_PORT=0 HARK_FAKE_AUDIO=1 \
    "$electron" "${flags[@]}" "$root/app" >/dev/null 2>&1 &
  for _ in $(seq 1 60); do panel_visible && break; sleep 0.25; done
  sleep 1.5
}
stop() { pkill -f "$electron"; sleep 1; }
expect() { # $1 name, $2 expected: hidden|visible
  local got=visible; panel_visible || got=hidden
  if [ "$got" = "$2" ]; then echo "  ✓ $1: $got"; else echo "  ✗ $1: expected $2, got $got"; fails=$((fails+1)); fi
}
read -r W H < <(xdotool getdisplaygeometry)

echo "Side panel and clicks:"
launch ''
panel_visible || { echo "  ✗ the panel did not show"; exit 1; }
# open the panel's own filter dropdown (pointer inside the panel): must stay
xdotool mousemove $((W - 340)) 86 click 1; sleep 1
expect "dropdown of the panel" visible
xdotool key Escape; sleep 0.5
# click another window: must hide
xdotool mousemove 200 150 click 1; sleep 1.5
expect "click on another window" hidden
stop

launch '{"shortcut":"Control+Alt+K","launchAtLogin":false,"hideOnBlur":false}'
xdotool mousemove 200 150 click 1; sleep 1.5
expect "pinned, click on another window" visible
stop

[ "$fails" = 0 ] && echo "OK" || { echo "$fails failure(s)"; exit 1; }
