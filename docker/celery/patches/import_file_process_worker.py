import csv
import io
import json
import uuid
import logging
import asyncio
from datetime import datetime
from typing import Any
import openpyxl
import xmltodict

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from openg2p_registry_core.helpers.document import get_document_handler
from openg2p_registry_core.models import (
    DataModel,
    G2PRegistryDocument,
    ImportFileProcessLog,
    ImportFileProcessQueue,
    ProcessStatusEnum,
)
from openg2p_registry_core.services import G2PIngestService

from ..app import celery_app
from ..config import Settings
from ..engine import Engine

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)
_engine = Engine.get_engine()
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

SUPPORTED_FORMATS = [".csv", ".tsv", ".xlsx", ".xls", ".json", ".jsonl", ".xml"]

@celery_app.task(name="import_file_process_worker", bind=True, max_retries=3)
def import_file_process_worker(self, import_file_id: str):
    """
    Worker that processes an import file record-by-record.

    Steps:
        1. Fetch queue item and resolve data model.
        2. Download file from Minio.
        3. Parse file into records (CSV / TSV / Excel / JSON / JSONL / XML).
        4. For each record, check idempotency log and call ingest pipeline.
        5. Write per-record log and commit.
        6. Update queue item status on success or failure.
    """
    _logger.info(
        "Import file process worker started for import_file_id=%s", import_file_id
    )

    session_maker = sessionmaker(bind=_engine, expire_on_commit=False)

    with session_maker() as session:
        queue_item: ImportFileProcessQueue | None = None
        try:
            queue_item = session.get(ImportFileProcessQueue, import_file_id)
            if not queue_item:
                raise Exception(
                    f"Import file queue item not found for import_file_id: {import_file_id}"
                )

            data_model: DataModel | None = session.get(DataModel, queue_item.data_model_id)
            if not data_model:
                raise Exception(
                    f"DataModel not found for data_model_id: {queue_item.data_model_id}"
                )

            catalog_doc: G2PRegistryDocument | None = session.get(
                G2PRegistryDocument, queue_item.document_id
            )
            if not catalog_doc:
                raise Exception(
                    f"Catalog document not found for document_id: {queue_item.document_id}"
                )

            handler = get_document_handler()
            file_content: bytes = handler.download(
                catalog_doc.document_store_id,
                catalog_doc.bucket,
            )

            # Parse file into records
            all_records = parse_file_to_records(
                file_content, catalog_doc.source_filename
            )
            total_records_in_file = len(all_records)
            total_records_ingested = 0

            _logger.info(
                "Parsed import_file_id=%s total_records=%s",
                import_file_id,
                total_records_in_file,
            )

            ingest_service = G2PIngestService.get_component()

            for record_number, record_data in enumerate(all_records, start=1):

                # Idempotency check
                existing_log: ImportFileProcessLog | None = (
                    session.execute(
                        select(ImportFileProcessLog).where(
                            ImportFileProcessLog.document_id == queue_item.document_id,
                            ImportFileProcessLog.record_number == record_number,
                        )
                    )
                    .scalar_one_or_none()
                )
                if existing_log:
                    _logger.debug(
                        "Skipping already-ingested record_number=%s import_file_id=%s",
                        record_number,
                        import_file_id,
                    )
                    continue

                # Build ingest payload compatible with the data model's expected envelope
                sender_id = _config.import_file_sender_id or "Staff Portal"
                signature = _config.import_file_signature or "file-import"

                # If targeting CSR_DATA_MODEL, ensure message_id matches pattern for intake form
                # and wrap flat row into the ODK-compatible payload structure expected by csr_odk_transform.j2
                if data_model.data_model_mnemonic == "CSR_DATA_MODEL":
                    prefix_map = {
                        "5bf0068c-ce19-46f8-874c-7147997f793b": "crop_sown_registry_plan",
                        "6be15ab9-0f1b-4c38-995f-395d52a1b17a": "crop_sown_registry_prep",
                        "4a7c2c98-0ffb-41d8-8fea-f22349823675": "crop_sown_registry_sown",
                        "52150a37-153d-496d-9cd9-2a3815d6e13b": "crop_sown_registry_harvest",
                    }
                    msg_prefix = prefix_map.get(queue_item.intake_form_id, "crop_sown_registry_plan")
                    message_id = f"{msg_prefix}_{uuid.uuid4().hex}"

                    # Helper to normalize date strings to YYYY-MM-DD
                    def _norm_date(dt_val):
                        if not dt_val:
                            return ""
                        dt_str = str(dt_val).strip()
                        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
                            try:
                                return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%d")
                            except ValueError:
                                pass
                        return dt_str

                    norm_planned_date = _norm_date(record_data.get("planned_date", ""))

                    # If flat record is not already nested, format into ODK survey structure
                    if "planning" not in record_data and "cult_land_prep" not in record_data:
                        payload = {
                            "register_mnemonic": "CropSown",
                            "__system": {
                                "submissionDate": norm_planned_date or datetime.now().strftime("%Y-%m-%d")
                            },
                            "farmer_identity": {
                                "farmer_id": record_data.get("farmer_id", ""),
                                "fayda_fan_id": record_data.get("fayda_fan_id", ""),
                                "farmer_name": record_data.get("farmer_name", ""),
                                "crop_year": record_data.get("crop_year", ""),
                                "production_season": record_data.get("production_season", record_data.get("season", "")),
                            },
                            "address": {
                                "region_display_id": record_data.get("region", ""),
                                "zone_display_id": record_data.get("zone", ""),
                                "woreda_display_id": record_data.get("woreda", ""),
                                "kebele_display_id": record_data.get("kebele", "")
                            },
                            "planning": [
                                {
                                    "land_info_id": record_data.get("land_id", ""),
                                    "land_area": record_data.get("land_area", "0"),
                                    "plot_category": record_data.get("plot_category", ""),
                                    "ownership_type": record_data.get("ownership_type", ""),
                                    "season_details": {
                                        "season_id": record_data.get("season", record_data.get("production_season", ""))
                                    },
                                    "crop_details": {
                                        "crop_name_id": record_data.get("commodity", ""),
                                        "crop_variety_id": record_data.get("crop_variety", ""),
                                        "collected_gc": norm_planned_date
                                    },
                                    "crop_planned_inputs": {
                                        "crop_growth_duration": record_data.get("growth_duration_days", 60),
                                        "crop_planned_area": record_data.get("planned_area", record_data.get("land_area", 1.0)),
                                        "crop_expected": record_data.get("expected_yield", 10.0),
                                        "seed_planned": record_data.get("seed_class", "IMPROVED"),
                                        "seed_source": record_data.get("seed_source", ""),
                                        "seed_variety": record_data.get("crop_variety", ""),
                                        "seed_planned_qty": record_data.get("planned_seed_qty", 0),
                                        "seed_planned_fertilizer_type": record_data.get("planned_fertilizer_type", ""),
                                        "seed_planned_fertilizer_qty": record_data.get("planned_fertilizer_qty", 0)
                                    }
                                }
                            ]
                        }
                    else:
                        payload = dict(record_data)
                        payload.setdefault("register_mnemonic", "CropSown")

                    ingest_data = {
                        "body": {
                            "header": {
                                "sender_id": sender_id,
                                "message_id": message_id,
                                "signature": signature,
                            },
                            "message": {
                                "payload": payload
                            }
                        }
                    }
                else:
                    # DCI or default envelope
                    message_id = uuid.uuid4().hex
                    ingest_data = {
                        "body": {
                            "header": {
                                "sender_id": sender_id,
                                "message_id": message_id,
                            },
                            "signature": signature,
                            "message": {
                                "search_response": [
                                    {
                                        "data": {
                                            "reg_type": "CropSown",
                                            "reg_record_type": "crop_sown_planning_intake",
                                            "reg_records": [record_data]
                                        }
                                    }
                                ]
                            }
                        }
                    }

                # Call ingest pipeline
                correlation_id, _ = _loop.run_until_complete(
                    ingest_service.ingest_data(
                        data_model.data_model_mnemonic,
                        ingest_data,
                        register_id=queue_item.register_id,
                        intake_form_id=queue_item.intake_form_id,
                    )
                )
                _logger.debug(
                    "Ingested record_number=%s import_file_id=%s correlation_id=%s",
                    record_number,
                    import_file_id,
                    correlation_id,
                )

                # Write per-record log
                session.add(
                    ImportFileProcessLog(
                        import_file_id=import_file_id,
                        document_id=queue_item.document_id,
                        record_number=record_number,
                        ingestion_timestamp=datetime.now(),
                    )
                )
                session.commit()
                total_records_ingested += 1

            # Mark queue item as processed
            queue_item.number_of_records_present = total_records_in_file
            queue_item.number_of_records_ingested = total_records_ingested
            queue_item.intake_form_ingestion_status = ProcessStatusEnum.PROCESSED.value
            queue_item.intake_form_ingestion_timestamp = datetime.now()
            queue_item.intake_form_ingestion_error = None
            session.add(queue_item)
            session.commit()

            _logger.info(
                "Completed import_file_id=%s records_in_file=%s records_ingested=%s",
                import_file_id,
                total_records_in_file,
                total_records_ingested,
            )

        except Exception as e:
            _logger.error(
                "Error in import_file_process_worker for import_file_id=%s: %s",
                import_file_id,
                str(e),
                exc_info=True,
            )
            session.rollback()

            if queue_item:
                queue_item.intake_form_ingestion_timestamp = datetime.now()
                queue_item.intake_form_ingestion_error = str(e)
                if (queue_item.intake_form_ingestion_attempts or 0) >= _config.worker_max_attempts:
                    queue_item.intake_form_ingestion_status = ProcessStatusEnum.FAILED.value
                else:
                    queue_item.intake_form_ingestion_status = ProcessStatusEnum.PENDING.value
                session.add(queue_item)
                session.commit()

            raise

    _logger.info(
        "Import file process worker finished for import_file_id=%s", import_file_id
    )

