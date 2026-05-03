#!/usr/bin/bash
#
# Install iNiR shell + personal dotfiles on a clean Arch Linux system.
#
# Usage:
#   bash install-my-setup.sh
#
# What this does:
#   1. Installs base packages (git, base-devel, etc.)
#   2. Installs yay (AUR helper)
#   3. Runs iNiR ./setup install
#   4. Deploys ReminderBot CLI scripts (~/.local/share/reminderbot/)
#   5. Applies custom iNiR config
#   6. Deploys fish shell config
#   7. Deploys Neovim config (LazyVim)
#   8. Deploys wallpapers
#
# Run as a regular user (script will use sudo where needed).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*" >&2; }
header() { echo -e "\n${CYAN}=== $* ===${NC}\n"; }

confirm() {
  local answer
  read -rp "$(echo -e "${YELLOW}[?]${NC} $1 [Y/n] ")" answer
  [[ -z "$answer" || "$answer" == "y" || "$answer" == "Y" ]]
}

if [[ $EUID -eq 0 ]]; then
  error "Do not run this script as root. Run as your regular user."
  exit 1
fi

echo ""
echo "========================================="
echo "  iNiR + Personal Setup Installer"
echo "  Repo: $SCRIPT_DIR"
echo "========================================="
echo ""

# ── 1. Base packages ─────────────────────────────────────────────

header "Base packages"

BASE_PACKAGES=(
  git
  base-devel
  fish
  neovim
  starship
  eza
  kitty
  ttf-jetbrains-mono-nerd
  noto-fonts
  noto-fonts-cjk
  noto-fonts-emoji
)

info "Installing base packages..."
sudo pacman -S --needed --noconfirm "${BASE_PACKAGES[@]}"

# ── 2. yay (AUR helper) ──────────────────────────────────────────

header "AUR helper (yay)"

if command -v yay &>/dev/null; then
  info "yay already installed"
else
  info "Installing yay..."
  TMPDIR="$(mktemp -d)"
  git clone https://aur.archlinux.org/yay-bin.git "$TMPDIR/yay-bin"
  (cd "$TMPDIR/yay-bin" && makepkg -si --noconfirm)
  rm -rf "$TMPDIR"
  info "yay installed"
fi

# ── 3. iNiR setup ────────────────────────────────────────────────

header "iNiR shell"

if confirm "Run iNiR ./setup install?"; then
  info "Running iNiR installer..."
  bash "$SCRIPT_DIR/setup" install
  info "iNiR installed"
fi

# ── 4. ReminderBot CLI ───────────────────────────────────────────

header "ReminderBot CLI"

REMINDERBOT_DEST="$HOME/.local/share/reminderbot"

if confirm "Deploy ReminderBot CLI scripts?"; then
  if ! command -v uv &>/dev/null; then
    warn "uv not found — installing via pacman..."
    sudo pacman -S --needed --noconfirm uv
  fi

  mkdir -p "$REMINDERBOT_DEST/cli"
  cp -r "$SCRIPT_DIR/dots/reminderbot/"* "$REMINDERBOT_DEST/"
  info "ReminderBot CLI deployed to $REMINDERBOT_DEST"

  if [[ ! -f "$REMINDERBOT_DEST/.env" ]]; then
    cat > "$REMINDERBOT_DEST/.env" <<'EOF'
API_URL=http://localhost:8000
API_KEY=
EOF
    warn "Created $REMINDERBOT_DEST/.env — fill in API_URL and API_KEY"
  else
    info ".env already exists, skipped"
  fi
fi

# ── 5. Custom iNiR config ────────────────────────────────────────

header "Custom iNiR config"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/illogical-impulse"
# Fall back to inir config dir if illogical-impulse doesn't exist
if [[ ! -d "$CONFIG_DIR" ]]; then
  CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/inir"
fi

if [[ -d "$CONFIG_DIR" ]]; then
  if confirm "Apply custom iNiR config? (backs up existing)"; then
    if [[ -f "$CONFIG_DIR/config.json" ]]; then
      cp "$CONFIG_DIR/config.json" "$CONFIG_DIR/config.json.bak"
      warn "Backed up existing config to config.json.bak"
    fi
    cp "$SCRIPT_DIR/defaults/config.json" "$CONFIG_DIR/config.json"
    info "Custom config applied"
  fi
else
  warn "iNiR config directory not found — run ./setup install first"
fi

# ── 6. Fish shell config ─────────────────────────────────────────

header "Fish shell config"

if confirm "Deploy fish config?"; then
  FISH_DIR="$HOME/.config/fish"
  if [[ -d "$FISH_DIR" ]]; then
    cp -r "$FISH_DIR" "${FISH_DIR}.bak"
    warn "Backed up existing fish config to fish.bak/"
  fi
  mkdir -p "$FISH_DIR"
  cp -r "$SCRIPT_DIR/dots/fish/"* "$FISH_DIR/"
  info "Fish config deployed"

  if confirm "Set fish as default shell?"; then
    if ! grep -q "$(command -v fish)" /etc/shells; then
      echo "$(command -v fish)" | sudo tee -a /etc/shells >/dev/null
    fi
    chsh -s "$(command -v fish)"
    info "Default shell set to fish"
  fi
fi

# ── 7. Neovim config ─────────────────────────────────────────────

header "Neovim config"

if confirm "Deploy nvim config (LazyVim)?"; then
  NVIM_DIR="$HOME/.config/nvim"
  if [[ -d "$NVIM_DIR" ]]; then
    mv "$NVIM_DIR" "${NVIM_DIR}.bak"
    warn "Backed up existing nvim config to nvim.bak/"
  fi
  mkdir -p "$NVIM_DIR"
  cp -r "$SCRIPT_DIR/dots/nvim/"* "$NVIM_DIR/"
  info "Neovim config deployed"
  info "Run 'nvim' to trigger lazy plugin installation"
fi

# ── 8. Wallpapers ─────────────────────────────────────────────────

header "Wallpapers"

if confirm "Deploy wallpapers?"; then
  mkdir -p "$HOME/Wallpapers"
  if [[ -d "$SCRIPT_DIR/dots/wallpapers" ]]; then
    rsync -a "$SCRIPT_DIR/dots/wallpapers/" "$HOME/Wallpapers/"
    info "Wallpapers deployed from repo"
  else
    warn "dots/wallpapers/ not found in repo, skipping"
  fi
fi

# ── Done ──────────────────────────────────────────────────────────

echo ""
info "Setup complete!"
echo ""
echo "Next steps:"
echo "  - Log out and select Niri as your session"
echo "  - Or run: inir run"
echo "  - Set a wallpaper via the wallpaper selector"
echo "  - Open nvim to install plugins"
echo ""
