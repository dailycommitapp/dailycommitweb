"""No cloud, registry, app, live database or real credentials required."""

import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "deploy/dev" / (name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


ENV = module("validate_env")
DATABASE = module("database")


def secret_values():
    values = {k: secrets.token_hex(32) for k in ENV.STABLE}
    values.update(
        LEARNHOUSE_INITIAL_ADMIN_EMAIL="admin@example.test",
        LEARNHOUSE_INITIAL_ADMIN_PASSWORD=secrets.token_urlsafe(24) + "Aa1!",
    )
    return values


class EnvironmentTests(unittest.TestCase):
    def test_internal_connections_and_runtime_urls(self):
        values = secret_values()
        files = ENV.environment(values, ENV.PUBLIC_ORIGIN)
        app = files["app.env"]
        self.assertIn("@db:5432/learnhouse", app["LEARNHOUSE_SQL_CONNECTION_STRING"])
        self.assertIn("@redis:6379/0", app["LEARNHOUSE_REDIS_CONNECTION_STRING"])
        self.assertEqual(app["LEARNHOUSE_API_URL"], "http://127.0.0.1:9000")
        self.assertEqual(
            app["NEXT_PUBLIC_COLLAB_URL"], "wss://dev.dailycommit.co.za/collab"
        )
        self.assertEqual(app["LEARNHOUSE_TENANCY"], "single")
        self.assertEqual(app["LEARNHOUSE_SSL"], "true")
        self.assertEqual(app["NEXT_PUBLIC_LEARNHOUSE_HTTPS"], "true")
        self.assertEqual(app["NEXTAUTH_URL"], ENV.PUBLIC_ORIGIN)
        self.assertEqual(
            app["NEXT_PUBLIC_LEARNHOUSE_API_URL"], ENV.PUBLIC_ORIGIN + "/api/v1/"
        )
        self.assertEqual(
            app["NEXT_PUBLIC_LEARNHOUSE_BACKEND_URL"], ENV.PUBLIC_ORIGIN + "/"
        )
        self.assertEqual(app["LEARNHOUSE_ALLOWED_ORIGINS"], ENV.PUBLIC_ORIGIN)
        self.assertEqual(app["LEARNHOUSE_DEVELOPMENT_MODE"], "false")
        self.assertNotIn("LEARNHOUSE_JUDGE0_API_URL", app)
        self.assertNotIn("LEARNHOUSE_AI_API_KEY", app)
        self.assertEqual(
            set(files["db.env"]), {"POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"}
        )
        self.assertEqual(set(files["redis.env"]), {"REDIS_PASSWORD"})
        self.assertFalse(
            any(
                k.endswith(("SECRET", "PASSWORD", "KEY", "TOKEN"))
                for k in app
                if k.startswith("NEXT_PUBLIC_")
            )
        )

    def test_unsafe_values_and_origins_fail_without_echoing_secrets(self):
        values = secret_values()
        for origin in [
            "https://example.test",
            "http://example.test:8080",
            "http://example.test/path",
            "http://user:pass@example.test",
            "http://example.test?token=private",
        ]:
            with self.assertRaises(ValueError):
                ENV.validate(values, origin)
        for bad in ["short", "space in password", "bad\nline"]:
            candidate = dict(values, POSTGRES_PASSWORD=bad)
            with self.assertRaises(ValueError) as error:
                ENV.validate(candidate, ENV.PUBLIC_ORIGIN)
            self.assertNotIn(bad, str(error.exception))
        with self.assertRaises(ValueError):
            ENV.validate(
                dict(values, LEARNHOUSE_JUDGE0_API_URL="http://unused"),
                ENV.PUBLIC_ORIGIN,
            )
        with self.assertRaises(ValueError):
            ENV.validate(
                dict(values, REDIS_PASSWORD=values["POSTGRES_PASSWORD"]),
                ENV.PUBLIC_ORIGIN,
            )

    def test_https_origin_is_pinned_and_default_port_normalized(self):
        values = secret_values()
        for invalid in (
            "http://dev.dailycommit.co.za",
            "https://example.test",
            "https://dev.dailycommit.co.za:8443",
            "https://dev.dailycommit.co.za/path",
            "https://user:password@dev.dailycommit.co.za",
            "https://dev.dailycommit.co.za?x=1",
            "https://dev.dailycommit.co.za#fragment",
        ):
            with self.assertRaises(ValueError):
                ENV.validate(values, invalid)
        self.assertEqual(
            ENV.validate(values, ENV.PUBLIC_ORIGIN + ":443/")[0], ENV.PUBLIC_ORIGIN
        )

    def test_raw_password_and_private_file(self):
        values = secret_values()
        password = "Unusual $ # quoted ' \" Aa1!"
        files = ENV.environment(
            dict(values, LEARNHOUSE_INITIAL_ADMIN_PASSWORD=password),
            ENV.PUBLIC_ORIGIN,
        )
        self.assertEqual(
            files["app.env"]["LEARNHOUSE_INITIAL_ADMIN_PASSWORD"], password
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "app.env"
            ENV.write_private(path, "SECRET=" + password + "\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                ENV.write_private(path, "overwrite")

    def test_native_database_state_classification(self):
        self.assertEqual(DATABASE.classify(set(), set()), "fresh")
        self.assertEqual(DATABASE.classify({"alembic_version"}, set()), "fresh")
        self.assertEqual(
            DATABASE.classify({"organization", "user"}, set()), "unversioned"
        )
        self.assertEqual(
            DATABASE.classify({"organization", "user", "alembic_version"}, {"head"}),
            "versioned",
        )
        with self.assertRaises(ValueError):
            DATABASE.classify({"alembic_version"}, {"head"})


FAKE_DOCKER = r"""#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['COMMAND_LOG'],'a') as f:f.write(json.dumps(args)+'\n')
if args[:2]==['compose','version']: print('2.30.0');sys.exit(0)
if args and args[0]=='info':
    if '--format' in args: print('x86_64')
    sys.exit(0)
if args and args[0] in ('login','pull'):sys.exit(0)
if 'pg_dump' in args:
    if os.environ.get('FAIL_BACKUP')=='1':sys.exit(1)
    print('synthetic backup for test only');sys.exit(0)
if 'psql' in args: print(' has_admin\n-----------\n t');sys.exit(0)
if '/run/dailycommit-database.py' in args:
    operation=args[-1]
    if operation=='inspect':print(json.dumps({'state':os.environ.get('DB_STATE','fresh'),'versions':[],'image_heads':['test']}))
    sys.exit(0)
if 'validate' in args and os.environ.get('FAIL_CADDY_VALIDATE')=='1':sys.exit(1)
if 'up' in args and args[-1]=='caddy' and os.environ.get('FAIL_CADDY_START')=='1':sys.exit(1)
if 'up' in args and args[-1]=='app' and os.environ.get('FAIL_APP')=='1':sys.exit(1)
sys.exit(0)
"""


class DeploymentFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        (self.bundle / "deploy/dev").mkdir(parents=True)
        for name in ("deploy.sh", "database.py"):
            shutil.copy2(ROOT / "deploy/dev" / name, self.bundle / "deploy/dev" / name)
        shutil.copy2(
            ROOT / "docker-compose.dev.yml", self.bundle / "docker-compose.dev.yml"
        )
        shutil.copy2(ROOT / "deploy/dev/Caddyfile", self.bundle / "Caddyfile")
        for name in ("app.env", "db.env", "redis.env"):
            (self.bundle / name).write_text("")
        (self.bundle / "secret-fingerprints.json").write_text("{}")
        (self.bundle / ".registry-auth.json").write_text(
            json.dumps({"username": "testuser", "token": secrets.token_hex(20)})
        )
        self.vm = self.root / "vm"
        self.vm.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        # The real VM has util-linux flock. This shim only makes cross-platform command-flow tests possible.
        flock = self.bin / "flock"
        flock.write_text("#!/bin/sh\nexit 0\n")
        flock.chmod(0o755)
        curl = self.bin / "curl"
        curl.write_text(
            "#!/usr/bin/env python3\nimport os,sys,json\nwith open(os.environ['COMMAND_LOG'],'a') as f:f.write(json.dumps(['curl']+sys.argv[1:])+'\\n')\nsys.exit(1 if os.environ.get('FAIL_HTTPS')=='1' else 0)\n"
        )
        curl.chmod(0o755)
        sleep = self.bin / "sleep"
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(0o755)
        self.log = self.root / "commands.jsonl"
        self.image = "ghcr.io/dailycommitapp/dailycommitweb@sha256:" + "a" * 64
        self.sha = "b" * 40

    def run_deploy(self, **extra):
        env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            DAILYCOMMIT_DEPLOY_DIR=str(self.vm),
            COMMAND_LOG=str(self.log),
            **extra,
        )
        result = subprocess.run(
            ["bash", str(self.bundle / "deploy/dev/deploy.sh"), self.image, self.sha],
            env=env,
            capture_output=True,
            text=True,
        )
        commands = (
            [json.loads(line) for line in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )
        return result, commands

    def test_fresh_deploy_preserves_volumes_and_waits_for_health(self):
        result, commands = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("down" in cmd or "prune" in cmd for cmd in commands))
        self.assertTrue(
            any(
                "up" in cmd and "--wait" in cmd and cmd[-1] == "app" for cmd in commands
            )
        )
        self.assertTrue(any(cmd[-1] == "stamp" for cmd in commands))
        self.assertEqual(
            (self.vm / "current-image.txt").read_text().strip(), self.image
        )
        self.assertTrue(list((self.vm / "backups").glob("*.dump")))
        self.assertFalse((self.bundle / ".registry-auth.json").exists())
        self.assertFalse(list(self.vm.glob(".docker-auth.*")))

    def test_backup_failure_leaves_existing_app_running(self):
        result, commands = self.run_deploy(FAIL_BACKUP="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any(
                "stop" in cmd or cmd[-1:] == ["app"] and "up" in cmd for cmd in commands
            )
        )
        self.assertFalse((self.vm / "current-image.txt").exists())

    def test_unknown_unversioned_database_is_never_stamped(self):
        result, commands = self.run_deploy(DB_STATE="unversioned")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(cmd[-1:] in (["stamp"], ["upgrade"]) for cmd in commands))
        self.assertIn("Unversioned existing database", result.stderr)

    def test_upgrade_before_app_and_health_failure_is_not_accepted(self):
        result, commands = self.run_deploy(DB_STATE="versioned", FAIL_APP="1")
        self.assertNotEqual(result.returncode, 0)
        stop = next(i for i, c in enumerate(commands) if "stop" in c)
        upgrade = next(i for i, c in enumerate(commands) if c[-1:] == ["upgrade"])
        start = next(
            i for i, c in enumerate(commands) if "up" in c and c[-1:] == ["app"]
        )
        self.assertLess(stop, upgrade)
        self.assertLess(upgrade, start)
        self.assertFalse((self.vm / "current-image.txt").exists())

    def test_caddy_config_failure_happens_before_backup_or_app_stop(self):
        result, commands = self.run_deploy(FAIL_CADDY_VALIDATE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("pg_dump" in c or "stop" in c for c in commands))
        self.assertFalse((self.vm / "current-image.txt").exists())

    def test_proxy_starts_after_backup_before_app_readiness(self):
        result, commands = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backup = next(i for i, c in enumerate(commands) if "pg_dump" in c)
        stopped = next(i for i, c in enumerate(commands) if "stop" in c)
        caddy = next(
            i for i, c in enumerate(commands) if "up" in c and c[-1] == "caddy"
        )
        app = next(i for i, c in enumerate(commands) if "up" in c and c[-1] == "app")
        https = next(i for i, c in enumerate(commands) if c[0] == "curl")
        self.assertLess(backup, stopped)
        self.assertLess(stopped, caddy)
        self.assertLess(caddy, app)
        self.assertLess(app, https)
        self.assertIn("--resolve", commands[https])
        self.assertNotIn("--insecure", commands[https])
        self.assertNotIn("-k", commands[https])
        self.assertEqual(commands[https][-1], ENV.PUBLIC_ORIGIN + "/api/v1/health")

    def test_caddy_start_failure_does_not_accept_or_start_new_app(self):
        result, commands = self.run_deploy(FAIL_CADDY_START="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("up" in c and c[-1] == "app" for c in commands))
        self.assertFalse((self.vm / "current-image.txt").exists())
        self.assertTrue(list((self.vm / "backups").glob("*.dump")))

    def test_failed_certificate_check_does_not_accept_release(self):
        result, commands = self.run_deploy(FAIL_HTTPS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(c[0] == "curl" for c in commands), 12)
        self.assertFalse((self.vm / "current-image.txt").exists())
        self.assertTrue(list((self.vm / "backups").glob("*.dump")))

    def test_stable_secret_rotation_stops_before_docker_login(self):
        (self.vm / "secret-fingerprints.json").write_text('{"changed":true}')
        result, commands = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[:1] == ["login"] for c in commands))


