# Deploying MAL-Graph

Production runs the same services as development plus Caddy, from `docker-compose.prod.yml`:

```
https://app.mal-graph.eu ──► Caddy (TLS, basic auth, static UI) ──► /api → FastAPI ──► Memgraph
                                                                                └──► Jikan ──► MongoDB
```

Nothing but Caddy (80/443) is published; the databases and Jikan are only reachable on the
compose network.

## One-time server setup (Scaleway Instance, Ubuntu 24.04)

The server was created with `scw instance server create … cloud-init=@deploy/cloud-init.yml`, which
installs Docker, opens 22/80/443 in ufw and clones this repo to `/opt/mal-graph`. To do it by hand:

```sh
apt-get install -y docker-ce docker-compose-plugin git rsync
git clone https://github.com/djhoomin/MAL-Graph.git /opt/mal-graph
```

Then on the server, in `/opt/mal-graph`:

1. `.env` — copy `.env.example` and set `MAL_CLIENT_ID`, a random `MONGO_PASSWORD`,
   `PUBLIC_URL=https://app.mal-graph.eu`, a random `SESSION_SECRET` and `SITE_ADDRESS=app.mal-graph.eu` (Caddy obtains the Let's Encrypt certificate itself; the DNS
   A record must already point at the server).
   The MAL app's redirect URL must be `https://app.mal-graph.eu/api/auth/callback`. With sign-in on,
   `MAL_USERNAME` is only the default user for the CLI commands below.
2. `deploy/caddy/users` — one `username bcrypt-hash` per line:
   ```sh
   docker run --rm caddy:2-alpine caddy hash-password --plaintext 'the-password'
   ```
3. Seed the Jikan cache from your laptop so the server doesn't have to crawl MAL again:
   ```sh
   rsync -az data/cache/ root@app.mal-graph.eu:/opt/mal-graph/data/cache/
   ```
4. Build and start:
   ```sh
   docker compose -f docker-compose.prod.yml up -d --build
   docker compose -f docker-compose.prod.yml exec api malgraph sync-list
   docker compose -f docker-compose.prod.yml exec api malgraph expand-list   # instant for cached anime
   ```

## Updating

```sh
cd /opt/mal-graph && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

Data lives in named volumes (`mg_lib`, `mongo_data`, `caddy_data`) and survives rebuilds.
The **Sync list** button in the UI keeps the graph current with your MAL list; no cron needed.

## Backups

`deploy/backup.sh` runs every night at 03:30 UTC from `/etc/cron.d/mal-graph-backup` and logs to
`/var/log/mal-graph-backup.log`. Each run writes one `backups/mal-graph-<time>.tar.gz` with a fresh Memgraph
snapshot (the graph and every user's list), `data/golf` and `data/conversations`. The server keeps the last 7.

Each backup is also uploaded to the private bucket named in `deploy/backup.env` (Scaleway Object Storage, nl-ams,
MAL-graph project), where a lifecycle rule deletes it after 30 days. That file holds a key for the
`mal-graph-backup` IAM application, which may only write objects in the MAL-graph project, so the server can't
read or delete existing backups. `backup.env` is not in git. Without it the script only keeps local copies.

The cron entry:
```
30 3 * * * root /opt/mal-graph/deploy/backup.sh >> /var/log/mal-graph-backup.log 2>&1
```

To restore, copy the backup to the server and run:
```sh
cd /opt/mal-graph && mkdir -p /tmp/restore && tar xzf mal-graph-<time>.tar.gz -C /tmp/restore
docker compose -f docker-compose.prod.yml stop api memgraph
VOL=$(docker volume inspect -f '{{ .Mountpoint }}' mal-graph_mg_lib)
mkdir -p "$VOL/old" && mv "$VOL"/snapshots/* "$VOL"/wal/* "$VOL/old/" 2>/dev/null || true
cp /tmp/restore/<snapshot file> "$VOL/snapshots/"            # Memgraph loads the newest snapshot on start
rsync -a /tmp/restore/data/ data/                             # golf scores and conversations
docker compose -f docker-compose.prod.yml start memgraph api
```
Download from the bucket with your own Scaleway key (the server's key can't read), for example with
`curl --aws-sigv4 "aws:amz:nl-ams:s3" --user "<access key>@<MAL-graph project id>:<secret key>" -O https://<bucket>.s3.nl-ams.scw.cloud/<file>`.

## Local test of the production stack

```sh
echo "tester $(docker run --rm caddy:2-alpine caddy hash-password --plaintext test)" > deploy/caddy/users
docker compose -p malgraph-prod -f docker-compose.prod.yml -f deploy/local-override.yml up -d --build
open http://localhost:8088   # tester / test
```
