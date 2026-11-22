# DailyCommit dev on an Azure Ubuntu VM

This deployment is **DEV only** at **https://dev.dailycommit.co.za**: Caddy terminates HTTPS in front of the existing community/public application image, PostgreSQL and Redis on the same Azure VM. The root Dockerfile is unchanged: web + FastAPI + collab still run behind the image's internal Nginx on port 80. Caddy is the **only service publishing host TCP ports 80 and 443**. No AWS, Render, external database, Judge0 or application functionality changes are included.

These files prepare the HTTPS deployment; updating them does not deploy, change DNS or change GitHub variables. Do not push/merge to the auto-deploying `dailycommit-dev` branch until you are ready for the next live deployment.

## Flow and files

A push (including a merged PR) to `dailycommit-dev` runs `.github/workflows/deploy-dev.yml`:

1. Verify that active GitHub rules enforce approving PR review, all required checks and an up-to-date branch. Full CI/deployment tests run on the PR, not again on the merge push. Missing or unreadable rules stop before publishing or contacting the VM.
2. Build `./Dockerfile` for `linux/amd64`, with `LEARNHOUSE_PUBLIC=true`.
3. Publish `ghcr.io/<lowercase owner>/<lowercase repository>:sha-<full commit SHA>`, `:dev`, and `:latest`. For this repo the image is `ghcr.io/dailycommitapp/dailycommitweb`. Here `latest` is a **dev alias**, not a production release. Docker tags cannot contain `/`.
4. Connect to the Ubuntu VM using SSH with a pre-verified host key. Send only the deployment bundle, not a git clone or local database.
5. Authenticate to GHCR using temporary VM credentials; pull the **build's immutable digest**, not a moving `latest` tag.
6. Validate stable secrets, pull Caddy, and validate its configuration before stopping the app or changing schema. Start/wait for PostgreSQL and Redis and back up PostgreSQL before app/schema changes.
7. On an existing versioned database, stop only the app and apply the new image's native Alembic migrations before startup. On a brand-new database, let LearnHouse perform its native schema/org/admin bootstrap and stamp that exact image's Alembic heads afterward.
8. Stop/recreate the legacy HTTP app as needed to free host port 80. Start Caddy first, then update/wait for the internal app's API/database, frontend and collab readiness. Verify schema heads and the initial admin.
9. Verify HTTPS certificate trust, hostname and API readiness through Caddy before recording the accepted image/commit. No insecure TLS bypass is used.

Every PR runs the `CI` workflow (`.github/workflows/ci.yml`). It calls the existing API/web tests, lint/type checks, lockfile checks and Docker build validation as reusable workflows, once each, regardless of file paths. PRs targeting `dailycommit-dev` also call `validate-dev.yml` for deployment helper/Compose/Caddy validation. A final job named **CI passed** runs even when a dependency fails, and succeeds only when all applicable jobs succeeded. Failed, cancelled, unexpectedly skipped or missing jobs block it. Dev validation may be skipped only for PRs into another base branch.

The six reusable checks retain their existing direct push/manual triggers for other branches but no longer have independent PR triggers, preventing duplicate runs. Their concurrency groups use distinct prefixes so sibling workflows do not cancel one another. The lockfile job retains its existing dependency-bot auto-fix permissions and optional token; other jobs do not receive that secret. Full-project web lint remains report-only for existing lint debt, with type checks and strict PR lint unchanged. E2E remains an independent manual/nightly workflow that builds a temporary DailyCommit image from the checked-out source.

After approval and merge, only the lightweight `Verify PR protections` job, publishing build and VM deployment run. They do not rerun the PR CI suite. Runtime migration, backup, health and HTTPS checks remain mandatory on the VM. Manual deployment runs are restricted to `dailycommit-dev` and must pass the same branch-rule guard. Deployment concurrency never automatically cancels a live update, and `flock` serializes VM updates.

### Required GitHub rules before deploying

After these changes are pushed and a PR has run CI, edit the active ruleset for `dailycommit-dev` in **Settings → Rules → Rulesets**:

1. Keep **Require a pull request before merging** and at least one approving review.
2. Enable **Require status checks to pass**.
3. Add just the GitHub Actions check **CI passed**. If the old individual checks are selected, remove them from the required list after switching to the combined check; they still run under CI.
4. Enable **Require branches to be up to date before merging** and save the ruleset.

