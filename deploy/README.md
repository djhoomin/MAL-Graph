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

1. `.env` — copy `.env.example` and set `MAL_CLIENT_ID`, `MAL_USERNAME`, a random `MONGO_PASSWORD`,
   and `SITE_ADDRESS=app.mal-graph.eu` (Caddy obtains the Let's Encrypt certificate itself; the DNS
   A record must already point at the server).
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

## Local test of the production stack

```sh
echo "tester $(docker run --rm caddy:2-alpine caddy hash-password --plaintext test)" > deploy/caddy/users
docker compose -p malgraph-prod -f docker-compose.prod.yml -f deploy/local-override.yml up -d --build
open http://localhost:8088   # tester / test
```
