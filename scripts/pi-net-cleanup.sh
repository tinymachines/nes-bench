#!/usr/bin/env bash
# Take the head (the Raspberry Pi) off a gateway network that no longer
# exists, and hand its resolver back to NetworkManager.
#
#   scripts/pi-net-cleanup.sh <pi-host>          # apply, with backups
#   scripts/pi-net-cleanup.sh <pi-host> --check  # diagnose only, change nothing
#
# The host is an argument on purpose: the Pi's address lives in
# bench.local.md, which git ignores, and must not be written here.
#
# What it found on 2026-09-11, and what this undoes:
#   - /etc/resolv.conf was chattr-immutable and named two DNS servers on
#     the old gateway network (a Tor-over-DNSCrypt resolver), which is
#     gone, so nothing resolved although IPv4 routing to the internet
#     was fine. NetworkManager had the right file ready in
#     /run/NetworkManager/resolv.conf and could not write it.
#   - dnsmasq (on :53, default config) took its upstreams from that file.
#   - /etc/apt/apt.conf.d/95proxies and ~/.npmrc sent apt and npm through
#     a proxy on the same dead network.
# Every file changed is copied first into ~/net-cleanup-<date>/ on the
# Pi. Nothing else on the Pi referenced that network (no VPN packages,
# routes, firewall rules or proxy environment).
set -euo pipefail

host="${1:?usage: $0 <pi-host> [--check]}"
mode="${2:-apply}"
ssh_opts=(-o ConnectTimeout=8 -o BatchMode=yes)

diagnose='
echo "== routes"; ip -4 route show default; ip rule | grep -v "lookup local\|lookup main\|lookup default" || true
echo "== resolver"; lsattr /etc/resolv.conf 2>/dev/null; cat /etc/resolv.conf
echo "== NetworkManager would write"; cat /run/NetworkManager/resolv.conf 2>/dev/null || echo "(none)"
echo "== proxies"; cat /etc/apt/apt.conf.d/95proxies 2>/dev/null || echo "apt: none"; grep -E "^(https-)?proxy=" ~/.npmrc 2>/dev/null || echo "npm: none"
echo "== reachability"; ping -c1 -W2 1.1.1.1 >/dev/null 2>&1 && echo "ipv4 egress ok" || echo "ipv4 egress FAILED"
getent hosts deb.debian.org >/dev/null 2>&1 && echo "dns ok" || echo "dns FAILED"
'

apply='
set -e
B=~/net-cleanup-$(date +%F); mkdir -p "$B"
sudo cp -a /etc/resolv.conf "$B/resolv.conf"
[ -f /etc/apt/apt.conf.d/95proxies ] && sudo cp -a /etc/apt/apt.conf.d/95proxies "$B/apt-95proxies"
[ -f ~/.npmrc ] && cp -a ~/.npmrc "$B/npmrc"
echo "== resolver back to NetworkManager"
sudo chattr -i /etc/resolv.conf
# NetworkManager'"'"'s default rc-manager (symlink) leaves a REGULAR
# /etc/resolv.conf alone, which is why the first run of this script
# cleared the flag and changed nothing: the file has to be the symlink.
sudo ln -sf /run/NetworkManager/resolv.conf /etc/resolv.conf
sudo nmcli general reload dns-rc
sleep 1; cat /etc/resolv.conf
echo "== proxies removed"
sudo rm -f /etc/apt/apt.conf.d/95proxies
[ -f ~/.npmrc ] && sed -i "/^proxy=/d;/^https-proxy=/d" ~/.npmrc
echo "== dnsmasq re-reads its upstreams"
systemctl is-active dnsmasq >/dev/null 2>&1 && sudo systemctl restart dnsmasq || true
# With DNS dead the clock could not sync either, and a clock months
# behind makes every certificate "not yet valid" and apt refuse every
# release file. timesyncd recovers on its own once names resolve.
echo "== clock"
sudo systemctl restart systemd-timesyncd; sleep 5; date -u; timedatectl show -p NTPSynchronized
echo "== verify"
getent hosts deb.debian.org | head -1
curl -sSI --max-time 10 https://deb.debian.org/ | head -1
sudo apt-get update 2>&1 | tail -1
echo "== backups in $B"; ls -l "$B"
'

case "$mode" in
  --check) ssh "${ssh_opts[@]}" "$host" "$diagnose" ;;
  apply)   ssh "${ssh_opts[@]}" "$host" "$apply" ;;
  *)       echo "usage: $0 <pi-host> [--check]" >&2; exit 2 ;;
esac
