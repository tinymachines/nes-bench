#!/bin/bash
# Set a Raspberry Pi 5 up as the ESP32 test platform for the nes-bench
# firmware, with the same toolchain the sketches were built and flashed
# with elsewhere, plus a Rust side for experiments.
#
#   bash pi-esp32-setup.sh            # everything (ESP-IDF included, ~4 GB)
#   bash pi-esp32-setup.sh --no-idf   # skip ESP-IDF (Arduino + Rust only)
#   bash pi-esp32-setup.sh --verify   # print what is installed, build the
#                                     # two pad sketches if nes-bench is here
#
# Idempotent: every step checks before it acts, so rerunning is cheap.
# Versions are pinned where the firmware was proven against them:
#   esp32 Arduino core 3.3.11  (pad-usb on the P4, pad-ble on the C6,
#                               both compiled and flashed 2026-09-27)
#   arduino:avr 1.8.8          (bridge-uno, avr-gcc 7.3.0)
# Nothing host-specific is in here: no addresses, no serial numbers.
set -euo pipefail

ESP32_CORE=3.3.11
AVR_CORE=1.8.8
IDF_VERSION=v5.5.1
IDF_TARGETS=esp32,esp32s3,esp32c3,esp32c6,esp32h2,esp32p4
ESP32_URL=https://espressif.github.io/arduino-esp32/package_esp32_index.json
BIN=$HOME/.local/bin
VENV=$HOME/.venvs/esp
export PATH=$BIN:$HOME/.cargo/bin:$PATH

WITH_IDF=1; VERIFY_ONLY=0
for a in "$@"; do case $a in --no-idf) WITH_IDF=0;; --verify) VERIFY_ONLY=1;; *) echo "unknown flag $a"; exit 2;; esac; done

