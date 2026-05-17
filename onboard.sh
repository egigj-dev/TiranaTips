#!/bin/bash
# onboard.sh — Run as ubuntu (sudo) to onboard a new teammate
# Usage: sudo bash onboard.sh <username> <port>
# Example: sudo bash onboard.sh alice 8001

set -e

USERNAME=$1
PORT=$2

if [ -z "$USERNAME" ] || [ -z "$PORT" ]; then
  echo "Usage: sudo bash onboard.sh <username> <port>"
  exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Onboarding: $USERNAME on port $PORT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Lock ubuntu home
chmod 700 /home/ubuntu

# 1. Create user (no sudo, no password login)
echo "[1/7] Creating user $USERNAME..."
adduser --disabled-password --gecos "" $USERNAME
deluser $USERNAME sudo 2>/dev/null || true

# 2. Lock home directory
echo "[2/7] Locking home directory..."
chmod 700 /home/$USERNAME

# 3. Set up SSH
echo "[3/7] Setting up SSH directory..."
mkdir -p /home/$USERNAME/.ssh
touch /home/$USERNAME/.ssh/authorized_keys
chmod 700 /home/$USERNAME/.ssh
chmod 600 /home/$USERNAME/.ssh/authorized_keys
chown -R $USERNAME:$USERNAME /home/$USERNAME/.ssh

# 4. Clone the repo
echo "[4/7] Cloning TiranaTips repo..."
sudo -u $USERNAME git clone https://github.com/egigj-dev/TiranaTips.git /home/$USERNAME/tiranatips

# 5. Copy .env and set port
echo "[5/7] Copying .env..."
cp /home/ubuntu/tiranatips/.env /home/$USERNAME/tiranatips/.env
chown $USERNAME:$USERNAME /home/$USERNAME/tiranatips/.env

# 6. Ensure shared venv exists and is up to date
echo "[6/7] Checking shared venv..."
if [ ! -d "/opt/tiranatips/venv" ]; then
  mkdir -p /opt/tiranatips
  python3 -m venv /opt/tiranatips/venv
fi
/opt/tiranatips/venv/bin/pip install -q -r /home/ubuntu/tiranatips/requirements.txt
chmod -R 755 /opt/tiranatips/venv

# 7. Done — prompt for public key
echo "[7/7] Almost done!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Paste $USERNAME's public key below"
echo " (then press Enter, then Ctrl+D)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat >> /home/$USERNAME/.ssh/authorized_keys
chmod 600 /home/$USERNAME/.ssh/authorized_keys
chown $USERNAME:$USERNAME /home/$USERNAME/.ssh/authorized_keys

echo ""
echo "✓ $USERNAME is ready!"
echo ""
echo "  SSH:   ssh $USERNAME@84.8.251.50"
echo "  Folder: /home/$USERNAME/tiranatips"
echo "  Port:  $PORT"
echo "  Venv:  source /opt/tiranatips/venv/bin/activate"
echo ""
echo "Share CONTRIBUTING.md with them to get started."
