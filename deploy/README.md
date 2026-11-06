# Deploying to AWS

CAFIITK-190. One EC2 instance runs caf-api, caf-worker, mockpay and nginx
(`docker-compose.prod.yml`); PostgreSQL runs on RDS. The backend image and the Alembic
migrations are the ones Docker Compose uses locally (NFR-40). CloudFront serves HTTPS
with its own certificate and forwards to nginx, which serves the Flutter web build and
the API from the same origin, so CORS allows only that origin (NFR-27).

```
browser ──HTTPS──▶ CloudFront ──HTTP──▶ EC2 nginx :80 ──▶ caf-api ──▶ RDS PostgreSQL 16
                                                         caf-worker, mockpay (internal)
```

Why CloudFront and not Let's Encrypt: the campus network resolves sslip.io, nip.io,
traefik.me and DuckDNS names to a block page, and Let's Encrypt refuses
`amazonaws.com` names. A `*.cloudfront.net` name has a valid certificate, costs
nothing, and is reachable on campus.

The account is on the AWS Free plan: it cannot be charged, and closes when the USD 100
credit or six months run out.

## Current deployment

| | |
|---|---|
| URL | https://dh3nmzc5y7ht8.cloudfront.net |
| Region | `ap-southeast-2` (Sydney) |
| EC2 | `caf-server`, `t3.small`, Ubuntu 24.04, Elastic IP 13.211.39.218 |
| RDS | `caf-db`, PostgreSQL 16, `db.t4g.micro`, Single-AZ, not public |

## 1. Security groups (EC2 → Security Groups)

| Name | Inbound |
|---|---|
| `caf-ec2-sg` | SSH 22 from your IP only; HTTP 80 from the prefix list `com.amazonaws.global.cloudfront.origin-facing` only |
| `caf-rds-sg` | PostgreSQL 5432 from `caf-ec2-sg` only |

caf-api (8000) and mockpay (8001) are never opened. Port 80 must admit only CloudFront:
nginx trusts the last X-Forwarded-For entry, which only CloudFront can set.

## 2. RDS

Aurora and RDS → Create database: Standard create, PostgreSQL **16** (the version the
project is tested on), template Free tier, `db.t4g.micro`, Single-AZ, 20 GB gp3,
storage autoscaling off, public access No, security group `caf-rds-sg`, initial
database name `caf`. Use a master password of letters and digits only. Leave RDS
Extended Support off (it is paid).

## 3. EC2

Ubuntu Server 24.04 LTS, `t3.small`, key pair `caf-deploy`, security group
`caf-ec2-sg`. Allocate an Elastic IP and associate it with the instance.

## 4. CloudFront

Create distribution (Free plan):

- Origin: the instance's public DNS name (`ec2-<ip-with-dashes>.<region>.compute.amazonaws.com`), **HTTP only**, port 80
- Viewer protocol policy: Redirect HTTP to HTTPS
- Allowed methods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
- Cache policy **CachingDisabled**; origin request policy **AllViewer** (forwards `Authorization`)

Note the `*.cloudfront.net` domain once it is Deployed.

## 5. Prepare the instance

```sh
ssh -i ~/Downloads/caf-deploy.pem ubuntu@<elastic-ip>

sudo apt update && sudo apt install -y docker.io docker-compose-v2 postgresql-client git
sudo usermod -aG docker ubuntu && exit   # log in again for the group to apply

git clone https://github.com/XForce-IITK/Caf-IITK.git && cd Caf-IITK
cp deploy/.env.production.example .env && chmod 600 .env
nano .env   # CAF_HOST, CAF_DATABASE_URL, CAF_JWT_SECRET (openssl rand -base64 48), seed passwords
mkdir -p app/build/web   # before Docker would create it as root
```

## 6. Build the client (on your laptop)

The instance is too small to build Flutter, so build locally and copy the result:

```sh
cd app
flutter build web --release --dart-define=API_BASE_URL=https://<cloudfront-domain>
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
H=https://<cloudfront-domain>
curl -sI http://<cloudfront-domain>/ | head -1        # 301 to https
curl -s $H/ready                                       # {"status":"ready"}
curl -s -o /dev/null -w '%{http_code}\n' $H/metrics    # 404
curl -sI -X OPTIONS -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: POST' \
     $H/api/v1/auth/login | head -1                    # 400: foreign origin refused
curl -s -m 5 http://<elastic-ip>/ready || echo blocked # blocked: only CloudFront reaches nginx
```

Database roles (E81), on the instance:

```sh
docker compose -f docker-compose.prod.yml exec -T api python -c "
from sqlalchemy import create_engine, text
from app.core.config import get_settings
with create_engine(get_settings().database_url).connect() as c:
    print(c.execute(text('''SELECT pg_has_role(current_user, 'caf_app', 'USAGE'),
        pg_has_role(current_user, 'caf_agent', 'USAGE'),
        has_table_privilege('caf_app', 'audit_log', 'UPDATE')''')).one())"   # (True, True, False)
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

Disable and delete the CloudFront distribution, delete the EC2 instance, release the
Elastic IP, and delete the RDS database (no final snapshot), so nothing keeps drawing
on the credit.
