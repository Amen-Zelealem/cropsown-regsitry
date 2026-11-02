"""Words around the platform's code-list validator; its rules stay in core.

When a request carries a code that is not on its Master Data list (a stale
form value, ODK or file import), core says
"record 0: commodity='CROP_NOT_REAL' is not a value of CROP_COMMODITY (permitted: ...)".
That names a record number, a database field, a list id and every permitted
code. It is reworded here to "Crop: choose a crop from the list." with the
field name the form shows, for every Master Data backed field on the crop forms.

The sentence is a registry translation (coss_code_choice), so it can be
changed in the registry's language data; this module holds the default.
"""

import re

DEFAULT_TEXT = "{label}: choose {noun} from the list."
TRANSLATION_KEY = "coss_code_choice"

# field -> (label as the forms show it, noun for "choose a ...")
FIELDS = {
    "commodity": ("Crop", "a crop"),
    "primary_commodity": ("Primary commodity", "a crop"),
    "secondary_commodity": ("Secondary commodity", "a crop"),
    "season": ("Season", "a season"),
    "production_season": ("Production season", "a season"),
    "cluster_season": ("Season (cluster)", "a season"),
    "crop_category": ("Crop category", "a category"),
    "seed_variety": ("Variety", "a variety"),
    "plot_category": ("Plot category", "a category"),
    "ownership_type": ("Ownership type", "one"),
    "soil_fertility_type": ("Soil fertility", "one"),
    "planned_fertilizer_type": ("Planned fertilizer type", "a fertilizer type"),
    "actual_fertilizer_type": ("Actual fertilizer type", "a fertilizer type"),
    "fertilizer_type": ("Actual fertilizer type", "a fertilizer type"),
    "water_source": ("Water source", "one"),
    "water_source_method": ("Water application method", "one"),
    "water_source_frequency": ("Watering frequency", "one"),
    "cultivation_type": ("Cultivation type", "one"),
    "land_prep_method": ("Land preparation method", "one"),
    "cluster_status": ("Cluster / non-cluster status", "one"),
    "infestation_type": ("Type of infestation", "one"),
    "pest_type": ("Pest type", "a pest"),
    "weed_type": ("Weed type", "a weed"),
    "disease_type": ("Disease type", "a disease"),
    "pest_name": ("Pest name", "a pest"),
    "pesticide_method": ("Pest control method", "one"),
}

_PROBLEM = re.compile(
    r"""record \d+: (\w+)=('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*") is not a value of (\S+) \(permitted: ([^)]*)\)"""
)


def field_label(field: str) -> tuple[str, str]:
    label, noun = FIELDS.get(field, (None, None))
    if label:
        return label, noun
    text = field.replace("_", " ").strip()
    return text[:1].upper() + text[1:], "one"


def problems_in(message: str) -> list[re.Match]:
    return list(_PROBLEM.finditer(message or ""))


def reword(message: str, messages: dict | None = None) -> str:
    """`message` with each code-list problem in plain words. Text that is not a
    code-list problem is kept as it is."""
    template = (messages or {}).get(TRANSLATION_KEY)
    template = template if isinstance(template, str) and template else DEFAULT_TEXT
    out, end, seen = [], 0, set()
    for match in problems_in(message):
        out.append(message[end:match.start()])
        label, noun = field_label(match.group(1))
        try:
            sentence = template.format(label=label, noun=noun)
        except (IndexError, KeyError, ValueError):
            sentence = DEFAULT_TEXT.format(label=label, noun=noun)
        if sentence not in seen:  # several rows with the same mistake say it once
            seen.add(sentence)
            out.append(sentence)
        end = match.end()
    out.append(message[end:])
    return " ".join(part for part in (p.strip(" ;") for p in out) if part)


def install_attribute_messages():
    from openg2p_fastapi_common.context import component_registry
    from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
    from openg2p_registry_core.services.g2p_attribute_value_validator import (
        G2PAttributeValueValidator,
    )

    class AttributeValueValidator(G2PAttributeValueValidator):
        async def validate_records(self, records, *, field_map=None):
            try:
                return await super().validate_records(records, field_map=field_map)
            except G2PRegistryException as error:
                if error.code != G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1]:
                    raise
                text = error.message or ""
                if not problems_in(text):
                    raise
                from .field_rules import _translations

                raise G2PRegistryException(code=error.code, message=reword(text, await _translations())) from error

    core = G2PAttributeValueValidator.get_component()
    if core is not None and getattr(core, "cropsown_messages", False):
        return core
    service = AttributeValueValidator()
    service.cropsown_messages = True
    component_registry.remove(service)
    first = next(
        (i for i, c in enumerate(component_registry) if isinstance(c, G2PAttributeValueValidator)),
        len(component_registry),
    )
    component_registry.insert(first, service)
    return service