GitHub may not offer the new check until it has run on a PR. There is no separate new Secret. Do not add the nightly E2E job, the publishing build or Azure deployment as pre-merge requirements.

`deploy/dev/verify_pr_gate.py` now requires `CI passed` plus the existing strict up-to-date and approving-review rules. It only reads GitHub rules; these repository changes do not edit the ruleset. A target-branch update requires updating the PR and passing CI against the current target branch before merging. Deployment deliberately stops if the combined check is not configured as required.

## One-time VM preparation

Use an x86_64/amd64 Ubuntu VM. Docker Engine is already installed per project context; also install the **Docker Compose plugin >= 2.30**, Python 3, and util-linux (`flock`). Raw env-file parsing requires Compose 2.30+. Install `curl` for the final HTTPS verification. Verify:

```sh
docker version
docker compose version
python3 --version
command -v flock
curl --version
uname -m
```

Create/use a dedicated deployment user. As an authorized VM administrator, replace `DEPLOY_USER` with its actual Linux username:

```sh
sudo usermod -aG docker DEPLOY_USER
sudo install -d -m 750 -o DEPLOY_USER -g DEPLOY_USER /opt/dailycommit
```

Reconnect that user so group membership takes effect, and confirm `docker info` works without an interactive sudo prompt. Docker group membership provides powerful host access: use a dedicated account/key for this VM. Install the public half of the deployment SSH key in that user's `~/.ssh/authorized_keys`. GitHub receives only the private key as a Secret; it must be an automation key that does not prompt for a passphrase.

Allow SSH port 22 from the intended runner/network. Before the first HTTPS deployment:

- Point the public DNS **A record** for `dev.dailycommit.co.za` to this VM's public IPv4 address. If an AAAA record exists, its IPv6 route must also reach this VM; remove/correct stale records.
- Make TCP **80 and 443** reachable from the internet through both the Azure NSG and any Ubuntu firewall. Caddy's automatic HTTP/TLS ACME challenges need external reachability; restricting these ports only to tester IPs will prevent certificate issuance/renewal. Keep SSH restricted separately.
- Ensure outbound DNS and HTTPS access for Caddy's public certificate authority requests, and ensure no other host service owns 80/443. The deployment stops the old port-80 app only after the database backup and applicable migration checks.
- Do not expose PostgreSQL 5432, Redis 6379, API 9000, collab 4000 or Caddy's admin port 2019 publicly. PostgreSQL is mapped only to `127.0.0.1:5432` on the VM for local access or SSH forwarding; Redis has no host port mapping. Only Caddy binds host 80/443. HTTP redirects to HTTPS automatically. Public application traffic, including `/api/v1`, uploads and `/collab` WebSockets, is forwarded to `app:80` and then the image's existing internal Nginx routes.

Caddy obtains and renews publicly trusted certificates automatically for the configured hostname. No certificate upload, GitHub TLS secret, manual certificate path or DNS-provider API key is needed. Do not use `tls internal` or disable certificate verification for this public hostname.

