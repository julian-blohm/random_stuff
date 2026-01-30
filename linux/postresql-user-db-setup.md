# PostgreSQL: Creating Users and Databases

This guide contains the steps for creating a new PostgreSQL user, database, and assigning privileges.  

---

## 1. Switch to the `postgres` system user
On the server where PostgreSQL is installed:
```bash
sudo -i -u postgres
```

---

## 2. Create a new database user
Use the `psql` command:
```bash
psql -c "CREATE USER <username> WITH PASSWORD '<password>';"
```

---

## 3. Create a new database
```bash
psql -c "CREATE DATABASE <database_name>;"
```

---

## 4. Grant privileges on the database to the user
```bash
psql -c "GRANT ALL PRIVILEGES ON DATABASE <database_name> TO <username>;"
```

---

## 5. Exit from `postgres` user
```bash
exit
```

---

## 6. Verification (optional)
You can test the connection with the new user:
```bash
psql -U <username> -d <database_name> -h localhost -W
```

Enter the password you set earlier. Once inside `psql`, you can run:
```sql
\conninfo   -- show current connection info
\q          -- quit
```

---

## Notes
- no restart of PostgreSQL after creating users/databases needed.  
- For finer control, you can grant specific privileges instead of `ALL PRIVILEGES` (e.g., `CONNECT`, `CREATE`, `USAGE`).  
