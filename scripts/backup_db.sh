#!/usr/bin/env bash
set -euo pipefail

# REPO_DIR anchors the database; BACKUP_DIR and KEEP_DAYS control destination and retention.
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
: "${BACKUP_DIR:?Set BACKUP_DIR to an absolute directory off the data volume}"
KEEP_DAYS="${KEEP_DAYS:-14}"
[[ "$BACKUP_DIR" = /* && "$KEEP_DAYS" =~ ^[0-9]+$ ]]
[[ -f "$REPO_DIR/data/chat_history.db" ]]
umask 077
mkdir -p -- "$BACKUP_DIR"

# TMP is private and unique; the trap never removes an existing validated backup.
TMP="$(mktemp "$BACKUP_DIR/.chat_history.XXXXXX.tmp")"
trap 'rm -f -- "$TMP"' EXIT
sqlite3 "$REPO_DIR/data/chat_history.db" ".backup '$TMP'"
INTEGRITY="$(sqlite3 "$TMP" 'PRAGMA integrity_check;')"
[[ "$INTEGRITY" == "ok" ]]
mv -f -- "$TMP" "$BACKUP_DIR/chat_history-$(date -u +%F).db"

# Only dated backup files are eligible for retention after a successful backup.
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'chat_history-????-??-??.db' -mtime +"$KEEP_DAYS" -delete
