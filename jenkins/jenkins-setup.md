# Jenkins setup (CentOS 9 / Fedora) using yum or dnf

## Notes
- Fedora uses `dnf`; CentOS 9 uses `yum` (dnf under the hood).
- The Jenkins docs install Java 21 (OpenJDK) in the examples below.
- Choose one repo: LTS (recommended) or weekly.

[Official Jenkins Setup Guide](https://www.jenkins.io/doc/book/installing/linux/#fedora)

## 1) Install Jenkins LTS (recommended)

### Fedora (dnf)
```bash
sudo wget -O /etc/yum.repos.d/jenkins.repo \
  https://pkg.jenkins.io/rpm-stable/jenkins.repo
sudo dnf upgrade
sudo dnf install fontconfig java-21-openjdk
sudo dnf install jenkins
sudo systemctl daemon-reload
```

### CentOS 9 / RHEL derivatives (yum)
```bash
sudo wget -O /etc/yum.repos.d/jenkins.repo \
  https://pkg.jenkins.io/rpm-stable/jenkins.repo
sudo yum upgrade
sudo yum install fontconfig java-21-openjdk
sudo yum install jenkins
sudo systemctl daemon-reload
```

## 2) Start and enable Jenkins
```bash
sudo systemctl enable jenkins
sudo systemctl start jenkins
sudo systemctl status jenkins
```

## 3) (Optional) Open firewall if you need remote access
```bash
YOURPORT=8080
PERM="--permanent"
SERV="$PERM --service=jenkins"
sudo firewall-cmd $PERM --new-service=jenkins
sudo firewall-cmd $SERV --set-short="Jenkins ports"
sudo firewall-cmd $SERV --set-description="Jenkins port exceptions"
sudo firewall-cmd $SERV --add-port=$YOURPORT/tcp
sudo firewall-cmd $PERM --add-service=jenkins
sudo firewall-cmd --zone=public --add-service=http --permanent
sudo firewall-cmd --reload
```

## 4) Initial admin setup
- Browse to http://localhost:8080
- Get the initial admin password:
```bash
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```
- Paste it into the Unlock Jenkins page, install suggested plugins,
  then create the first administrator user.

## 5) Weekly release (optional)
Use the weekly repo instead of rpm-stable:
```
https://pkg.jenkins.io/rpm/jenkins.repo
```

## Troubleshooting: Port 8080 already in use
If Jenkins fails to start with an “Address already in use” error, find what is
listening on port 8080 and either stop it or change Jenkins’ port.

Check which process is using 8080:
```bash
sudo netstat -ltnp | grep :8080
# or
sudo lsof -iTCP:8080 -sTCP:LISTEN
```

Change Jenkins to a different port (example: 8081):
```bash
sudo sed -i 's/^JENKINS_PORT=.*/JENKINS_PORT="8081"/' /etc/sysconfig/jenkins
sudo systemctl daemon-reload
sudo systemctl restart jenkins
```

Note: On training hosts, `ttyd` often uses port 8080 for the web terminal, so
changing Jenkins’ port is safer than stopping `ttyd`.
