"""Build the four Crop Sown ODK forms whose season, crop and geography choices come from Master Data.

    python odk/tools/build_mds_forms.py --pack ../openg2p-data/packs/ETH-OAN

The forms are the Planning, Cultivation, Sowing and Harvesting forms published on
ODK Central project 2 (form ids crop_sown_registry_plan, _prep, _sown, _harvest;
the submission header prefix of each id selects the registry intake form, so the ids
never change). Their published workbooks are kept unchanged in odk/source/. This
builder rewrites them:

1. Identity. The first group of every form is "farmer_identity" and holds exactly two
   required questions: Farmer ID (FR- and 12 digits) and Fayda ID (a 16 digit FAN or a
   12 digit FIN, spaces allowed). The registry transform
   (odk_to_crop_intake.j2) reads the fields farmer_id and fayda_id from that group and
   tells a FIN from a FAN by length, so the typed Fayda ID (fayda_id_entered) is copied
   into a hidden calculate named fayda_id with the spaces removed. Crop year and
   production season move to the group production_season_info, which the transform also
   reads. The old fyda_id / fayda_fan_id, is_farmer_registered and farmer_name questions
   are dropped.
2. Master Data lists. ODK Collect cannot read Master Data while a form is filled in, so
   the form carries each list at build time, exactly as Master Data serves it: the choice
   name is the value code (what the registry stores) and the label its display.
     - production season and season       -> CROP_SEASON          (inline choices)
     - agro ecological zone               -> AGRO_ECOLOGICAL_ZONE (inline choices)
     - crop_name.csv                      -> CROP_COMMODITY, with its CROP_CATEGORY
     - seed_variety.csv                   -> SEED_VARIETY (the one "Variety" question)
     - region/zone/woreda/kebele.csv      -> the geography, named by P-code, each row
                                             carrying its parent's P-code
   Every list is read from --pack. The forms carry one variety question, "Variety",
   on SEED_VARIETY; the source workbooks' separate "Crop Variety" question (a list
   the pack does not carry) is dropped. The geography is read from --geography
   (levels.json and values.json in the pack's format; default: the pack's), which must be
   the geography of the environment the form is published to.
3. Everything else is left as published (see NOT_MASTER_DATA for why), except the two
   yes/no lists, which are not Master Data lists either.

The form version is the build date (--version, default VERSION below).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "odk/source"
FORMS = REPO / "odk/forms"
MEDIA = REPO / "odk/media/mds"
VERSION = "2026.11.02.1"
FORM_IDS = ("crop_sown_registry_plan", "crop_sown_registry_prep", "crop_sown_registry_sown", "crop_sown_registry_harvest")
LEVELS = ("region", "zone", "woreda", "kebele")

# XLSForm choice list name -> Master Data attribute
INLINE_LISTS = {"crop_season": "CROP_SEASON", "agro_ecological_zone": "AGRO_ECOLOGICAL_ZONE"}
# Source choice lists replaced by an inline Master Data list
REPLACES = {"production_season": "crop_season", "season": "crop_season", "ecological_zone": "agro_ecological_zone"}
# External CSV (media file name in the form) -> (file written, Master Data attribute)
FILE_LISTS = {"crop_name.csv": "CROP_COMMODITY", "seed_variety.csv": "SEED_VARIETY"}
GEO_FILES = {"region.csv": "region", "zone.csv": "zone", "woreda.csv": "woreda", "kebele1.csv": "kebele"}
# Source questions dropped from the forms: the registry has one variety field (seed_variety)
DROPPED_QUESTIONS = {"crop_variety_id"}
# Label of the variety question (the registry labels the field "Variety")
VARIETY_LABEL = "Variety"
YES_NO = {"only_yes", "yes_only"}

# Lists left as published, with the reason they are not Master Data lists. A list that is
# neither here, nor yes/no, nor a Master Data list above makes the build fail.
NOT_MASTER_DATA = {
    "cluster_status": "the transform and the form's own rules compare the answer to 'clustered' and 'independent'",
    "plot_cat": "the transform maps the published names to plot category codes and drops any other value",
    "ownership": "the transform maps the published names to ownership codes and drops any other value",
    "soil_fertility": "the transform maps the published names to soil fertility codes and drops any other value",
    "cropping_sys": "Master Data's cropping system codes differ from the registry's published values",
    "seed_class": "Master Data's seed type list adds a hybrid class the registry does not accept yet",
    "seed_source": "the transform maps the published names to seed source labels",
    "fertilizer_type": "the transform maps the published names to fertilizer codes",
    "fert_type": "organic or inorganic: the transform reads the name as given",
    "water_source": "the transform maps the published names to water source codes; Master Data's water source list is for households",
    "method": "the transform maps the published names to irrigation method codes",
    "frequency": "the transform maps the published names to irrigation frequency codes",
    "cult_method": "the transform maps the published names to machinery codes",
    "land_prep_method": "the published names are slash separated words, Master Data's codes are underscore separated",
    "sowing_status": "no Master Data list",
    "infestation_type": "the form's relevance rules compare the answer to pest, weed, disease, nutrient_deficiency, climate_shock; Master Data has three of the five",
    "growth_stage": "the transform upper-cases the name; Master Data prefixes its codes",
    "security_level": "no Master Data list",
    "pest_type": "no Master Data list with these names",
    "method_control": "no Master Data list",
    "pesticides_type": "no Master Data list",
    "weed_type": "no Master Data list with these names",
    "weedicides_type": "no Master Data list",
    "disease_type": "Master Data's crop disease codes are not the published names; the transform maps the published ones",
    "fungicide_type": "no Master Data list",
    "nutrient_type": "no Master Data list",
    "method_of_control": "no Master Data list",
    "m_control": "no Master Data list",
    "shock_type": "Master Data's shock type list is for households",
    "recovery_type": "no Master Data list",
    "crop_maturity": "no Master Data list",
}

IDENTITY_ROWS = [
    {"type": "begin_group", "name": "farmer_identity", "label": "Farmer Identity", "appearance": "field-list"},
    {"type": "text", "name": "farmer_id", "label": "Farmer ID",
     "hint": "FR- followed by 12 digits, for example FR-123456789012", "required": "yes",
     "required_message": "Enter the Farmer ID.",
     "constraint": "regex(., '^FR-[0-9]{12}$')",
     "constraint_message": "The Farmer ID must be FR- followed by 12 digits, for example FR-123456789012."},
    {"type": "text", "name": "fayda_id_entered", "label": "Fayda ID",
     "hint": "The 16 digit FAN or the 12 digit FIN. Spaces are allowed.", "required": "yes",
     "required_message": "Enter the Fayda ID.",
     "constraint": "regex(translate(., ' ', ''), '^([0-9]{12}|[0-9]{16})$')",
     "constraint_message": "The Fayda ID must be a 16 digit FAN or a 12 digit FIN. Spaces are allowed."},
    {"type": "calculate", "name": "fayda_id", "calculation": "translate(${fayda_id_entered}, ' ', '')"},
    {"type": "end_group"},
]
KEEP_FROM_OLD_IDENTITY = ("crop_year", "production_season")


def read_lists(*folders: Path) -> dict[str, dict]:
    """Every Master Data list found under the folders, by attribute id."""
    lists = {}
    for folder in folders:
        for path in sorted(folder.rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "attribute_id" in data and "values" in data:
                lists[data["attribute_id"]] = data
    return lists


def ordered(values: list[dict]) -> list[dict]:
    return sorted(values, key=lambda v: (v.get("sort_order") or 0, v["value_code"]))


def read_geography(folder: Path) -> dict[str, list[dict]]:
    levels = {level["level_id"]: level["level_mnemonic"] for level in json.loads((folder / "levels.json").read_text(encoding="utf-8"))}
    units: dict[str, list[dict]] = {level: [] for level in LEVELS}
    for value in json.loads((folder / "values.json").read_text(encoding="utf-8")):
        level = levels[value["level_id"]]
        if level in units:
            units[level].append(value)
    return units


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_media(lists: dict[str, dict], units: dict[str, list[dict]], media: Path) -> dict[str, int]:
    """The external lists, one CSV each; choice names are Master Data codes."""
    counts = {}
    categories = {v["value_code"]: v["value_display"] for v in lists["CROP_CATEGORY"]["values"]}
    crops = []
    for value in ordered(lists["CROP_COMMODITY"]["values"]):
        category = (value.get("attributes") or {}).get("category", "")
        if category and category not in categories:
            raise SystemExit(f"{value['value_code']}: category {category} is not a CROP_CATEGORY code")
        crops.append([value["value_code"], value["value_display"], category, categories.get(category, "")])
    write_csv(media / "crop_name.csv", ["name", "label", "category", "category_label"], crops)
    counts["crop_name.csv"] = len(crops)
    for file, attribute in (("seed_variety.csv", "SEED_VARIETY"),):
        rows = [[v["value_code"], v["value_display"]] for v in ordered(lists[attribute]["values"])]
        write_csv(media / file, ["name", "label"], rows)
        counts[file] = len(rows)
    for level in LEVELS:
        rows = [[u["level_value_id"], u["display_name"], u["level_value_id"], (u.get("parent_level_value_id") or "") if level != "region" else ""]
                for u in sorted(units[level], key=lambda u: u["level_value_id"])]
        write_csv(media / f"{level}.csv", ["name", "label", "code", "parent"], rows)
        counts[f"{level}.csv"] = len(rows)
    return counts


def sheet_rows(sheet) -> tuple[list[str], list[dict]]:
    header = [c.value for c in sheet[1]]
    columns = [h for h in header if h]
    rows = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        row = {h: v for h, v in zip(header, values) if h and v not in (None, "")}
        if row:
            rows.append(row)
    return columns, rows


def put_rows(book, title: str, columns: list[str], rows: list[dict]) -> None:
    old = book[title]
    index = book.index(old)
    book.remove(old)
    sheet = book.create_sheet(title, index)
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(c) for c in columns])


def with_columns(columns: list[str], *extra: str) -> list[str]:
    return columns + [e for e in extra if e not in columns]


def rebuild_identity(survey: list[dict], form_id: str) -> list[dict]:
    """Replace the first group with the two identity questions; keep crop year and season."""
    if survey[0].get("type") != "begin_group":
        raise SystemExit(f"{form_id}: the first row is not the identity group")
    end = next(i for i, row in enumerate(survey) if row.get("type") == "end_group")
    old = survey[1:end]
    kept = [row for row in old if row.get("name") in KEEP_FROM_OLD_IDENTITY]
    if {row["name"] for row in kept} != set(KEEP_FROM_OLD_IDENTITY):
        raise SystemExit(f"{form_id}: the old identity group has no crop year and production season")
    season_group = [{"type": "begin_group", "name": "production_season_info", "label": "Production Season", "appearance": "field-list"},
                    *kept, {"type": "end_group"}]
    return [dict(r) for r in IDENTITY_ROWS] + season_group + survey[end + 1:]


def use_master_data(survey: list[dict], form_id: str) -> set[str]:
    """Point the questions at the Master Data lists. Returns the external files used."""
    files_used = set()
    survey[:] = [row for row in survey if row.get("name") not in DROPPED_QUESTIONS]
    for row in survey:
        kind = row.get("type") or ""
        parts = kind.split()
        if len(parts) == 2 and parts[0] in ("select_one", "select_multiple") and parts[1] in REPLACES:
            parts[1] = REPLACES[parts[1]]
            row["type"] = " ".join(parts)
        if len(parts) == 2 and parts[0] == "select_one_from_file":
            if parts[1] in GEO_FILES:
                level = GEO_FILES[parts[1]]
                parts[1] = f"{level}.csv"
                row["type"] = " ".join(parts)
                if row.get("choice_filter"):
                    row["choice_filter"] = re.sub(r"^\s*(region|zone|woreda)\s*=", "parent=", row["choice_filter"])
            files_used.add(parts[1])
        if row.get("name") == "crop_category_id":
            row["calculation"] = "instance('crop_name')/root/item[name=${crop_name_id}]/category"
    for row in survey:
        if row.get("name") == "seed_variety":
            row["label"] = VARIETY_LABEL
    out = []
    for row in survey:
        out.append(row)
        if row.get("name") == "crop_category_id":
            out.append({"type": "calculate", "name": "crop_category_name",
                        "calculation": "instance('crop_name')/root/item[name=${crop_name_id}]/category_label"})
    for row in out:
        if row.get("name") == "note_crop_category":
            row["label"] = "Crop Category: ${crop_category_name}"
    survey[:] = out
    return files_used


def used_lists(survey: list[dict]) -> set[str]:
    """Names of the inline choice lists the questions use."""
    used = set()
    for row in survey:
        parts = (row.get("type") or "").split()
        if len(parts) == 2 and parts[0] in ("select_one", "select_multiple"):
            used.add(parts[1])
    return used


def build_choices(rows: list[dict], lists: dict[str, dict], form_id: str, survey: list[dict]) -> list[dict]:
    """Drop the replaced lists, add the Master Data ones, and refuse any other list we cannot account for."""
    used = used_lists(survey)
    unknown = sorted(n for n in used if n not in INLINE_LISTS and n not in YES_NO and n not in NOT_MASTER_DATA)
    if unknown:
        raise SystemExit(f"{form_id}: choice lists neither Master Data nor accounted for: {', '.join(unknown)}")
    kept = [r for r in rows if r.get("list_name") in used and r.get("list_name") not in INLINE_LISTS]
    for name, attribute in INLINE_LISTS.items():
        if name in used:
            for value in ordered(lists[attribute]["values"]):
                kept.append({"list_name": name, "name": value["value_code"], "label": value["value_display"]})
    return kept


def build_form(form_id: str, lists: dict[str, dict], version: str, source: Path, target: Path) -> dict:
    book = openpyxl.load_workbook(source / f"{form_id}.xlsx")
    s_cols, survey = sheet_rows(book["survey"])
    c_cols, choices = sheet_rows(book["choices"])
    t_cols, settings = sheet_rows(book["settings"])
    survey = rebuild_identity(survey, form_id)
    files = use_master_data(survey, form_id)
    choices = build_choices(choices, lists, form_id, survey)
    settings[0]["version"] = version
    s_cols = with_columns(s_cols, "required_message", "calculation")
    put_rows(book, "survey", s_cols, survey)
    put_rows(book, "choices", with_columns(c_cols, "list_name", "name", "label"), choices)
    put_rows(book, "settings", with_columns(t_cols, "version"), settings)
    target.mkdir(parents=True, exist_ok=True)
    out = target / f"{form_id}.xlsx"
    book.save(out)
    used = used_lists(survey)
    return {"form_id": form_id, "version": version, "workbook": out.name, "media": sorted(files),
            "master_data_lists": {n: INLINE_LISTS[n] for n in sorted(used & set(INLINE_LISTS))},
            "lists_left_as_published": sorted(used & set(NOT_MASTER_DATA))}


def build(pack: Path, geography: Path | None = None, version: str = VERSION, source: Path = SOURCE,
          target: Path = FORMS, media: Path = MEDIA) -> dict:
    lists = read_lists(pack / "codelists", pack / "domains")
    needed = {"CROP_SEASON", "AGRO_ECOLOGICAL_ZONE", "CROP_COMMODITY", "CROP_CATEGORY", "SEED_VARIETY"}
    missing = sorted(needed - set(lists))
    if missing:
        raise SystemExit(f"not found in the pack: {', '.join(missing)}")
    units = read_geography(geography or pack)
    counts = write_media(lists, units, media)
    forms = [build_form(form_id, lists, version, source, target) for form_id in FORM_IDS]
    report = {"version": version, "media_rows": counts, "forms": forms}
    (target / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pack", required=True, type=Path, help="the country pack (packs/ETH-OAN of openg2p-data)")
    parser.add_argument("--geography", type=Path, default=None,
                        help="levels.json + values.json of the target environment's geography (default: the pack's)")
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    print(json.dumps(build(args.pack, args.geography, args.version), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
