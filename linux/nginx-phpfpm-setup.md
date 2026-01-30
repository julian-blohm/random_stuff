# Nginx + PHP-FPM Setup Guide (CentOS 9)

This guide shows how to run PHP applications with **Nginx** as the web server and **PHP-FPM** as the PHP runtime on CentOS 9.

---

## Why this setup?

- **Nginx is not a PHP engine** — it’s a fast, lightweight web server. It serves static files (HTML, CSS, images) directly, but when it sees a `.php` file it cannot process it itself.  
- **PHP-FPM (FastCGI Process Manager)** is the program that actually executes PHP code. It listens on a socket or port, waits for requests, runs the PHP script, and sends the result back.  
- **Together**: Nginx receives the request → if it’s PHP, Nginx forwards it to PHP-FPM → PHP-FPM runs it and returns HTML → Nginx sends it to the client.

This separation makes the stack:
- Faster at serving static files than Apache with mod_php
- Easier to scale (tune Nginx and PHP independently)
- More common in modern PHP deployments (WordPress, Laravel, etc.)

---

## 1. Install Nginx
```bash
sudo dnf -y install nginx
sudo systemctl enable --now nginx
```

---

## 2. Install PHP-FPM (PHP 8.2)
Enable and install the PHP module from AppStream:
```bash
sudo dnf -y module reset php
sudo dnf -y module enable php:8.2
sudo dnf -y install php-fpm php-mysqlnd
```

Enable and start PHP-FPM:
```bash
sudo systemctl enable --now php-fpm
```

---

## 3. Configure PHP-FPM
Open the default pool config:
```bash
sudo vim /etc/php-fpm.d/www.conf
```

Set the socket path and user/group so Nginx can talk to PHP-FPM:
```
listen = /var/run/php-fpm/default.sock
listen.owner = nginx
listen.group = nginx
user = nginx
group = nginx
```

Create the socket directory:
```bash
sudo mkdir -p /var/run/php-fpm
```

Restart PHP-FPM:
```bash
sudo systemctl restart php-fpm
```

---

## 4. Configure Nginx
Edit the main config:
```bash
sudo vim /etc/nginx/nginx.conf
```

Inside the `http { ... }` block, add:
```nginx
    server {
        listen 8094;
        root /var/www/html;
        index index.php index.html;

        location / {
            try_files $uri $uri/ =404;
        }

        location ~ \.php$ {
            include /etc/nginx/fastcgi_params;
            fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
            fastcgi_pass unix:/var/run/php-fpm/default.sock;
        }
    }
```

Test and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## 5. Test the Setup
Create a simple PHP file:
```bash
echo "<?php phpinfo(); ?>" | sudo tee /var/www/html/info.php
```

Access it:
```bash
curl http://localhost:8094/info.php
```

You should see the PHP info output.
