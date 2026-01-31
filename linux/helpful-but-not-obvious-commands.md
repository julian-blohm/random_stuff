
Colection of some commands i usually forget but help me sometimes.

## Non-interactive sudo for a one-off install
Use a password from an env var to run a single command via sudo (useful in scripts).

```
MY_PASSWORD="password"
echo $MY_PASSWORD | sudo -S yum install <my super package>
```

## Find large files quickly
List the 20 largest files under the current directory.

```
find . -type f -printf "%s\t%p\n" | sort -nr | head -20
```

## Quick per-folder size overview
See which directories are taking space.

```
du -sh ./* | sort -h
```

## See what is listening on a port
Identify the process bound to a given port.

```
sudo lsof -iTCP:8080 -sTCP:LISTEN -n -P
```

## Follow logs and filter live
Tail a log and show only matching lines as they arrive.

```
tail -f /var/log/syslog | grep --line-buffered -i "error"
```

## Systemd: show failed services
Quick health check for services that did not start.

```
systemctl --failed
```

## Journalctl: last boot logs
See logs from the previous boot only.

```
journalctl -b -1
```

## Retry a flaky command
Retry up to 5 times with a 5s backoff between attempts.

```
for i in {1..5}; do <command> && break; sleep 5; done
```

## Download and show HTTP headers
Useful for debugging redirects, caching, and auth.

```
curl -I -L https://example.com
```

## SCP with port and key
Copy a file over SSH using a specific key and non-default port.

```
scp -i ~/.ssh/id_ed25519 -P 2222 ./local-file user@host:/remote/path/
```

## Extract a tarball to a specific directory
Keep target dirs tidy.

```
tar -xzf archive.tgz -C /opt/somewhere
```
