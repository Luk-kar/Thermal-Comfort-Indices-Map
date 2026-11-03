Claude
```bash
# first time only — creates the persistent cache volume
docker volume create claude-cache

# build (or rebuild) the image
docker compose -f docker-compose.claude.yml build

# scrap any previous container, start a fresh one
docker compose -f docker-compose.claude.yml run --rm claude

---

docker compose -f docker-compose.claude.yml build --no-cache
docker compose -f docker-compose.claude.yml run --rm claude
```