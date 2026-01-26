# Kubernetes Cheat Sheet

> Assumes `kubectl` is configured and you’re in the right namespace. Use `-n <ns>` as needed.

---

## 0) Kubectl Basics
```bash
kubectl version --short                     # client/server versions
kubectl config get-contexts                 # see contexts
kubectl config use-context <ctx>            # switch context

kubectl get ns                              # list namespaces
kubectl get nodes                           # list nodes
kubectl get all                             # common workload objects
kubectl get pods,deploy,svc,cm,secret,pvc,pv  # specific kinds
kubectl get pods -l app=<lbl> -o wide       # filter by label
kubectl get pod <pod-name> -o yaml > /<path>/output-file.yaml # export pod manifest

kubectl describe <kind> <name>              # detailed object view/events
kubectl logs <pod> [-c <container>] -f      # stream logs
kubectl exec -it <pod> -- sh                # exec into a pod (or bash)

kubectl apply -f file.yaml                  # create/update from manifest
kubectl delete -f file.yaml                 # delete from manifest

kubectl cp -r /local/folder <pod-name>:/path/in/container # copy files into container/pod; 
# use -c with container name to copy local file only to that specific container
```

Troubleshoot Deployments
```bash
kubectl get deploy,rs,pod -o wide
kubectl describe deploy <name>
kubectl describe rs -l app=<label>
kubectl describe pod <pod>
kubectl logs <pod> [-c container]
kubectl get events --sort-by=.metadata.creationTimestamp
kubectl rollout status deploy/<name>
kubectl rollout undo deploy/<name>
```
Common issues: bad image, bad command/args, wrong selectors, port conflicts, PVC pending/bound, issues with volume mounts.

---

## 1) Pod Creations
**Declarative way using pod.yaml**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: demo
  labels:
    app: demo-pod
spec:
  containers:
  - name: app
    image: nginx:alpine
    ports:
    - containerPort: 80
```
```bash
kubectl apply -f pod.yaml
kubectl port-forward pod/demo-pod 8080:80
```

**Imperative way using command**
```bash
kubectl run demo --image=nginx:alpine --port=80 --labels="app=demo-pod"
kubectl port-forward pod/demo-pod 8080:80
```

---

## 2) Deployment & Rollout
**deploy.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-deploy
spec:
  replicas: 3
  selector:
    matchLabels: { app: web }
  template:
    metadata:
      labels: { app: web }
    spec:
      containers:
      - name: web
        image: nginx:1.25-alpine
        ports: [{ containerPort: 80 }]
```
```bash
# deploy 
kubectl apply -f deploy.yaml    
# check status
kubectl rollout status deploy/web-deploy

# Update image:
kubectl set image deploy/web-deploy web=nginx:1.25.3-alpine
# Get history of changes (if change cause info is used)
kubectl rollout history deploy/web-deploy

# Roll back to earlier version:
kubectl rollout undo deploy/web-deploy                 # to previous
kubectl rollout undo deploy/web-deploy --to-revision=2 # to specific
```

**Imperative way using command**
```bash
kubectl create deploy web-deploy --image=nginx:1.25-alpine --replicas=3
kubectl set image deploy/web-deploy web=nginx:1.25.3-alpine  # rolling update
kubectl rollout undo deploy/web-deploy
```

---

## 3) Resource Requests/Limits
**Declarativ** (add under container spec)
```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "256Mi"
```
**Imperative**
```bash
kubectl set resources deploy/web-deploy \
  --requests=cpu=100m,memory=128Mi \
  --limits=cpu=500m,memory=256Mi
```

---

## 4) Services / Expose
```bash
# Expose a deployment on a NodePort
kubectl expose deploy/web-deploy --port=80 --target-port=80 --type=NodePort --name web-svc
kubectl get svc web-svc -o wide   # see nodePort
```
**YAML (ClusterIP)**:
```yaml
apiVersion: v1
kind: Service
metadata: { name: web-svc }
spec:
  selector: { app: web }
  ports: [{ port: 80, targetPort: 80 }]
  type: ClusterIP
```

---

## 5) Volumes
### EmptyDir (shared between containers in a Pod)
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: volume-share-nautilus
spec:
  volumes: [{ name: volume-share, emptyDir: {} }]
  containers:
    - name: volume-container-nautilus-1
      image: fedora:latest
      command: ["sleep", "infinity"]
      volumeMounts: [{ name: volume-share, mountPath: /tmp/beta }]
    - name: volume-container-nautilus-2
      image: fedora:latest
      command: ["sleep", "infinity"]
      volumeMounts: [{ name: volume-share, mountPath: /tmp/demo }]
```

### PersistentVolume + PVC
**pv.yaml**
```yaml
apiVersion: v1
kind: PersistentVolume
metadata: { name: pv-data }
spec:
  capacity: { storage: 1Gi }
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  hostPath: { path: /data/pv }        # lab-friendly; in cloud use storage class
```
**pvc.yaml**
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: pvc-data }
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 1Gi } }
```
Mount in a Pod/Deployment:
```yaml
volumes: [{ name: data, persistentVolumeClaim: { claimName: pvc-data } }]
containers:
- name: app
  volumeMounts: [{ name: data, mountPath: /var/lib/app }]
```

---

## 6) Init Containers
```yaml
initContainers:
- name: init-wait
  image: busybox:1.36
  command: ["sh","-c","until nslookup db; do sleep 2; done"]
containers:
- name: app
  image: nginx:alpine
```
> Init containers must **succeed** before main containers start.

---

## 7) Secrets
Create secrets:
```bash
kubectl create secret generic db-cred   --from-literal=USER=appuser   --from-literal=PASSWORD='S3cureP@ss!'
```