# ---------------------------------------------------------------------------
# File parsers
# ---------------------------------------------------------------------------

def parse_file_to_records(file_content: bytes, filename: str) -> list[dict[str, Any]]:
    """
    Parse any supported file format into a flat list of row dicts.

    Supported formats:
        - CSV   (.csv)
        - TSV   (.tsv)
        - Excel (.xlsx, .xls)
        - JSON  (.json)  — expects a list of objects, or {"data": [...]}
        - JSONL (.jsonl) — expects one JSON object per line
        - XML   (.xml)   — expects repeated sibling elements under a root

    Args:
        file_content: Raw bytes of the file.
        filename:     Original filename (used to detect format by extension).

    Returns:
        List of dicts, one per record.

    Raises:
        ValueError: If the file format is unsupported or content is malformed.
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".csv"):
        return _parse_csv(file_content, delimiter=",")

    elif filename_lower.endswith(".tsv"):
        return _parse_csv(file_content, delimiter="\t")

    elif filename_lower.endswith((".xlsx", ".xls")):
        return _parse_excel(file_content)

    elif filename_lower.endswith(".json"):
        return _parse_json(file_content)

    elif filename_lower.endswith(".jsonl"):
        return _parse_jsonl(file_content)

    elif filename_lower.endswith(".xml"):
        return _parse_xml(file_content)

    else:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "unknown"
        raise ValueError(
            f"Unsupported file format '.{ext}'. "
            f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
        )


def _parse_csv(file_content: bytes, delimiter: str = ",") -> list[dict[str, Any]]:
    """Parse CSV or TSV bytes into a list of row dicts."""
    try:
        text = file_content.decode("utf-8-sig")  # strips BOM if present
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        records = list(reader)
        _logger.debug("Parsed %d records from CSV/TSV", len(records))
        return records
    except Exception as e:
        raise ValueError(f"Failed to parse CSV/TSV file: {e}") from e


def _parse_excel(file_content: bytes) -> list[dict[str, Any]]:
    """Parse Excel (.xlsx / .xls) bytes into a list of row dicts."""
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(file_content), read_only=True, data_only=True
        )
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        workbook.close()

        if not rows:
            return []

        headers = [
            str(cell).strip() if cell is not None else f"column_{i}"
            for i, cell in enumerate(rows[0])
        ]

        records = []
        for row in rows[1:]:
            if all(cell is None for cell in row):  # skip empty rows
                continue
            record = {
                headers[i]: (str(row[i]).strip() if row[i] is not None else "")
                for i in range(len(headers))
            }
            records.append(record)

        _logger.debug("Parsed %d records from Excel", len(records))
        return records
    except Exception as e:
        raise ValueError(f"Failed to parse Excel file: {e}") from e


def _parse_json(file_content: bytes) -> list[dict[str, Any]]:
    """
    Parse JSON bytes into a list of row dicts.

    Accepts:
        - A JSON array:              [ {...}, {...} ]
        - A wrapped object with any top-level list value:
                                     { "data": [...] }
                                     { "records": [...] }
    """
    try:
        parsed = json.loads(file_content.decode("utf-8"))

        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict):
            list_key = next(
                (k for k, v in parsed.items() if isinstance(v, list)), None
            )
            if not list_key:
                raise ValueError(
                    "JSON object has no top-level list. "
                    "Expected format: [{...}] or {\"data\": [{...}]}"
                )
            records = parsed[list_key]
            _logger.debug("Using JSON key '%s' as record list", list_key)
        else:
            raise ValueError("JSON content must be an array or an object containing an array.")

        records = [_flatten_dict(r) for r in records]
        _logger.debug("Parsed %d records from JSON", len(records))
        return records
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON content: {e}") from e


def _parse_jsonl(file_content: bytes) -> list[dict[str, Any]]:
    """
    Parse JSON Lines (.jsonl) bytes into a list of row dicts.

    Expects one valid JSON object per line, with blank lines ignored, e.g.:
        {"name": "Alice", "age": 30}
        {"name": "Bob",   "age": 25}
    """
    try:
        records = []
        for line_number, raw_line in enumerate(
            file_content.decode("utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line:          # skip blank lines
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {e}"
                ) from e
            if not isinstance(obj, dict):
                raise ValueError(
                    f"Expected a JSON object on line {line_number}, "
                    f"got {type(obj).__name__}"
                )
            records.append(_flatten_dict(obj))

        _logger.debug("Parsed %d records from JSONL", len(records))
        return records
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to parse JSONL file: {e}") from e


def _parse_xml(file_content: bytes) -> list[dict[str, Any]]:
    """
    Parse XML bytes into a list of row dicts.

    Expects repeated sibling elements under a single root, e.g.:
        <records>
            <record><name>Alice</name><age>30</age></record>
            <record><name>Bob</name><age>25</age></record>
        </records>
    """
    try:
        parsed = xmltodict.parse(file_content.decode("utf-8"))

        root = parsed
        if len(parsed) == 1:
            root = next(iter(parsed.values()))

        list_key = next(
            (k for k, v in root.items() if isinstance(v, list)), None
        )

        if list_key:
            records = root[list_key]
        elif isinstance(root, dict):
            records = [root]  # single record — wrap in list
        else:
            raise ValueError("Could not locate a list of records in the XML structure.")

        records = [_flatten_dict(r) for r in records]
        _logger.debug("Parsed %d records from XML", len(records))
        return records
    except Exception as e:
        raise ValueError(f"Failed to parse XML file: {e}") from e


def _flatten_dict(
    d: dict,
    parent_key: str = "",
    sep: str = ".",
) -> dict[str, Any]:
    """
    Recursively flatten a nested dict into dot-notation keys.

    Example:
        {"name": {"first": "Alice", "last": "Smith"}, "age": 30}
        → {"name.first": "Alice", "name.last": "Smith", "age": 30}
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)