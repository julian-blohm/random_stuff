# Setting up Apache Tomcat on CentOS

This guide provides a step-by-step approach for installing and configuring Apache Tomcat on CentOS.  
It is intended for lab environments and troubleshooting references.

---

## 1. Install Tomcat
The CentOS package manager provides Tomcat and its dependencies (including Java).
```bash
sudo yum -y install tomcat
```

---

## 2. Configure Tomcat Port
By default, Tomcat listens on **8080**. You may change it to any other port.

Edit the connector configuration:
```bash
sudo sed -i 's/port="8080"/port="<your-port>"/' /etc/tomcat/server.xml
```

- Replace `<your-port>` with the desired port number (e.g., 3000).
- Ensure no other service is bound to that port.

---

## 3. Deploy Application
Tomcat serves web applications from the `/var/lib/tomcat/webapps/` directory.

### Remove any old ROOT app (optional)
```bash
sudo rm -rf /var/lib/tomcat/webapps/ROOT
```

### Deploy your WAR
```bash
sudo mv /tmp/ROOT.war /var/lib/tomcat/webapps/ROOT.war
```

### Set correct ownership
```bash
sudo chown tomcat:tomcat /var/lib/tomcat/webapps/ROOT.war
```

---

## 4. Start and Enable Tomcat
Restart the service and enable auto-start on boot:
```bash
sudo systemctl restart tomcat
sudo systemctl enable tomcat
```

---

## 5. Firewall and SELinux Considerations
### Firewall
If `firewalld` or `iptables` is enabled, allow the chosen port:
```bash
# firewalld
sudo firewall-cmd --permanent --add-port=<your-port>/tcp
sudo firewall-cmd --reload

# iptables
sudo iptables -I INPUT -p tcp --dport <your-port> -j ACCEPT
sudo service iptables save
```

### SELinux
If SELinux is in **Enforcing** mode, allow Tomcat to bind to the new port:
```bash
sudo semanage port -a -t http_port_t -p tcp <your-port> 2>/dev/null || sudo semanage port -m -t http_port_t -p tcp <your-port>
```

---

## 6. Verification
Wait a few seconds for Tomcat to deploy the WAR, then test:

- On the server:
```bash
curl -I http://localhost:<your-port>
```

- From a remote host:
```bash
curl -I http://<server-hostname>:<your-port>
```

Expected: `HTTP/1.1 200 OK`

---

## 7. Common Issues
- **Port Conflict**: Ensure no other service is using the configured port.
- **403/404 Errors**: Check that the WAR was deployed as `ROOT.war` and exploded under `/var/lib/tomcat/webapps/ROOT`.
- **Firewall/SELinux**: Verify that the port is allowed.
- **Logs**: For deployment or startup issues, review:
  ```bash
  tail -n 100 /var/log/tomcat/catalina.out
  ```
