# Nginx Installation and SSL Setup Guide

This guide describes the minimal steps to install Nginx and configure it with an SSL certificate on CentOS/RHEL systems.
It also shows how to generate a simple self-signed SSL certificate if none is provided.

---

## 1. Install Nginx
Install and start Nginx
```bash
sudo yum -y install nginx
sudo systemctl enable --now nginx
```
`systemctl enable --now nginx` — enables Nginx to start automatically on boot (`enable`) and starts it immediately (`--now`). If this succeeds, the default Nginx page is accessible over HTTP (port 80).

---

## 2. SSL Certificate using existing certificate and key
### Option A: Use a provided certificate and key
If the certificate and key are already provided, move them to a standard location

```bash
sudo mkdir -p /etc/pki/nginx
sudo mv /tmp/example.crt /etc/pki/nginx/
sudo mv /tmp/example.key /etc/pki/nginx/
# ensures only root owns the cert/key files
sudo chown root:root /etc/pki/nginx/example.*
# read/write for root, no permissions for others; private keys should never be world-readable
sudo chmod 600 /etc/pki/nginx/example.key
```

### Option B: Generate a simple self-signed certificate
If no certificate is available, create one.

```bash
sudo mkdir -p /etc/pki/nginx
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/pki/nginx/example.key \
  -out /etc/pki/nginx/example.crt \
  -subj "/CN=example.com"
```
- `openssl req`: Creates a new certificate request
- `x509`: Outputs a self-signed certificate
- `nodes`: No passphrase for the private key (so Nginx can read it)
- `days 365`: Certificate valid for 1 year
- `newkey rsa:2048`: Creates a new RSA key of 2048 bits
- `subj "/CN=example.com"`: Sets the Common Name (replace with domain or hostname); will create `example.crt` and `example.key` inside `/etc/pki/nginx/`.

---

## 3. Configure Nginx for HTTPS
Create a HTTPS server block

```bash
sudo tee /etc/nginx/conf.d/ssl.conf >/dev/null <<'EOF'
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/pki/nginx/example.crt;
    ssl_certificate_key /etc/pki/nginx/example.key;

    root /usr/share/nginx/html;
    index index.html;
}
EOF
```

Explanation:
- `conf.d/ssl.conf` — single-purpose config file that Nginx automatically includes (clean separation from the main config)
- `listen 443 ssl` — Nginx listens on port 443 (HTTPS)
- `server_name _` — a catch-all “default” server for any hostname (good for simple setups)
- `ssl_certificate` / `ssl_certificate_key` — point to the cert/key
- `root /usr/share/nginx/html` — Location of website files
- `index` - Default file to serve

```bash
sudo nginx -t
sudo systemctl reload nginx
```
- `nginx -t` — Tests the config file
- `systemctl reload nginx` — Reloads Nginx with the new config

---

## 4. Add an Index Page
```bash
echo "Welcome!" | sudo tee /usr/share/nginx/html/index.html >/dev/null
```

---

## 5. Test HTTPS Access
Use curl with -k to ignore certificate validation (self-signed certificates are not trusted by default)
```bash
curl -Ik https://<server-ip>/
```
- `-I`: Fetch only the headers
- `-k`: Skip SSL certificate validation
- Expected: `HTTP/1.1 200 OK`
