# IPTables Installation and Configuration Guide

This guide explains how to install, configure, and persist iptables rules on CentOS (or RHEL-based) systems.  
It is intended as a reference for common use cases such as restricting access to specific ports and allowing only trusted hosts.

---

## 1. Install iptables

On CentOS:
```bash
sudo yum -y install iptables iptables-services
sudo systemctl enable iptables
sudo systemctl start iptables
```

---

## 2. Basic Concepts
- **Chains**: INPUT (incoming traffic), OUTPUT (outgoing traffic), FORWARD (traffic routed through host).
- **Policies**: Default action if no rule matches (ACCEPT or DROP/REJECT).
- **Rules**: Match packets based on protocol, port, source/destination, etc.

---

## 3. Common Rule Patterns

### Allow traffic from a specific host to a specific port
```bash
sudo iptables -A INPUT -p tcp -s <IP_ADDRESS> --dport <PORT> -j ACCEPT
```

### Block traffic on a port from all other hosts
```bash
sudo iptables -A INPUT -p tcp --dport <PORT> -j REJECT
```

### Allow SSH (port 22) to prevent lockout
```bash
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
```

### Allow established/related connections
```bash
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
```

### Allow local loopback
```bash
sudo iptables -A INPUT -i lo -j ACCEPT
```

---

## 4. Persisting Rules
- On CentOS/RHEL:
```bash
sudo service iptables save   # saves rules to /etc/sysconfig/iptables
```

---

## 5. Verification
List rules with line numbers:
```bash
sudo iptables -L -n --line-numbers
```

Test connectivity:
```bash
curl -I http://<server>:<PORT>
```

---

## 6. Example Use Cases

### Restrict a web service port (e.g., 3000) to a trusted host
```bash
# Allow from trusted host only
sudo iptables -A INPUT -p tcp -s 192.168.1.100 --dport 3000 -j ACCEPT

# Block all other access to that port
sudo iptables -A INPUT -p tcp --dport 3000 -j REJECT
```

### Restrict Apache (e.g., port 8084) to a load balancer
```bash
sudo iptables -A INPUT -p tcp -s <LBR_IP> --dport 8084 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8084 -j REJECT
```

---

## 7. Resetting Rules
To flush all rules (use with caution):
```bash
sudo iptables -F
```

To set default policy:
```bash
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT ACCEPT
```

---

## Conclusion
IPTables is a powerful firewall tool to control network access on Linux systems.  
Key practices:
- Always allow SSH before applying restrictive rules.
- Explicitly allow required services/ports.
- Persist rules to survive reboots.
- Verify rules with `iptables -L` and connectivity tests.

This guide can be adapted for various ports (`<PORT>`) and hosts (`<IP_ADDRESS>`), such as limiting application access to load balancers or trusted systems.
