# Deploying to AWS

CAFIITK-190. One EC2 instance runs caf-api, caf-worker, mockpay and nginx
(`docker-compose.prod.yml`); PostgreSQL runs on RDS. The backend image and the Alembic
migrations are the ones Docker Compose uses locally (NFR-40). nginx serves HTTPS only
and the Flutter web build from the same origin, so CORS allows only that origin
(NFR-27).

The account is on the AWS Free plan: it cannot be charged, and closes when the USD 100
credit or six months run out. Region: `ap-south-1` (Mumbai).

## 1. Security groups (EC2 → Security Groups)

| Name | Inbound |
|---|---|
| `caf-ec2-sg` | SSH 22 from your IP only; HTTP 80 and HTTPS 443 from anywhere |
| `caf-rds-sg` | PostgreSQL 5432 from `caf-ec2-sg` only |

caf-api (8000) and mockpay (8001) are never opened.

## 2. RDS

Aurora and RDS → Create database:

- Standard create, PostgreSQL 16, template **Free tier**
- Identifier `caf-db`, master username `caf`, a password of letters and digits only
- `db.t4g.micro`, Single-AZ, 20 GB gp3, storage autoscaling off
- Public access **No**, security group `caf-rds-sg` (remove `default`)
- Additional configuration: initial database name `caf`; automated backups 1 day

Note the endpoint once it is Available.

## 3. EC2

Launch instance:

- Ubuntu Server 24.04 LTS, `t3.small` (2 GB; free-tier eligible on this account)
- Key pair `caf-deploy`, security group `caf-ec2-sg`, 20 GB gp3

Then Elastic IPs → Allocate → Associate with the instance, so the address survives a
restart.

## 4. Hostname

Let's Encrypt needs a name, not an IP. Without a domain, use
`<elastic-ip-with-dashes>.sslip.io` (for `13.200.1.2`, `13-200-1-2.sslip.io`), which
resolves to that IP with no setup. If certbot refuses it, register a free DuckDNS name
pointing at the Elastic IP instead.

## 5. Prepare the instance

```sh
ssh -i ~/Downloads/caf-deploy.pem ubuntu@<elastic-ip>

sudo apt update && sudo apt install -y docker.io docker-compose-v2 certbot postgresql-client
sudo usermod -aG docker ubuntu && exit   # log in again for the group to apply

git clone -b develop https://github.com/XForce-IITK/Caf-IITK.git && cd Caf-IITK
cp deploy/.env.production.example .env && chmod 600 .env
nano .env   # CAF_HOST, CAF_DATABASE_URL, CAF_JWT_SECRET (openssl rand -base64 48), seed passwords

sudo certbot certonly --standalone -d <CAF_HOST> --agree-tos -m <team email> -n
```

The certificate lasts 90 days, longer than the demo period.

## 6. Build the client (on your laptop)

The instance is too small to build Flutter, so build locally and copy the result:

```sh
cd app
flutter build web --release --dart-define=API_BASE_URL=https://<CAF_HOST>
rsync -az --delete -e "ssh -i ~/Downloads/caf-deploy.pem" build/web/ ubuntu@<elastic-ip>:Caf-IITK/app/build/web/
```

## 7. Start

On the instance, in `Caf-IITK/`:

```sh
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # all running, api healthy
docker compose -f docker-compose.prod.yml logs migrate
```

`migrate` runs `alembic upgrade head` and seeds the Administrator and Kitchen accounts.
The containers restart on their own after a reboot.

## 8. Check

```sh
curl -sI http://<CAF_HOST>/ | head -1                 # 301 to https
curl -s https://<CAF_HOST>/ready                       # {"status":"ready"}
curl -s -o /dev/null -w '%{http_code}\n' https://<CAF_HOST>/metrics   # 404
curl -sI -H 'Origin: https://evil.example' https://<CAF_HOST>/api/v1/menu | grep -i access-control   # nothing
```

Database roles (E81), on the instance with the RDS URL minus `+psycopg`:

```sh
psql "postgresql://caf:<pw>@<rds-endpoint>:5432/caf?sslmode=require" -c "
  SELECT pg_has_role(current_user, 'caf_app', 'USAGE'),
         pg_has_role(current_user, 'caf_agent', 'USAGE'),
         has_table_privilege('caf_app', 'audit_log', 'UPDATE');"   # t | t | f
```

Then in a browser: log in as the Administrator, change an item, and start an agent run.

Metrics are only on the instance: `ssh -L 8000:127.0.0.1:8000 ...` and open
`http://localhost:8000/metrics`.

## Updating

```sh
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

Rebuild and copy the client (step 6) when `app/` changed.

## After the demo

Delete the EC2 instance, release the Elastic IP, and delete the RDS database (no final
snapshot), so nothing keeps drawing on the credit.