say() { printf '\n== %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

verify() {
  say "what this Pi has"
  echo "host:      $(uname -m) $(. /etc/os-release; echo "$PRETTY_NAME") $(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')"
  echo "groups:    $(id -nG)"
  echo "claude:    $(have claude && claude --version 2>/dev/null | head -1 || echo missing)"
  echo "arduino:   $(have arduino-cli && arduino-cli version | sed 's/ Commit.*//' || echo missing)"
  have arduino-cli && arduino-cli core list 2>/dev/null | sed 's/^/           /'
  echo "esptool:   $($VENV/bin/esptool version 2>/dev/null | tail -1 || echo missing)"
  echo "rust:      $(have rustc && rustc --version || echo missing)"
  have rustup && rustup target list --installed 2>/dev/null | grep riscv | sed 's/^/           /'
  echo "espflash:  $(have espflash && espflash --version || echo missing)"
  echo "espup:     $(have espup && espup --version || echo missing)"
  echo "xtensa:    $(rustup toolchain list 2>/dev/null | grep -q '^esp' && echo 'esp toolchain present (S3 targets)' || echo 'no esp toolchain')"
  echo "esp-idf:   $([ -f $HOME/esp/esp-idf/version.txt ] && cat $HOME/esp/esp-idf/version.txt || (cd $HOME/esp/esp-idf 2>/dev/null && git describe --tags 2>/dev/null) || echo missing)"
  echo "avrdude:   $(have avrdude && avrdude -? 2>&1 | grep -o 'version [0-9.]*' | head -1 || echo missing)"
  echo "serial:    $(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | tr '\n' ' ' || true)"
  echo "usb:       $(lsusb 2>/dev/null | grep -iE '303a|1a86|10c4|0403|2341' | sed 's/^/           /' | tr '\n' ';' || true)"

  # The check that cannot pass on nothing: each sketch must yield a .bin
  # of a plausible size with the fqbn its own header records.
  local bench=""
  for d in "$HOME/projects/tinymachines/nes-bench" "$HOME/nes-bench" "$HOME/projects/nes-bench"; do [ -d "$d/firmware" ] && bench=$d && break; done
  if [ -z "$bench" ] || ! have arduino-cli; then
    echo; echo "nes-bench not cloned here (or no arduino-cli): the sketch builds were NOT tried"; return
  fi
  say "building the pad sketches from $bench"
  local out; out=$(mktemp -d)
  local ok=1
  for pair in "pad-ble:esp32:esp32:esp32c6:CDCOnBoot=cdc" "pad-usb:esp32:esp32:esp32p4:FlashSize=16M,PartitionScheme=fatflash,PSRAM=enabled"; do
    local sk=${pair%%:*} fqbn=${pair#*:}
    if arduino-cli compile --fqbn "$fqbn" --output-dir "$out/$sk" "$bench/firmware/$sk" >"$out/$sk.log" 2>&1; then
      local b="$out/$sk/$sk.ino.bin"
      if [ -s "$b" ] && [ "$(stat -c %s "$b")" -gt 200000 ]; then
        echo "  $sk: ok, $(stat -c %s "$b") bytes ($fqbn)"
      else echo "  $sk: compiled but no plausible .bin at $b"; ok=0; fi
    else echo "  $sk: FAILED, see $out/$sk.log"; tail -5 "$out/$sk.log" | sed 's/^/    /'; ok=0; fi
  done
  [ $ok = 1 ] && echo "both sketches build here" || { echo "a sketch did not build"; return 1; }
}

if [ $VERIFY_ONLY = 1 ]; then verify; exit; fi

# ---- 1. packages ---------------------------------------------------------
say "apt packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  build-essential git curl wget jq tmux unzip \
  cmake ninja-build ccache pkg-config \
  flex bison gperf libffi-dev libssl-dev libusb-1.0-0 libudev-dev dfu-util \
  python3 python3-venv python3-pip python3-serial \
  picocom minicom usbutils avrdude \
  >/dev/null
# brltty claims CP210x and CH340 adapters as braille displays and steals
# the port. Nothing on this bench reads braille.
if dpkg -l brltty 2>/dev/null | grep -q '^ii'; then sudo apt-get remove -y -qq brltty >/dev/null; fi

# ---- 2. the user reaches serial and raw USB ------------------------------
say "groups and udev"
for g in dialout plugdev; do getent group $g >/dev/null && sudo usermod -aG $g "$USER"; done
sudo tee /etc/udev/rules.d/60-esp-bench.rules >/dev/null <<'RULES'
# Espressif USB-Serial-JTAG and USB-OTG (303a), CH340 (1a86), CP210x (10c4),
# FTDI (0403), Arduino (2341): reachable by plugdev, ignored by ModemManager.
SUBSYSTEM=="usb", ATTR{idVendor}=="303a", MODE="0660", GROUP="plugdev", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", MODE="0660", GROUP="plugdev", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="usb", ATTR{idVendor}=="10c4", MODE="0660", GROUP="plugdev", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="usb", ATTR{idVendor}=="0403", MODE="0660", GROUP="plugdev", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="usb", ATTR{idVendor}=="2341", MODE="0660", GROUP="plugdev", TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ENV{ID_MM_DEVICE_IGNORE}="1"
RULES
sudo udevadm control --reload-rules && sudo udevadm trigger

# ---- 3. arduino-cli with the esp32 and avr cores --------------------------
say "arduino-cli"
mkdir -p "$BIN"
if ! have arduino-cli; then
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$BIN" sh >/dev/null
fi
arduino-cli config init --overwrite >/dev/null
arduino-cli config set board_manager.additional_urls "$ESP32_URL"
arduino-cli core update-index >/dev/null
core_has() { arduino-cli core list 2>/dev/null | awk -v c="$1" -v v="$2" '$1==c && $2==v {f=1} END {exit !f}'; }
core_has esp32:esp32 $ESP32_CORE || arduino-cli core install esp32:esp32@$ESP32_CORE
core_has arduino:avr $AVR_CORE  || arduino-cli core install arduino:avr@$AVR_CORE

# ---- 4. esptool in its own venv -------------------------------------------
say "esptool (venv $VENV)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip esptool pyserial
ln -sf "$VENV/bin/esptool" "$BIN/esptool"

# ---- 5. rust: stable plus the RISC-V targets the C3/C6/H2/P4 need --------
say "rust"
if ! have rustup; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal >/dev/null
fi
rustup toolchain install stable --profile minimal -c rust-src -c clippy -c rustfmt >/dev/null
rustup toolchain install nightly --profile minimal -c rust-src >/dev/null
for t in riscv32imc-unknown-none-elf riscv32imac-unknown-none-elf riscv32imafc-unknown-none-elf; do
  rustup target add --toolchain stable $t >/dev/null
  rustup target add --toolchain nightly $t >/dev/null
done
if ! have cargo-binstall; then
  curl -L --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/cargo-bins/cargo-binstall/main/install-from-binstall-release.sh | bash >/dev/null
fi
cargo binstall --no-confirm espflash cargo-espflash espup cargo-generate esp-generate ldproxy >/dev/null 2>&1 || \
cargo binstall --no-confirm espflash cargo-espflash espup cargo-generate esp-generate ldproxy
# espup adds the Xtensa fork of rustc, which is what an S3 (and the
# classic ESP32) needs; RISC-V parts build on plain stable/nightly.
if ! rustup toolchain list | grep -q '^esp'; then espup install >/dev/null; fi
grep -q 'export-esp.sh' "$HOME/.bashrc" || echo '[ -f "$HOME/export-esp.sh" ] && . "$HOME/export-esp.sh"' >> "$HOME/.bashrc"

# ---- 6. ESP-IDF, for the C6 slave firmware and anything below Arduino ----
if [ $WITH_IDF = 1 ]; then
  say "esp-idf $IDF_VERSION ($IDF_TARGETS)"
  mkdir -p "$HOME/esp"
  if [ ! -d "$HOME/esp/esp-idf/.git" ]; then
    git clone -q --depth 1 --branch $IDF_VERSION --recursive https://github.com/espressif/esp-idf.git "$HOME/esp/esp-idf"
  fi
  (cd "$HOME/esp/esp-idf" && ./install.sh "$IDF_TARGETS" >/dev/null)
  grep -q 'alias get_idf' "$HOME/.bashrc" || echo 'alias get_idf=". $HOME/esp/esp-idf/export.sh"' >> "$HOME/.bashrc"
fi

# ---- 7. PATH for login shells ---------------------------------------------
grep -q '.local/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"' >> "$HOME/.bashrc"

verify
echo
echo "done. Log out and in once so the dialout/plugdev membership applies."