class WorkflowTests(unittest.TestCase):
    def test_only_branch_push_deploys_and_public_image_is_immutable(self):
        workflow = (ROOT / ".github/workflows/deploy-dev.yml").read_text()
        self.assertIn("branches: [dailycommit-dev]", workflow)
        self.assertIn("github.ref == 'refs/heads/dailycommit-dev'", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("LEARNHOUSE_PUBLIC=true", workflow)
        self.assertIn("file: ./Dockerfile", workflow)
        self.assertIn(":sha-${{ github.sha }}", workflow)
        self.assertIn(":dev", workflow)
        self.assertIn(":latest", workflow)
        self.assertIn("$IMAGE_NAME@$IMAGE_DIGEST", workflow)
        self.assertIn("StrictHostKeyChecking=yes", workflow)
        self.assertNotIn("ssh-keyscan", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("password: ${{ secrets.GITHUB_TOKEN }}", workflow)

    def test_existing_checks_recognize_deployment_branch(self):
        for name in (
            "api-lint.yaml",
            "api-tests.yaml",
            "web-lint.yaml",
            "web-tests.yaml",
            "lockfiles.yaml",
            "build-community.yaml",
        ):
            self.assertIn(
                "dailycommit-dev", (ROOT / ".github/workflows" / name).read_text()
            )

    def test_compose_data_services_are_not_published(self):
        text = (ROOT / "docker-compose.dev.yml").read_text()
        self.assertEqual(text.count("ports:"), 1)
        self.assertIn("pgvector/pgvector:pg16", text)
        self.assertIn("dailycommit-dev-postgres", text)
        self.assertIn("dailycommit-dev-content", text)
        self.assertIn("dailycommit-dev-redis", text)
        self.assertIn("--appendonly yes", text)
        self.assertIn("/app/api/content", text)
        app = text.split("  app:", 1)[1].split("  caddy:", 1)[0]
        self.assertNotIn("ports:", app)
        self.assertIn('expose:\n      - "80"', app)
        caddy = text.split("  caddy:", 1)[1].split("  db:", 1)[0]
        self.assertIn('"80:80"', caddy)
        self.assertIn('"443:443"', caddy)
        self.assertNotIn("depends_on:", caddy)
        self.assertIn("dev.dailycommit.co.za", caddy)
        self.assertIn("dailycommit-dev-caddy-data", text)
        self.assertIn("dailycommit-dev-caddy-config", text)
        self.assertNotIn("2019:2019", text)

    def test_caddy_config_and_workflow_bundle(self):
        config = (ROOT / "deploy/dev/Caddyfile").read_text()
        self.assertIn("dev.dailycommit.co.za {", config)
        self.assertIn("reverse_proxy app:80", config)
        self.assertNotIn("tls internal", config)
        self.assertNotIn("auto_https off", config)
        workflow = (ROOT / ".github/workflows/deploy-dev.yml").read_text()
        self.assertIn('cp deploy/dev/Caddyfile "$work/bundle/Caddyfile"', workflow)
        self.assertIn('cp deploy/dev/Caddyfile "$staging/Caddyfile"', workflow)
        self.assertIn("--network none", workflow)
        self.assertIn("caddy validate", workflow)


if __name__ == "__main__":
    unittest.main()
