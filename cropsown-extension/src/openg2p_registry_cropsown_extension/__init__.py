import os

if "COMMON_AUTH_REDIS_URL" not in os.environ and "REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL" in os.environ:
    os.environ["COMMON_AUTH_REDIS_URL"] = os.environ["REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL"]
if "COMMON_AUTH_PROVIDER_API_URL" not in os.environ and "REGISTRY_STAFF_PORTAL_API_AUTH_PROVIDER_API_URL" in os.environ:
    os.environ["COMMON_AUTH_PROVIDER_API_URL"] = os.environ["REGISTRY_STAFF_PORTAL_API_AUTH_PROVIDER_API_URL"]
if "COMMON_KEYCLOAK_CLIENT_ID" not in os.environ and "AUTH_CLIENT_ID" in os.environ:
    os.environ["COMMON_KEYCLOAK_CLIENT_ID"] = os.environ["AUTH_CLIENT_ID"]
if "COMMON_DB_HOSTNAME" not in os.environ and "REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME" in os.environ:
    os.environ["COMMON_DB_HOSTNAME"] = os.environ["REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME"]
if "COMMON_DB_PORT" not in os.environ and "REGISTRY_STAFF_PORTAL_API_DB_PORT" in os.environ:
    os.environ["COMMON_DB_PORT"] = str(os.environ["REGISTRY_STAFF_PORTAL_API_DB_PORT"])
if "COMMON_DB_DBNAME" not in os.environ and "REGISTRY_STAFF_PORTAL_API_DB_DBNAME" in os.environ:
    os.environ["COMMON_DB_DBNAME"] = os.environ["REGISTRY_STAFF_PORTAL_API_DB_DBNAME"]
if "COMMON_DB_USERNAME" not in os.environ and "REGISTRY_STAFF_PORTAL_API_DB_USERNAME" in os.environ:
    os.environ["COMMON_DB_USERNAME"] = os.environ["REGISTRY_STAFF_PORTAL_API_DB_USERNAME"]
if "COMMON_DB_PASSWORD" not in os.environ and "REGISTRY_STAFF_PORTAL_API_DB_PASSWORD" in os.environ:
    os.environ["COMMON_DB_PASSWORD"] = os.environ["REGISTRY_STAFF_PORTAL_API_DB_PASSWORD"]
if "COMMON_DB_DRIVER" not in os.environ:
    os.environ["COMMON_DB_DRIVER"] = "postgresql+asyncpg"

try:
    from openg2p_fastapi_common.config import Settings as CommonSettings
    _common_conf = CommonSettings.get_config(strict=False)
    if getattr(_common_conf, "db_hostname", None) in (None, "localhost", "127.0.0.1"):
        _common_conf.db_hostname = os.environ.get("COMMON_DB_HOSTNAME", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME", "postgres"))
        _common_conf.db_port = int(os.environ.get("COMMON_DB_PORT", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_PORT", 5432)))
        _common_conf.db_dbname = os.environ.get("COMMON_DB_DBNAME", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_DBNAME", "cropsown"))
        _common_conf.db_username = os.environ.get("COMMON_DB_USERNAME", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_USERNAME", "postgres"))
        _common_conf.db_password = os.environ.get("COMMON_DB_PASSWORD", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_PASSWORD", "postgres"))
        _common_conf.db_driver = "postgresql+asyncpg"
        _common_conf.db_datasource = f"{_common_conf.db_driver}://{_common_conf.db_username}:{_common_conf.db_password}@{_common_conf.db_hostname}:{_common_conf.db_port}/{_common_conf.db_dbname}"
except Exception:
    pass

try:
    from iam_core.user_auth.config import Settings as IamSettings
    _iam_conf = IamSettings.get_config(strict=False)
    if getattr(_iam_conf, "auth_redis_url", None) in (None, "redis://localhost:6379/0"):
        _iam_conf.auth_redis_url = os.environ.get("REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL", "redis://redis:6379/0")
    if not getattr(_iam_conf, "auth_provider_api_url", None):
        _iam_conf.auth_provider_api_url = os.environ.get("REGISTRY_STAFF_PORTAL_API_AUTH_PROVIDER_API_URL", "http://iam:8000")
except Exception:
    pass

__version__ = "1.0.0"
__variant__ = "cropsown"

try:
    from . import odk_ingest_hooks  # noqa: F401
except ImportError:
    pass

