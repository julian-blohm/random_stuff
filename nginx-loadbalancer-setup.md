# Configuring Nginx as a Load Balancer on CentOS

This guide explains how to configure an Nginx-based load balancer (LBR) that distributes traffic across multiple Apache app servers.  
It assumes you already have Apache running on the app servers.

---

## 1. Install Nginx on the LBR server
```bash
sudo yum -y install nginx
```

---

## 2. Check which port Apache is running on each App Server
Log in to each app server and run the following to get the port:

```bash
# Check Apache Listen directive
grep -R "^Listen" /etc/httpd/conf/httpd.conf /etc/httpd/conf.d/
```

---

## 3. Configure Nginx
Edit the main config file:

```bash
sudo vi /etc/nginx/nginx.conf
```

Inside the existing `http { ... }` block, add this near the end (before the closing `}`):

```nginx
    upstream app_servers {
        # Replace with the actual Apache port you found (e.g., 8084)
        server stapp01:8084;
        server stapp02:8084;
        server stapp03:8084;
    }

    server {
        listen 80;

        location / {
            proxy_pass http://app_servers;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
```

Save and quit (`:wq`).

---

## 4. Validate and Restart Nginx
```bash
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 5. Verification
- From the LBR server:
```bash
curl -I http://localhost/
```

- From the jump host:
```bash
curl -I http://<LBR-hostname>/
```

Expected result: `HTTP/1.1 200 OK`
