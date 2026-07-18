#!/usr/bin/env bash
# SkillNet database backup script.
# Run manually or via cron: 0 3 * * * /path/to/skillnet/scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/skillnet_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up SkillNet database..."
docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER:-skillnet}" \
  "${POSTGRES_DB:-skillnet}" \
  --clean --if-exists \
  | gzip > "$BACKUP_FILE"

echo "Backup saved to: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Keep the last 7 daily backups.
find "$BACKUP_DIR" -name "skillnet_*.sql.gz" -mtime +7 -delete 2>/dev/null || true
echo "Old backups cleaned (kept last 7 days)."
