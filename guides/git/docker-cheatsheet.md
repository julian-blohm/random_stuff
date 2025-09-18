# Docker Day‑to‑Day Cheat Sheet

## 0) Install & start Service
```bash
# RHEL/CentOS
sudo yum install docker -y
sudo systemctl enable --now docker

docker --version && docker info   # verify
```

---

## 1) Images & Containers Basics (38, 36, 43)
```bash
docker pull nginx:latest                      # (38) pull image
docker images                                 # list images

# (36) run Nginx container, name it, map port 8080->80
docker run -d --name web -p 8080:80 nginx

docker ps                                     # running containers
docker logs -f web                            # follow logs
docker stop web && docker start web           # stop/start
docker rm -f web                              # remove container
docker rmi nginx:latest                       # remove image (no dependent containers)
```

---

## 2) Copy Files To/From Container (37)
```bash
docker cp ./localfile.txt web:/usr/share/nginx/html/localfile.txt   # host -> container
docker cp web:/etc/nginx/nginx.conf ./nginx.conf                    # container -> host
```

---

## 3) Exec Into Container (40)
```bash
docker exec -it web /bin/sh          # busybox/alpine
# or
docker exec -it web /bin/bash        # debian/ubuntu images
docker exec -it web nginx -t         # run a command inside
```

---

## 4) Create Image **from a Container** (39)
```bash
docker commit -m "add index" -a "you" web myorg/web:custom
docker run -d --name web2 -p 8081:80 myorg/web:custom
# Export/import (alt):
docker export web | gzip > web.tar.gz
cat web.tar.gz | gunzip | docker import - myorg/web:exported
```

---

## 5) Write a **Dockerfile** (41)
**Dockerfile** (example: static site served by Nginx):
```Dockerfile
FROM nginx:alpine
COPY ./site/ /usr/share/nginx/html/
EXPOSE 80
```
Build & run:
```bash
docker build -t mysite:latest .
docker run -d --name site -p 8080:80 mysite:latest
```

**Common patterns (Python app) (47):**
```Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]             # or: ["gunicorn","-b","0.0.0.0:8000","app:app"]
```

---

## 6) Networks (42)
```bash
docker network create appnet
docker run -d --name web --network appnet nginx
docker network ls
docker network inspect appnet
```

---

## 7) Port Mapping (43)
```bash
# -p hostPort:containerPort  (host receives traffic)
docker run -d --name api -p 9000:8080 myorg/api:latest
# multiple ports:
docker run -d --name svc -p 80:80 -p 443:443 myorg/svc:latest
```

---

## 8) Docker Compose (44, 46)
**compose.yaml** (web + redis example):
```yaml
services:
  web:
    image: nginx:alpine
    ports: ["8080:80"]
    volumes: ["./site:/usr/share/nginx/html:ro"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```
Commands:
```bash
docker compose up -d              # start
docker compose ps
docker compose logs -f web
docker compose down               # stop & remove
```

---

## 9) Fixing Dockerfile Issues (45) — quick tips
- **Wrong copy path** → ensure `COPY` source exists in build context (`.`).
- **Permissions** → use `RUN chown -R app:app /app` or `--chown=app:app` on `COPY` (newer Docker).
- **Package install** → run update first: `apt-get update && apt-get install -y ...`.
- **Cache bust** → change order: put `requirements.txt` before copying whole app for Python/Node.
- **Missing CMD/ENTRYPOINT** → container exits immediately; define one.
- **Port not exposed** → still works with `-p`, but `EXPOSE` documents intent.

---

## 10) Clean Up
```bash
docker system df                         # space usage
docker system prune -f                   # remove stopped/unused
docker volume ls && docker volume prune  # volumes
docker network ls && docker network prune
```

---

## 11) Handy One‑liners for the tasks
- **Run Nginx on 8080 (36, 43):**
```bash
docker run -d --name web -p 8080:80 nginx
```
- **Copy a file into container (37):**
```bash
docker cp ./index.html web:/usr/share/nginx/html/index.html
```
- **Exec and edit (40):**
```bash
docker exec -it web /bin/sh
```
- **Build from Dockerfile (41):**
```bash
docker build -t myimg:latest .
```
- **Compose up (44/46):**
```bash
docker compose up -d
```

---

### Notes
- Use `--name` to reference containers easily in later commands.  
- Prefer mounting a directory during development: `-v $(pwd)/site:/usr/share/nginx/html:ro`.  
- If `docker compose` isn’t available, try `docker-compose` (older plugin).  
