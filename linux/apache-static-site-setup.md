# Deploying Multiple Static Sites with Apache

This guide explains how to configure Apache to serve (multiple) static websites from different directories under the same server.  
It assumes Apache is already installed and configured to listen on the desired port (see e.g. LAMP stack setup guide for those steps).

---

## 1. Prepare Website Content
- Obtain or create the static site content directories (e.g., `site1`, `site2`).  
- If content is on another host, copy it over with `scp`:
```bash
scp -r /path/to/site1 /path/to/site2 user@target-server:/tmp/
```

---

## 2. Place Sites Under Apache Web Root
Move the site directories into Apache’s document root (commonly `/var/www/html`):

```bash
sudo mv /tmp/site1 /var/www/html/site1
sudo mv /tmp/site2 /var/www/html/site2
```

Each directory name becomes part of the URL path.

---

## 3. Verify Access
Access the sites via curl or a browser:

```bash
curl http://localhost:<port>/site1/
curl http://localhost:<port>/site2/
```