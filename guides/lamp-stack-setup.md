# Setting up a LAMP Stack (Apache, MariaDB, PHP) on CentOS/RHEL

This guide provides general steps for setting up a basic LAMP stack (Linux, Apache, MariaDB, PHP).  

---

## 1. Install Apache and PHP
```bash
sudo yum -y install httpd php php-mysqlnd
```
`php-mysqlnd` is the native driver for php

---

## 2. Configure Apache to Listen on a Custom Port
Edit `/etc/httpd/conf/httpd.conf` or use `sed`:
```bash
sudo sed -i 's/^Listen .*/Listen <port>/' /etc/httpd/conf/httpd.conf
```
Replace `<port>` with the desired port (e.g., 6400).

Start and enable Apache:
```bash
sudo systemctl enable --now httpd
```

---

## 3. Install MariaDB
```bash
sudo yum -y install mariadb-server
sudo systemctl enable --now mariadb
```

---

## 4. Create Database and User
Run the following commands to create a database, user, and grant privileges:

```bash
mysql -u root -e "
CREATE DATABASE <database_name>;
CREATE USER '<db_user>'@'%' IDENTIFIED BY '<password>';
GRANT ALL PRIVILEGES ON <database_name>.* TO '<db_user>'@'%';
FLUSH PRIVILEGES;
"
```

Replace:
- `<database_name>` → name of your application database (e.g., `app_db`)  
- `<db_user>` → username for the app (e.g., `app_user`)  
- `<password>` → strong password  

---

## 5. Verification

- Confirm Apache is listening on the configured port:
```bash
sudo netstat -tulpn | grep httpd
```

- Test PHP + DB connectivity by placing a small PHP file in `/var/www/html/test.php`:
```php
<?php
$mysqli = new mysqli("db_host", "db_user", "db_password", "db_name");
if ($mysqli->connect_errno) {
    echo "Failed to connect to DB: " . $mysqli->connect_error;
} else {
    echo "App is able to connect to the database using user db_user";
}
?>
```

Access it:
```bash
curl http://localhost:<port>/test.php
```