Mount secret as file:
```yaml
volumes: [{ name: secretvol, secret: { secretName: db-cred } }]
volumeMounts: [{ name: secretvol, mountPath: /secrets, readOnly: true }]
```

Use envs and print them:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: print-envars-greeting
spec:
  restartPolicy: Never
  containers:
  - name: print-env-container
    image: bash
    ports:
    - containerPort: 80
    env:
    - name: GREETING
      value: "Welcome to"
    - name: COMPANY
      value: "MyCompany"
    - name: GROUP
      value: "Datacenter"
    command: ["/bin/sh", "-c", 'echo "$(GREETING) $(COMPANY) $(GROUP)"']
```


---

## 8) Sidecar Containers
```yaml
apiVersion: v1
kind: Pod
metadata: { name: webserver }
spec:
  volumes: [{ name: shared-logs, emptyDir: {} }]
  containers:
  - name: nginx-container
    image: nginx:latest
    volumeMounts: [{ name: shared-logs, mountPath: /var/log/nginx }]
  - name: sidecar-container
    image: ubuntu:latest
    command: ["sh","-c","while true; do cat /var/log/nginx/access.log /var/log/nginx/error.log; sleep 30; done"]
    volumeMounts: [{ name: shared-logs, mountPath: /var/log/nginx }]
```

---

## 10) Example: Nginx Web
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: nginx-deploy }
spec:
  replicas: 3
  selector: { matchLabels: { app: nginx } }
  template:
    metadata: { labels: { app: nginx } }
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports: [{ containerPort: 80 }]
---
apiVersion: v1
kind: Service
metadata: { name: nginx-svc }
spec:
  type: NodePort
  selector: { app: nginx }
  ports: [{ port: 80, targetPort: 80, nodePort: 30011 }]
```

---

## 11) App Samples

### Redis Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: redis }
spec:
  replicas: 1
  selector: { matchLabels: { app: redis } }
  template:
    metadata: { labels: { app: redis } }
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports: [{ containerPort: 6379 }]
---
apiVersion: v1
kind: Service
metadata: { name: redis }
spec:
  selector: { app: redis }
  ports: [{ port: 6379, targetPort: 6379 }]
  type: ClusterIP
```

### MySQL / MariaDB (66) with PVC + Secret
```bash
kubectl create secret generic mysql-pass --from-literal=MYSQL_ROOT_PASSWORD='RootP@ss1'   --from-literal=MYSQL_PASSWORD='AppP@ss1' --from-literal=MYSQL_USER='appuser'   --from-literal=MYSQL_DATABASE='appdb'
```
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: mysql-pvc }
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 1Gi } }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: mysql }
spec:
  selector: { matchLabels: { app: mysql } }
  template:
    metadata: { labels: { app: mysql } }
    spec:
      containers:
      - name: mysql
        image: mariadb:10.11
        envFrom: [{ secretRef: { name: mysql-pass } }]
        ports: [{ containerPort: 3306 }]
        volumeMounts: [{ name: data, mountPath: /var/lib/mysql }]
      volumes: [{ name: data, persistentVolumeClaim: { claimName: mysql-pvc } }]
---
apiVersion: v1
kind: Service
metadata: { name: mysql }
spec:
  selector: { app: mysql }
  ports: [{ port: 3306, targetPort: 3306 }]
```

### Guestbook (frontend + redis)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: guestbook-frontend }
spec:
  replicas: 2
  selector: { matchLabels: { app: guestbook } }
  template:
    metadata: { labels: { app: guestbook } }
    spec:
      containers:
      - name: frontend
        image: gcr.io/google-samples/gb-frontend:v5
        env: [{ name: GET_HOSTS_FROM, value: dns }]
        ports: [{ containerPort: 80 }]
---
apiVersion: v1
kind: Service
metadata: { name: guestbook-frontend }
spec:
  selector: { app: guestbook }
  ports: [{ port: 80, targetPort: 80 }]
  type: NodePort
```
Use the **Redis** service created earlier, or add it as in the Redis example.

### Grafana minimal setup
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: grafana-deployment-devops }
spec:
  replicas: 1
  selector: { matchLabels: { app: grafana } }
  template:
    metadata: { labels: { app: grafana } }
    spec:
      containers:
      - name: grafana
        image: grafana/grafana:10.1.0
        ports: [{ containerPort: 3000 }]
---
apiVersion: v1
kind: Service
metadata: { name: grafana }
spec:
  selector: { app: grafana }
  ports: [{ port: 3000, targetPort: 3000, nodePort: 32000 }]
  type: NodePort
```

---

## 12) Imperative Shortcuts (handy)
```bash
kubectl run tmp --image=busybox:1.36 -it --rm -- sh
kubectl create deploy web --image=nginx:alpine --replicas=2
kubectl set image deploy/web web=nginx:1.25.3-alpine
kubectl scale deploy/web --replicas=5
kubectl expose deploy/web --port=80 --target-port=80 --type=NodePort
```

---

## 13) Quick Debug Flow
```bash
kubectl get pods -o wide
kubectl describe pod <pod>
kubectl logs <pod> [-c <container>] --previous
kubectl get events --sort-by=.lastTimestamp
kubectl get pvc,pv
kubectl get rs,deploy
```
Common fixes: correct image/tag; fix `volumeMounts.name` vs `volumes.name`; ensure PVC is Bound; Service selector matches Pod labels; correct container `command/args`.

---

**Tip:** In lab tasks that require external access, use `NodePort` service and hit `NODE_IP:nodePort`. For local-only testing, `kubectl port-forward` is fastest.
