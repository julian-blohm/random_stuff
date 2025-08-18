
```bash
# install tomcat
sudo yum -y install tomcat

# use the port you want
sudo sed -i 's/port="8080"/port="<your-port>"/' /etc/tomcat/server.xml

# remove anything in the webapps folder (optional)
sudo rm -rf /var/lib/tomcat/webapps/ROOT

# place your war file in the webapps folder
sudo mv /tmp/ROOT.war /var/lib/tomcat/webapps/ROOT.war

# give permissions to tomcat
sudo chown tomcat:tomcat /var/lib/tomcat/webapps/ROOT.war

# restart and enable tomcat
sudo systemctl restart tomcat
sudo systemctl enable tomcat
```
