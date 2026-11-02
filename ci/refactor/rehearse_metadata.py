"""Run one registry's metadata source through native DDL in a disposable DB."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import re
import time
import os
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]

def main(domain, pipeline=False):
    portable = (ROOT / f"{domain}-extension").is_dir()
    repo = ROOT if portable else ROOT / f"OAN/worktrees/{domain}-registry/develop-refactor"
    probes = ROOT / "ci/refactor" if portable else ROOT / "tools/registry_refactor"
    output = repo / "ci-output/refactor/new-dev"
    output.mkdir(parents=True, exist_ok=True)
    # Every bind-mounted writer uses the host identity; never chown shared
    # repository trees or alter the database container's native user.
    writer_user = ["--user", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
    network = "coss-refactor-metadata-" + domain
    database = network + "-db"
    created_network = created_database = False
    network_id = database_id = None
    def run(*args):
        result = subprocess.run(args,capture_output=True,text=True,encoding="utf-8",errors="replace")
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)[-3500:])
        return result
    def remove_stale():
        # An aborted build skips the cleanup below and leaves this run's labelled
        # database and network behind; the next build of the same registry would
        # then fail on "already exists". Builds of one registry never overlap, so
        # a same-name leftover carrying our label is safe to remove.
        for kind, name, label in (("container", database, "{{index .Config.Labels \"coss-refactor.disposable\"}}"),
                                  ("network", network, "{{index .Labels \"coss-refactor.disposable\"}}")):
            found = subprocess.run(["docker",kind,"inspect","--format",label,name],capture_output=True,text=True)
            if found.returncode == 0 and found.stdout.strip() == "metadata":
                run("docker","rm","--force","--volumes",name) if kind == "container" else run("docker","network","rm",name)
    remove_stale()
    try:
        network_id = run("docker","network","create","--label","coss-refactor.disposable=metadata",network).stdout.strip()
        created_network = True
        database_id = run("docker","run","--detach","--memory=256m","--name",database,"--network",network,"--label","coss-refactor.disposable=metadata",
            "-e","POSTGRES_HOST_AUTH_METHOD=trust","-e","POSTGRES_DB=refactor_metadata","postgres:15-alpine").stdout.strip()
        created_database = True
        for _ in range(40):
            ready = subprocess.run(["docker","exec",database,"pg_isready","-h","127.0.0.1","-U","postgres"],capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Disposable database did not become ready")
        def probe(mode):
            result = run("docker","run","--rm",*writer_user,"--memory=768m","--network",network,"--entrypoint","python",
                "-v",f"{repo.as_posix()}:/work","-v",f"{probes.as_posix()}:/probe:ro",
                os.environ.get("COSS_REFACTOR_TEST_IMAGE","oan/farmer-reference-tests:rc557"),"/probe/metadata_probe.py","/work",domain,mode)
            print(result.stdout.splitlines()[-1],flush=True)
        probe("ddl")
        package = repo / f"{domain}-extension/src/openg2p_registry_{domain}_extension"
        files = sorted((package / "meta_data").rglob("*.sql"))
        steps = []
        for attempt in (1,2):
            for path in files:
                # Use native psql parsing/autocommit/ON_ERROR_STOP behavior,
                # preserving literal percent signs and DO/dollar-quoted blocks.
                raw = path.read_bytes()
                result = subprocess.run(["docker","exec","-i",database,"psql","-X","-U","postgres",
                    "-d","refactor_metadata","-v","ON_ERROR_STOP=0","-v","VERBOSITY=sqlstate"],
                    input=raw,capture_output=True)
                errors = re.findall(rb"ERROR:\s+([0-9A-Z]{5})",result.stderr)
                steps.append({"pass":attempt,"path":path.relative_to(repo).as_posix(),
                    "sha256":hashlib.sha256(raw).hexdigest(),"sqlstate_errors":[code.decode() for code in errors],
                    "psql_exit_code":result.returncode})
            probe(str(attempt))
        # Run the complete extension suite serially in a fresh process against
        # this owned disposable DB. Some ledger fixtures reset their own public
        # test tables: never run this against an environment DB or in parallel.
        # Package initialization aliases ORM modules. Isolate each test module
        # in a fresh process so standalone ledger tests and native app tests do
        # not import the same SQLAlchemy declarations under two package names.
        # Every module is still executed, serially, with the same owned PostgreSQL container.
        combined = ET.Element("testsuites")
        for module_index, test_module in enumerate(sorted((repo/f"{domain}-extension/tests").glob("test_*.py"))):
            report = test_module.stem + ".xml"
            # Ledger fixtures drop only their own tables/types. Keep them away
            # from native seeded metadata and from other modules' public DDL.
            # These databases live solely in the exact owned container and are
            # removed with it; no environment/database connection is accepted.
            module_database = f"extension_test_{module_index:03d}"
            run("docker","exec",database,"psql","-X","-U","postgres","-d","postgres",
                "-v","ON_ERROR_STOP=1","-c",f"CREATE DATABASE {module_database}")
            result = run("docker","run","--rm",*writer_user,"--memory=768m","--network",network,"--entrypoint","python",
                "-v",f"{repo.as_posix()}:/work","-w","/work",
                "-e",f"REGISTRY_EXTENSION_MODULE=openg2p_registry_{domain}_extension",
                "-e",f"PYTHONPATH=/work/{domain}-extension/src:/work/{domain}-extension/tests",
                "-e",f"FARMER_TEST_DATABASE_URL=postgresql+asyncpg://postgres@{database}/{module_database}",
                os.environ.get("COSS_REFACTOR_TEST_IMAGE","oan/farmer-reference-tests:rc557"),
                "-m","pytest","-q","-p","no:cacheprovider",f"{domain}-extension/tests/{test_module.name}",
                f"--junitxml=/work/ci-output/refactor/new-dev/{report}")
            print(test_module.name + ": " + result.stdout.splitlines()[-1],flush=True)
            module_result = ET.parse(output/report).getroot()
            for suite in module_result if module_result.tag == "testsuites" else [module_result]:
                combined.append(suite)
        ET.ElementTree(combined).write(output/"full-extension.xml",encoding="utf-8",xml_declaration=True)
        cases = list(combined.iter("testcase"))
        failures = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
        if failures:
            raise RuntimeError("Full native extension suite reported failed/error testcases")
        allowed_workflow_methods = {
            "test_native_http_add_routes_only_functional_woreda_approver_without_identity_writes",
            "test_native_http_update_routes_old_geography_and_retry_reuses_remote_request",
            "test_native_http_directory_failure_blocks_with_visible_diagnostic_and_bounded_retries",
        }
        skipped = Counter()
        executed = Counter()
        popup = []
        for case in cases:
            classname = case.get("classname", "")
            family = classname.rsplit(".", 1)[-1]
            name = case.get("name", "")
            skip = case.find("skipped")
            if "test_popup_identity_metadata" in classname:
                popup.append(case)
            if skip is None:
                executed[family] += 1
                continue
            reason = skip.get("message", "")
            if (family == "HttpLookupTests" and "test_farmer_reference_http" in classname
                    and reason == "Requires local Postman simulation; run ci/refactor/verify-onboarding"):
                skipped["farmer_http"] += 1
            elif (family in {"NativeReferenceTests", "NativeNotificationTests"}
                    and "test_farmer_reference_" in classname
                    and name in allowed_workflow_methods and reason == "Requires local Postman dependencies"):
                skipped["native_workflow_http"] += 1
            elif (family == "NativeNotificationTests" and "test_farmer_reference_notification_native" in classname
                    and name == "test_notification_uses_actual_configured_signed_lookup_over_http"
                    and reason == "Requires local Postman dependency"):
                skipped["signed_notification_http"] += 1
            else:
                raise RuntimeError(f"Unexpected native-suite skip: {classname}.{name}: {reason}")
        if skipped != Counter({"farmer_http":9,"native_workflow_http":9,"signed_notification_http":1}):
            raise RuntimeError(f"HTTP simulation skip inventory changed: {dict(skipped)}")
        if len(popup) != 4 or any(case.find("skipped") is not None for case in popup):
            raise RuntimeError("All four popup metadata regressions must execute")
        required_executed = {
            "NativeReferenceTests":34, "NativeNotificationTests":35,
            "OnboardingTests":15, "PendingLookupTests":4, "WorkerHeldTests":2,
            "PopupIdentityMetadataTests":3, "AddOnlyMigrationTests":3,
            "NativeSectionTests" if domain == "cropsown" else "IntakeIdentitySectionTests":1,
        }
        for family, expected in required_executed.items():
            if executed[family] != expected:
                raise RuntimeError(f"Native DB family {family}: expected {expected} executions, got {executed[family]}")
        print(json.dumps({"registry":domain,"full_extension_testcases":len(cases),
            "database_cases_executed":sum(required_executed.values()),
            "allowed_http_simulation_skips":dict(skipped),
            "real_workflow_http":"NOT RUN; requires separate isolated Postman dependency"}),flush=True)
        if pipeline:
            result = run("docker","run","--rm",*writer_user,"--memory=768m","--network",network,"--entrypoint","python",
                "-v",f"{repo.as_posix()}:/work","-v",f"{probes.as_posix()}:/probe:ro",
                "openg2p/openg2p-registry-celery:1.2.2-rc.614","/probe/notification_pipeline_probe.py","/work",domain)
            print(result.stdout.splitlines()[-1],flush=True)
        output = repo / "ci-output/refactor/new-dev"
        first = json.loads((output / "target-pass-1.json").read_text(encoding="utf-8"))
        second = json.loads((output / "target-pass-2.json").read_text(encoding="utf-8"))
        proof = {"registry":domain,"native_psql_semantics":True,"steps":steps,
                 "repeat_metadata_identical":first["metadata"] == second["metadata"],
                 "existing_environment_modified":False,"disposable_database_removed":True}
        (output / "seed-rehearsal.json").write_bytes((json.dumps(proof,indent=2)+"\n").encode("utf-8"))
        print(json.dumps({"registry":domain,"repeat_metadata_identical":proof["repeat_metadata_identical"],
            "files_with_errors":len([step for step in steps if step["sqlstate_errors"]])}),flush=True)
        if not proof["repeat_metadata_identical"] or any(step["sqlstate_errors"] or step["psql_exit_code"] for step in steps):
            raise RuntimeError("Metadata rehearsal failed: SQL errors or non-identical repeated configuration; inspect seed-rehearsal.json")
    finally:
        if created_database:
            owned = run("docker","inspect","--format",'{{.Id}} {{index .Config.Labels "coss-refactor.disposable"}}',database).stdout.strip()
            if owned != database_id + " metadata":
                raise RuntimeError("Disposable database identity changed; refusing cleanup")
            run("docker","rm","--force","--volumes",database)
        if created_network:
            owned = run("docker","network","inspect","--format",'{{.Id}} {{index .Labels "coss-refactor.disposable"}}',network).stdout.strip()
            if owned != network_id + " metadata":
                raise RuntimeError("Disposable network identity changed; refusing cleanup")
            run("docker","network","rm",network)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("domain",choices=("cropsown","livestock"))
    parser.add_argument("--pipeline",action="store_true")
    args=parser.parse_args()
    main(args.domain,args.pipeline)
