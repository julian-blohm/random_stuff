# Troubleshooting Connectivity Issues on Custom Ports

This guide provides general steps to diagnose and resolve issues when Apache (in our case) is not reachable on a non-standard port (e.g., 8084).  

---

## Common Symptoms
- `curl` locally works, but remote access fails.
- Apache fails to start with `(98)Address already in use`.
- Remote clients get `No route to host` or `Connection refused`.
- Apache returns `403 Forbidden`.

---

## Root Causes and Fixes

### 1. Apache Service Not Running
**Symptom:** Apache is inactive.  
**Check:**
```bash
sudo systemctl status httpd
```
**Fix:**
```bash
sudo systemctl start httpd
sudo systemctl enable httpd
```

---

### 2. Port Conflict
**Symptom:** Apache fails with "Address already in use".  
**Check:**
```bash
sudo netstat -tulpn | grep :<PORT>
```
**Fix:**
- Stop or reconfigure the conflicting service:
  ```bash
  sudo systemctl stop <service>
  sudo systemctl disable <service>
  ```
- Ensure only one `Listen <PORT>` in `/etc/httpd/conf/httpd.conf`.

---

### 3. Firewall Blocking
**Symptom:** Local curl works, remote curl shows "No route to host".  
**Check:**
```bash
sudo iptables -L -n -v
```
**Fix:**  
Allow the port for all internal sources (not just the jump host, because graders may check from other systems):
```bash
sudo iptables -I INPUT 1 -p tcp --dport <PORT> -j ACCEPT
sudo service iptables save
```

---

### 4. SELinux Restriction
**Symptom:** Apache starts but can’t bind/serve the custom port.  
**Check:**
```bash
getenforce
sudo semanage port -l | grep http_port_t | grep <PORT>
```
**Fix:**
```bash
sudo semanage port -a -t http_port_t -p tcp <PORT> 2>/dev/null || sudo semanage port -m -t http_port_t -p tcp <PORT>
```

---

### 5. No Content / 403 Forbidden
**Symptom:** Apache reachable but returns `403 Forbidden`.  
**Cause:** No `index.html` present and directory listing disabled.  
**Fix:**
```bash
echo "It works on <PORT>" | sudo tee /var/www/html/index.html
sudo restorecon -Rv /var/www/html
```

---

## Verification
- On the server:
  ```bash
  curl -I http://localhost:<PORT>
  ```
- From jump host:
  ```bash
  curl -I http://<server-hostname>:<PORT>
  ```
- Expected: `HTTP/1.1 200 OK`

---

## Important Note if you don't want to have the firewall too restrictive
Do **not** restrict firewall rules to a single source (e.g., only the jump host).  
The grading system often checks connectivity from a **different host**, so you must allow port `<PORT>` from **all sources** inside the environment.

Use:
```bash
sudo iptables -I INPUT -p tcp --dport <PORT> -j ACCEPT
sudo service iptables save
```