For SSH trust, obtain the server's public host key through an already trusted connection or Azure console, rather than blindly accepting a key discovered during CI:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
cat /etc/ssh/ssh_host_ed25519_key.pub
```

Set `VM_KNOWN_HOSTS` to a known_hosts line: `<VM_HOST> ssh-ed25519 <server public host key>`. The host portion must match `VM_HOST`. This is the **server host key**, not the deployment user's authorized_keys entry. Do not use StrictHostKeyChecking=no.

## GitHub configuration

In this repository create a GitHub environment named **dev**, allow deployments from `dailycommit-dev`, and store these Actions **Secrets** in that environment (repository-level Secrets also work if intentionally shared):

| Secret | Purpose |
| --- | --- |
| `VM_HOST` | VM public IPv4 address or SSH hostname, without a URL scheme. SSH port 22 is used. |
| `VM_USER` | Dedicated Ubuntu deployment username. |
| `VM_SSH_KEY` | Its private SSH key, preserving line breaks; no passphrase prompt. |
| `VM_KNOWN_HOSTS` | Verified SSH known_hosts entry for that VM. |
| `GHCR_USERNAME` | GitHub username owning the VM's registry access token; not the organization name unless it is actually the credential owner. |
| `GHCR_TOKEN` | Registry token with **read:packages**, access to this repo's GHCR package, and SSO authorization if your organization requires it. Used for VM pulls only. |
| `DEV_ENV_JSON` | JSON object containing runtime credentials described below. |

Set the **dev environment variable** `DEV_PUBLIC_URL` to exactly:

```text
https://dev.dailycommit.co.za
```

The renderer now rejects the former HTTP/IP origin, other hosts, non-default ports, paths, credentials, queries and fragments. `VM_HOST` remains the SSH hostname/IP and does not need to change. Keep the existing `DEV_ENV_JSON` values unchanged: HTTPS does not rotate passwords, JWT keys, internal keys or initial admin credentials.

Inside Docker, Caddy has the network alias `dev.dailycommit.co.za`. Existing server-rendered app requests therefore reach Caddy privately using the **real HTTPS hostname and a normally verified certificate**, without Azure public-IP hairpin routing or a separate internal-only app URL. Public DNS still needs to point at the VM for browsers and certificate-authority validation. The alias changes no application code and creates no public DNS record.

Image publishing uses GitHub's automatic `GITHUB_TOKEN` with `packages: write`, not your long-lived GHCR pull token. Ensure repository Actions policies permit that permission, that the GHCR package is linked to this repo, and that the pull-token account has package access. No external registry namespace is used. All new Actions are pinned to verified official commit SHAs.

### Runtime JSON secret

`DEV_ENV_JSON` must contain the following string keys. Values below are **placeholders**, not working passwords:

```json
{
  "POSTGRES_PASSWORD": "REPLACE_WITH_UNIQUE_RANDOM_VALUE_1",
  "REDIS_PASSWORD": "REPLACE_WITH_UNIQUE_RANDOM_VALUE_2",
  "LEARNHOUSE_AUTH_JWT_SECRET_KEY": "REPLACE_WITH_UNIQUE_RANDOM_VALUE_3",
  "NEXTAUTH_SECRET": "REPLACE_WITH_UNIQUE_RANDOM_VALUE_4",
  "COLLAB_INTERNAL_KEY": "REPLACE_WITH_UNIQUE_RANDOM_VALUE_5",
  "LEARNHOUSE_INITIAL_ADMIN_EMAIL": "your-admin-email@example.com",
  "LEARNHOUSE_INITIAL_ADMIN_PASSWORD": "REPLACE_WITH_A_STRONG_ADMIN_PASSWORD"
}
```

Generate **five different values**, each at least 32 URL-safe characters (64 hexadecimal characters is convenient):

```sh
openssl rand -hex 32
```

Run that separately for each DB/Redis/signing/internal secret and store the values directly in GitHub Secrets. The initial admin password must be at least 12 characters with uppercase, lowercase, a number and a symbol. JSON-escape quotes/backslashes correctly. Values must be single-line. Nothing should be committed to Git, passed as Docker build arguments, uploaded as an Actions artifact or printed in CI logs.

These five persistent secrets must stay stable across deploys. The deployment stores only private fingerprints to detect accidental rotation; a mismatch stops before changing the services. Changing `POSTGRES_PASSWORD` in GitHub does not change an already initialized PostgreSQL user's password. Credential rotation is a separate coordinated operation, not a normal deployment.

Optional email fields, if already configured: `LEARNHOUSE_EMAIL_PROVIDER`, `LEARNHOUSE_SYSTEM_EMAIL_ADDRESS`, `LEARNHOUSE_SYSTEM_EMAIL_SENDER_NAME`, `LEARNHOUSE_RESEND_API_KEY`, `LEARNHOUSE_SMTP_HOST`, `LEARNHOUSE_SMTP_PORT`, `LEARNHOUSE_SMTP_USERNAME`, `LEARNHOUSE_SMTP_PASSWORD`, `LEARNHOUSE_SMTP_USE_TLS`. All values remain strings. Without valid email credentials, mail-dependent features cannot deliver messages. This workflow does not set up an email provider, Google OAuth, AI or Judge0. Do not add unsupported keys to the secret.

The renderer derives these internal URLs automatically:

- PostgreSQL: `postgresql://learnhouse:<secret>@db:5432/learnhouse`.
- Redis (API and collab): `redis://:<secret>@redis:6379/0`.
- Internal API for collab: `http://127.0.0.1:9000` inside the combined app container.
- Browser URLs and WebSocket URL: derived from `DEV_PUBLIC_URL`.

