#!/usr/bin/env bash
# Nightly backup of MAL-Graph's state, run by cron on the server (see deploy/README.md).
#
# Each backup is one tar.gz holding a fresh Memgraph snapshot (the whole graph, including every user's list),
# the Graph Golf holes and scores, and the Ask conversations and usage. The last KEEP backups stay in backups/
# on the server. If deploy/backup.env exists, each backup is also uploaded to Object Storage, where a lifecycle
# rule deletes it after 30 days. The upload key may only write objects, so this server can't delete old backups.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"
KEEP=7
NAME="mal-graph-$(date -u +%Y%m%d-%H%M%S).tar.gz"
mkdir -p backups

# A fresh snapshot, then the newest snapshot file from Memgraph's data volume.
$COMPOSE exec -T memgraph bash -c "echo 'CREATE SNAPSHOT;' | mgconsole" >/dev/null
VOLUME=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/memgraph"}}{{.Source}}{{end}}{{end}}' "$($COMPOSE ps -q memgraph)")
SNAPSHOT=$(ls -t "$VOLUME/snapshots" | head -1)

tar czf "backups/$NAME.part" -C "$VOLUME/snapshots" "$SNAPSHOT" -C "$PWD" data/golf data/conversations
mv "backups/$NAME.part" "backups/$NAME"
ls -1t backups/mal-graph-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f --

where="kept on the server"
if [ -f deploy/backup.env ]; then
  set -a; . deploy/backup.env; set +a
  # The key goes to curl through a config on stdin, so it never shows up in the process list.
  printf 'user = "%s:%s"\n' "$BACKUP_ACCESS_KEY" "$BACKUP_SECRET_KEY" | curl -fsS -K - \
    --aws-sigv4 "aws:amz:$BACKUP_REGION:s3" -T "backups/$NAME" \
    "https://$BACKUP_BUCKET.s3.$BACKUP_REGION.scw.cloud/$NAME"
  where="kept on the server and uploaded to $BACKUP_BUCKET"
fi
echo "$(date -u '+%F %T') $NAME ($(du -h "backups/$NAME" | cut -f1)) $where"
