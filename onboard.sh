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

# 0. Lock ubuntu home so teammates can't access other projects
echo "[0/8] Locking ubuntu home directory..."
chmod 700 /home/ubuntu

# 1. Create user (no sudo, no password login)
echo "[1/8] Creating user $USERNAME..."
adduser --disabled-password --gecos "" $USERNAME
deluser $USERNAME sudo 2>/dev/null || true

# 2. Lock their home directory
echo "[2/8] Locking home directory..."
chmod 700 /home/$USERNAME

# 3. Set up SSH directory
echo "[3/8] Setting up SSH directory..."
mkdir -p /home/$USERNAME/.ssh
touch /home/$USERNAME/.ssh/authorized_keys
chmod 700 /home/$USERNAME/.ssh
chmod 600 /home/$USERNAME/.ssh/authorized_keys
chown -R $USERNAME:$USERNAME /home/$USERNAME/.ssh

# 4. Clone the repo
echo "[4/8] Cloning TiranaTips repo..."
sudo -u $USERNAME git clone https://github.com/egigj-dev/TiranaTips.git /home/$USERNAME/tiranatips

# 5. Copy .env
echo "[5/8] Copying .env..."
cp /home/ubuntu/tiranatips/.env /home/$USERNAME/tiranatips/.env
chown $USERNAME:$USERNAME /home/$USERNAME/tiranatips/.env

# 6. Install python3-venv if missing and set up shared venv
echo "[6/8] Setting up shared venv..."
apt install python3-venv python3-full -y -q
if [ ! -d "/opt/tiranatips/venv" ]; then
  mkdir -p /opt/tiranatips
  python3 -m venv /opt/tiranatips/venv
fi
/opt/tiranatips/venv/bin/pip install -q -r /home/ubuntu/tiranatips/requirements.txt
chmod -R 755 /opt/tiranatips/venv

# 7. Generate SSH key pair for the teammate
echo "[7/8] Generating SSH key pair..."
ssh-keygen -t ed25519 -C "$USERNAME" -f /tmp/${USERNAME}_key -N ""
bash -c "cat /tmp/${USERNAME}_key.pub >> /home/$USERNAME/.ssh/authorized_keys"
chown $USERNAME:$USERNAME /home/$USERNAME/.ssh/authorized_keys
chmod 600 /home/$USERNAME/.ssh/authorized_keys

# 8. Show private key and clean up
echo "[8/8] Done!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PRIVATE KEY — send this to $USERNAME"
echo " via Signal, WhatsApp or onetimesecret.com"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat /tmp/${USERNAME}_key
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Delete keys from server immediately
rm /tmp/${USERNAME}_key /tmp/${USERNAME}_key.pub

echo ""
echo "✓ $USERNAME is ready!"
echo ""
echo "  SSH:    ssh -i ~/.ssh/tiranatips_key $USERNAME@84.8.251.50"
echo "  Folder: /home/$USERNAME/tiranatips"
echo "  Port:   $PORT"
echo "  Venv:   source /opt/tiranatips/venv/bin/activate"
echo ""
echo "Share CONTRIBUTING.md with them to get started."
echo "Private key has been deleted from the server."