The hosted dev app uses production-safe process/security defaults (`LEARNHOUSE_DEVELOPMENT_MODE=false`), while being labeled environment `dev`. It is single-org, community-only, AI-disabled and HTTPS-aware: `LEARNHOUSE_SSL=true`, `NEXT_PUBLIC_LEARNHOUSE_HTTPS=true`, HTTPS API/backend/login URLs and a `wss://dev.dailycommit.co.za/collab` URL. Allowed origins are restricted to the HTTPS origin. Caddy's forwarded host/protocol headers are preserved by the existing image Nginx, allowing the existing login/cookie behavior to recognize HTTPS. This is not the local development runner or an EE bypass.

## First deployment and first admin

Push/merge the reviewed files and desired app changes into `dailycommit-dev`. The current working branch can differ while preparing changes; no remote deployment happens until the workflow is on and triggered for that branch. Do not blindly commit unrelated local work.

A fresh VM volume is separate from your laptop's database. LearnHouse's existing startup creates **Daily Commit**, slug `default`, and the initial admin using the two initial-admin Secrets. Log in at `<DEV_PUBLIC_URL>/login` using those credentials, then manage courses/users through `/dash`. Later changes to initial-admin Secrets do not reset existing account credentials. Normal account management/reset flows apply after bootstrap. The deployment checks an admin exists before marking the release accepted.

An existing organization without an admin is a partial bootstrap; this deployment reports failure rather than manufacturing an account or rerunning the whole installer against existing data. An existing database without Alembic history is likewise refused unless this exact image owns a recorded fresh-bootstrap marker. For adopting an older LearnHouse installation, back it up, establish its verified baseline using the old running image's migrations, then adopt it deliberately. No new image is blindly stamped over an unknown old schema.

## Persistent data and operations

`docker-compose.dev.yml` runs Caddy, the internal app, pgvector PostgreSQL 16 and password-protected Redis. The app exposes port 80 only to its Docker network; it no longer publishes any host port. PostgreSQL binds only `127.0.0.1:5432` for local/SSH-forwarded access; Redis has no published host ports. Redis uses AOF with `appendfsync everysec` and a persistent `/data` volume; normal restarts preserve it (an abrupt host failure can lose the latest second of writes).

Fixed Docker volumes:

| Volume | Mount |
| --- | --- |
| `dailycommit-dev-postgres` | `/var/lib/postgresql/data` |
| `dailycommit-dev-redis` | `/data` |
| `dailycommit-dev-content` | `/app/api/content` |
| `dailycommit-dev-caddy-data` | `/data` (ACME account, certificates and private keys) |
| `dailycommit-dev-caddy-config` | `/config` (Caddy persisted configuration) |

Caddy loads the tracked, non-secret `deploy/dev/Caddyfile`, copied to `/opt/dailycommit/Caddyfile` and mounted read-only. Its one site proxies **all** application paths to `app:80`, using Caddy's normal WebSocket and forwarded-header handling. TLS keys/certificates are created only in the Caddy data volume on the VM; never copy them into the repo, deployment bundle, image or GitHub Secrets. Preserve both Caddy volumes during updates, restarts and backups. Deleting them can trigger unnecessary reissuance and CA rate limits.

The project name is always `dailycommit-dev`; do not rename it or the volumes casually. No deployment command removes volumes or prunes images. Do **not** run volume-removing Compose teardown commands. App image updates do not delete the database or uploaded content.

`/opt/dailycommit` contains private `app.env`, `db.env`, `redis.env`, the compose file and non-secret `Caddyfile`, `.release.env` (immutable image reference), accepted image/commit files, private backups and migration logs. Runtime env files are required by Docker on the VM; their source of truth is GitHub Secrets. They use mode 0600. Registry login uses a temporary Docker config that is removed after deployment. SSH bundles are private and removed after the run; never publish that directory.

Inspect locally on the VM (do not paste secrets or unrestricted logs into public issues):

```sh
cd /opt/dailycommit
docker compose --project-name dailycommit-dev --env-file .release.env -f docker-compose.dev.yml ps
docker compose --project-name dailycommit-dev --env-file .release.env -f docker-compose.dev.yml logs --tail=100 app caddy
```

Avoid printing the fully rendered `docker compose config`, container environment, runtime env files or registry config to CI logs. `config --quiet` validates without displaying credentials. Docker health checks report unhealthy services; Docker restart policy alone does not restart a still-running but unhealthy process. The workflow fails in that case rather than reporting success.

Caddy's container health check checks its loopback-only admin API, not the upstream app or certificate. This deliberate separation prevents a startup deadlock: app SSR/health can require Caddy's HTTPS endpoint. Caddy has no `depends_on: app healthy` gate. After native database safeguards and releasing the old app's host port, deployment starts Caddy before waiting for app readiness. The proxy is recreated to apply the current read-only Caddyfile bind mount while retaining its certificate/config volumes; this may briefly interrupt existing connections in this single-VM dev stack.

Before accepting a release, the VM uses `curl --resolve dev.dailycommit.co.za:443:127.0.0.1 https://dev.dailycommit.co.za/api/v1/health`. This checks the actual TLS listener and hostname against the normal public CA trust store. `--resolve` only selects the local connection address; it does **not** bypass certificate validation. A bounded retry loop waits for issuance/readiness; no `-k`, `--insecure` or custom CA shortcut is used.

PostgreSQL is dumped with `pg_dump -Fc` before schema/app changes, under `/opt/dailycommit/backups`, mode 0600. Backups remain on this VM; this is not off-VM disaster recovery. Uploaded content has its own volume and should be backed up separately. Monitor disk use and apply an explicit retention policy; the script does not automatically delete old backups or images. DB/Redis base images are not pulled on every app deployment, so service upgrades remain deliberate. Their definitions and volume names are unchanged by HTTPS. The selected Caddy minor image (`caddy:2.11-alpine`) is pulled and validated before interruption so proxy updates/config errors fail early.

## Failure and recovery

A failed build never contacts the VM. A failed registry/proxy pull or Caddy configuration validation leaves the old app running. A failed backup stops before stopping the app. A migration failure leaves the app stopped with data/backup retained; a failed app/proxy health or certificate check does not record the image as accepted. Do not automatically start an old app against a potentially migrated schema.

Inspect the private migration log and backup first. For an application-only failure with confirmed schema compatibility, point `.release.env` at the previous accepted immutable image and run `up -d --no-deps --wait app`, with the healthy Caddy service and its existing volumes retained. Changing an app image alone does not require deleting/reissuing certificates. After a schema-changing deployment, restore a chosen database backup and the corresponding previous image together through a deliberate maintenance operation. Stop the app, preserve the failed database for investigation, and restore only the intended dev database; do not delete the persistent volume as a rollback method. This workflow intentionally has no automatic destructive restore/downgrade. For HTTPS failures, inspect public A/AAAA records, VM TCP 80/443 reachability, Caddy logs and certificate-volume permissions. An internal proxy-health success does not prove certificate issuance. Never delete certificate or database volumes as a troubleshooting shortcut.

Interrupted fresh bootstrap retains `.bootstrap-pending` with the exact image digest. Resume against that exact image after inspecting the failure. It is not permission to stamp another image's schema or overwrite existing data. If files/credentials were transferred but the registry/network failed, rerun the workflow after correcting the cause. Remove stale `.incoming/` or `.docker-auth.*` paths only after confirming no deployment holds `.deploy.lock`.

## Validation and boundaries

Run locally from the repo:

```sh
python3 -m unittest discover -s tests/deployment -v
bash -n deploy/dev/deploy.sh
```

Deployment-flow tests use synthetic data and a fake Docker CLI; the port-policy check renders real Compose JSON using the Docker CLI/Compose plugin without starting containers. No VM, registry or DB is touched. The workflow additionally runs real Compose parsing and `caddy validate` in an isolated, network-disabled container on a GitHub Ubuntu runner. Config validation does not start a server or request a certificate. Tests cover HTTPS/WSS URL generation, pinned origin validation, Caddy-only public ports and localhost-only PostgreSQL access, proxy-before-app startup, early config failure, certificate failure and the existing backup/migration/credential safeguards. A full root image build requires a running Docker engine and access to the pinned base images. Successful source checks alone do not claim an actual Azure deployment. The one-time DNS/firewall/VM prerequisites, GitHub Secrets, updated `DEV_PUBLIC_URL` and branch publication must be completed before the first HTTPS run. This change itself does not deploy or prove that the public domain/certificate is live.

References: [GitHub container publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images), [Compose service definitions](https://docs.docker.com/reference/compose-file/services/), [Compose up and volume preservation](https://docs.docker.com/reference/cli/docker/compose/up/), [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https), [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
