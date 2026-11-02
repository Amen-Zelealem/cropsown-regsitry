# Crop Sown bulk import from a file

The Crop Sown registry takes intakes from a CSV or Excel file through the staff portal menu **Import from file**, one entry per intake form. This page is the column specification. The blank header files are in `import-templates/`.

## How an upload is handled

1. Staff with the intake-submission edit permission upload a `.csv` or `.xlsx` file for one form.
2. The platform import worker reads the first sheet and passes every row on as one flat record.
3. A Jinja incoming template (`templates/crop_file_import_<form>_intake.j2`) maps the columns to the sections of the form. There is no Python mapping.
4. Every row becomes an intake submission. It waits for its Farmer to be approved in the Farmer registry, then goes through the two-stage approval (an officer, then a second officer; an admin can act at either stage). Nothing is written to the register directly.

## File rules

- One file per form. The first row holds the column names exactly as below (letter case is ignored). Columns not listed are ignored; columns may be in any order.
- One row is one intake. The cluster rows of a planning intake and the infestation rows of a sowing intake are **not** imported. Add them in the staff portal or by change request after the intake exists.
- A blank cell means "not given". Required columns are checked when the intake is saved and submitted.
- Numbers use a decimal point and no thousands separator. Dates are `YYYY-MM-DD` (a time after the date is dropped, as Excel writes it). Yes/no columns take `yes`, `no`, `true`, `false`, `1` or `0`.
- Dropdown columns take the Master Data **code**, never the label. Where a column takes several values, separate them with a semicolon.
- A row with a value the register cannot take (for example a letter in a number column) fails on its own, with the column named in the error; the other rows of the file continue. Check the row errors of the upload when the count of imported rows is lower than the count in the file.
- The farmer is named by the Farmer ID and one Fayda ID (FIN or FAN). Nothing else about the farmer is imported; the Farmer registry owns it.

## Planning intake (`crop_planning_intake_import_template.csv`)

Import configuration: `file_import_to_crop_planning_intake`.

| Column | Maps to | Required | Format or allowed codes |
|---|---|---|---|
| `farmer_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | FR- followed by 12 digits, for example FR-000000000001 |
| `fayda_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | A 12-digit FIN or a 16-digit FAN, digits only (spaces are dropped) |
| `crop_year` | Production Season (`cs_intake_season`) | Yes | Four-digit year, for example 2026 |
| `production_season` | Production Season (`cs_intake_season`) | Yes | Code from the CROP_SEASON list below. |
| `region` | Location (`cs_cropsown_location`) and the plot row | No | Master Data geo unit id (P-code), for example ET04 |
| `zone` | Location (`cs_cropsown_location`) and the plot row | No | Master Data geo unit id (P-code), for example ET0404 |
| `woreda` | Location (`cs_cropsown_location`) and the plot row | No | Master Data geo unit id (P-code), for example ET040404 |
| `kebele` | Location (`cs_cropsown_location`) and the plot row | No | Master Data geo unit id (P-code), for example ET040404888003 |
| `latitude` | Location (`cs_cropsown_location`) and the plot row | No | Decimal degrees; needs the longitude too |
| `longitude` | Location (`cs_cropsown_location`) and the plot row | No | Decimal degrees; needs the latitude too |
| `land_id` | `cs_planning_details` | Yes | Text |
| `plot_category` | `cs_planning_details` | No | Code from the PLOT_CATEGORY list below. |
| `ownership_type` | `cs_planning_details` | No | Code from the OWNERSHIP_TYPE list below. |
| `soil_fertility_type` | `cs_planning_details` | No | Code from the SOIL_FERTILITY list below. |
| `season` | `cs_planning_details` | No | Code from the CROP_SEASON list below. Blank means the production season. |
| `commodity` | `cs_planning_details` | Yes | Code from the CROP_COMMODITY list below. |
| `crop_category` | `cs_planning_details` | No | Code from the CROP_CATEGORY list below. |
| `local_name` | `cs_planning_details` | No | Text |
| `scientific_name` | `cs_planning_details` | No | Text |
| `seed_variety` | `cs_planning_details` | No | The variety (shown as "Variety"): code from the SEED_VARIETY list below. |
| `planned_fertilizer_type` | `cs_planning_details` | No | Code from the FERTILIZER_TYPE list below. |
| `water_source` | `cs_planning_details` | No | Code from the WATER_SOURCE list below. |
| `water_source_method` | `cs_planning_details` | No | Code from the WATER_SOURCE_METHOD list below. |
| `water_source_frequency` | `cs_planning_details` | No | Code from the WATER_SOURCE_FREQUENCY list below. |
| `da_name` | `cs_planning_details` | No | Text |
| `da_mobile_number` | `cs_planning_details` | No | Text |
| `supervisor_name` | `cs_planning_details` | No | Text |
| `supervisor_mobile_number` | `cs_planning_details` | No | Text |
| `land_area` | `cs_planning_details` | No | Number, digits and an optional decimal point |
| `planned_area` | `cs_planning_details` | No | Number, digits and an optional decimal point |
| `expected_yield` | `cs_planning_details` | No | Number, digits and an optional decimal point |
| `planned_seed_qty` | `cs_planning_details` | No | Number, digits and an optional decimal point |
| `planned_fertilizer_qty` | `cs_planning_details` | No | Number, digits and an optional decimal point |
| `start_month` | `cs_planning_details` | No | Whole number |
| `start_day` | `cs_planning_details` | No | Whole number |
| `end_month` | `cs_planning_details` | No | Whole number |
| `end_day` | `cs_planning_details` | No | Whole number |
| `growth_duration_days` | `cs_planning_details` | No | Whole number |
| `planned_labor` | `cs_planning_details` | No | Whole number |
| `start_gc` | `cs_planning_details` | No | YYYY-MM-DD |
| `end_gc` | `cs_planning_details` | No | YYYY-MM-DD |
| `planned_date` | `cs_planning_details` | No | YYYY-MM-DD |
| `is_plot_not_registered` | `cs_planning_details` | No | yes or no (also true/false, 1/0) |
| `cropping_system` | `cs_planning_details` | No | `MONO_CROPPING`, `INTER_CROPPING` |
| `seed_class` | `cs_planning_details` | No | `LOCAL`, `IMPROVED` |
| `seed_source` | `cs_planning_details` | No | `GOVERNMENT / WOREDS AGRICULTURE`, `AGRICULTURE COOPERATIVE / UNION`, `PRIVATE SEED ENTERPRISE`, `FARMER-TO-FARMER EXCHANGE / SAVED` |

## Cultivation intake (`crop_cultivation_intake_import_template.csv`)

Import configuration: `file_import_to_crop_cultivation_intake`.

| Column | Maps to | Required | Format or allowed codes |
|---|---|---|---|
| `farmer_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | FR- followed by 12 digits, for example FR-000000000001 |
| `fayda_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | A 12-digit FIN or a 16-digit FAN, digits only (spaces are dropped) |
| `crop_year` | Production Season (`cs_common_intake_season`) | Yes | Four-digit year, for example 2026 |
| `production_season` | Production Season (`cs_common_intake_season`) | Yes | Code from the CROP_SEASON list below. |
| `land_id` | `cs_cultivation_details` | Yes | Text |
| `season` | `cs_cultivation_details` | No | Code from the CROP_SEASON list below. Blank means the production season. |
| `commodity` | `cs_cultivation_details` | Yes | Code from the CROP_COMMODITY list below. |
| `crop_category` | `cs_cultivation_details` | No | Code from the CROP_CATEGORY list below. |
| `local_name` | `cs_cultivation_details` | No | Text |
| `scientific_name` | `cs_cultivation_details` | No | Text |
| `cultivation_type` | `cs_cultivation_details` | No | Code from the MACHINERY list below. |
| `seed_variety` | `cs_cultivation_details` | No | The variety (shown as "Variety"): code from the SEED_VARIETY list below. |
| `actual_fertilizer_type` | `cs_cultivation_details` | No | Code from the FERTILIZER_TYPE list below. |
| `water_source` | `cs_cultivation_details` | No | Code from the WATER_SOURCE list below. |
| `water_source_method` | `cs_cultivation_details` | No | Code from the WATER_SOURCE_METHOD list below. |
| `water_source_frequency` | `cs_cultivation_details` | No | Code from the WATER_SOURCE_FREQUENCY list below. |
| `da_name` | `cs_cultivation_details` | No | Text |
| `da_mobile_number` | `cs_cultivation_details` | No | Text |
| `supervisor_name` | `cs_cultivation_details` | No | Text |
| `supervisor_mobile_number` | `cs_cultivation_details` | No | Text |
| `land_area` | `cs_cultivation_details` | No | Number, digits and an optional decimal point |
| `actual_crop_area` | `cs_cultivation_details` | No | Number, digits and an optional decimal point |
| `actual_yield` | `cs_cultivation_details` | No | Number, digits and an optional decimal point |
| `actual_seed_qty` | `cs_cultivation_details` | No | Number, digits and an optional decimal point |
| `actual_fertilizer_qty` | `cs_cultivation_details` | No | Number, digits and an optional decimal point |
| `start_month` | `cs_cultivation_details` | No | Whole number |
| `start_day` | `cs_cultivation_details` | No | Whole number |
| `end_month` | `cs_cultivation_details` | No | Whole number |
| `end_day` | `cs_cultivation_details` | No | Whole number |
| `actual_growth_duration_days` | `cs_cultivation_details` | No | Whole number |
| `start_gc` | `cs_cultivation_details` | No | YYYY-MM-DD |
| `end_gc` | `cs_cultivation_details` | No | YYYY-MM-DD |
| `actual_cultivation_date` | `cs_cultivation_details` | No | YYYY-MM-DD |
| `is_plot_not_registered` | `cs_cultivation_details` | No | yes or no (also true/false, 1/0) |
| `cropping_system` | `cs_cultivation_details` | No | `MONO_CROPPING`, `INTER_CROPPING` |
| `actual_seed_class` | `cs_cultivation_details` | No | `LOCAL`, `IMPROVED` |
| `actual_seed_source` | `cs_cultivation_details` | No | `GOVERNMENT / WOREDS AGRICULTURE`, `AGRICULTURE COOPERATIVE / UNION`, `PRIVATE SEED ENTERPRISE`, `FARMER-TO-FARMER EXCHANGE / SAVED` |
| `land_prep_method` | `cs_cultivation_details` | No | Code from the LAND_PREP_METHOD list below. Several values separated by a semicolon. |

## Sowing intake (`crop_sowing_intake_import_template.csv`)

Import configuration: `file_import_to_crop_sowing_intake`.

| Column | Maps to | Required | Format or allowed codes |
|---|---|---|---|
| `farmer_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | FR- followed by 12 digits, for example FR-000000000001 |
| `fayda_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | A 12-digit FIN or a 16-digit FAN, digits only (spaces are dropped) |
| `crop_year` | Production Season (`cs_common_intake_season`) | Yes | Four-digit year, for example 2026 |
| `production_season` | Production Season (`cs_common_intake_season`) | Yes | Code from the CROP_SEASON list below. |
| `land_id` | `cs_sowing_details` | Yes | Text |
| `season` | `cs_sowing_details` | No | Code from the CROP_SEASON list below. Blank means the production season. |
| `commodity` | `cs_sowing_details` | Yes | Code from the CROP_COMMODITY list below. |
| `fertilizer_type` | `cs_sowing_details` | No | Code from the FERTILIZER_TYPE list below. |
| `cluster_name` | `cs_sowing_details` | No | Text |
| `cluster_season` | `cs_sowing_details` | No | Code from the CROP_SEASON list below. |
| `da_name` | `cs_sowing_details` | No | Text |
| `da_mobile_number` | `cs_sowing_details` | No | Text |
| `supervisor_name` | `cs_sowing_details` | No | Text |
| `supervisor_mobile_number` | `cs_sowing_details` | No | Text |
| `area_sown` | `cs_sowing_details` | Yes | Number, digits and an optional decimal point |
| `fertilizer_qty` | `cs_sowing_details` | No | Number, digits and an optional decimal point |
| `cluster_area_hectare` | `cs_sowing_details` | No | Number, digits and an optional decimal point |
| `cluster_area_sown` | `cs_sowing_details` | No | Number, digits and an optional decimal point |
| `sowing_date` | `cs_sowing_details` | Yes | YYYY-MM-DD |
| `has_pest_disease` | `cs_sowing_details` | No | yes or no (also true/false, 1/0) |
| `cluster_has_pest_disease` | `cs_sowing_details` | No | yes or no (also true/false, 1/0) |
| `agro_ecological_zone` | `cs_sowing_details` | No | `KOLLA`, `WOINA_DEGA`, `DEGA`, `WURCH`, `BEREHA` |
| `cluster_status` | `cs_sowing_details` | No | CLUSTER, INDEPENDENT, or both separated by a semicolon |

## Harvesting intake (`crop_harvesting_intake_import_template.csv`)

Import configuration: `file_import_to_crop_harvesting_intake`.

| Column | Maps to | Required | Format or allowed codes |
|---|---|---|---|
| `farmer_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | FR- followed by 12 digits, for example FR-000000000001 |
| `fayda_id` | Farmer lookup (`crop_farmer_lookup`) | Yes | A 12-digit FIN or a 16-digit FAN, digits only (spaces are dropped) |
| `crop_year` | Production Season (`cs_common_intake_season`) | Yes | Four-digit year, for example 2026 |
| `production_season` | Production Season (`cs_common_intake_season`) | Yes | Code from the CROP_SEASON list below. |
| `land_id` | `cs_harvest_details` | Yes | Text |
| `commodity` | `cs_harvest_details` | Yes | Code from the CROP_COMMODITY list below. |
| `cluster_name` | `cs_harvest_details` | No | Text |
| `da_name` | `cs_harvest_details` | No | Text |
| `da_mobile_number` | `cs_harvest_details` | No | Text |
| `supervisor_name` | `cs_harvest_details` | No | Text |
| `supervisor_mobile_number` | `cs_harvest_details` | No | Text |
| `area_harvested` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `qty_harvested` | `cs_harvest_details` | Yes | Number, digits and an optional decimal point |
| `post_harvest_loss_pct` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `qty_stored` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `qty_sold` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `cluster_area_harvested` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `cluster_qty_harvested` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `cluster_post_harvest_loss_pct` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `cluster_qty_stored` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `cluster_qty_sold` | `cs_harvest_details` | No | Number, digits and an optional decimal point |
| `harvest_date` | `cs_harvest_details` | Yes | YYYY-MM-DD |
| `cluster_harvest_date` | `cs_harvest_details` | No | YYYY-MM-DD |
| `crop_maturity_status` | `cs_harvest_details` | No | `READY_FOR_HARVEST`, `NOT_YET_READY_FOR_HARVEST` |
| `cluster_crop_maturity_status` | `cs_harvest_details` | No | `READY_FOR_HARVEST`, `NOT_YET_READY_FOR_HARVEST` |
| `cluster_status` | `cs_harvest_details` | No | CLUSTER, INDEPENDENT, or both separated by a semicolon |

## Code lists

The codes below are what Master Data serves; the template does not translate or look them up, so a code that Master Data does not hold is stored as given. Static choices (cropping system, seed class, seed source, maturity, agro-ecological zone) are listed in the tables above.

### CROP_SEASON

Master Data list `CROP_SEASON` as the ETH-OAN pack seeds it.

`SEASON_MEHER`, `SEASON_BELG`, `SEASON_IRRIGATION`

### CROP_CATEGORY

Master Data list `CROP_CATEGORY` as the ETH-OAN pack seeds it.

`CROPCAT_CEREAL`, `CROPCAT_FOOD_LEGUME`, `CROPCAT_OILSEED`, `CROPCAT_FRUIT_VEGETABLE`, `CROPCAT_ROOT_TUBER`, `CROPCAT_STIMULANT`, `CROPCAT_INDUSTRIAL`, `CROPCAT_SPICE_MEDICINAL_AROMATIC`, `CROPCAT_OTHER`

### CROP_COMMODITY

Master Data list `CROP_COMMODITY` as the ETH-OAN pack seeds it.

`CROP_TEFF`, `CROP_QUINOA`, `CROP_BREAD_WHEAT`, `CROP_DURUM_WHEAT`, `CROP_TRITICALE`, `CROP_EMMER_WHEAT`, `CROP_BUCKWHEAT`, `CROP_BARLEY`, `CROP_MALT_BARLEY`, `CROP_SORGHUM`, `CROP_FINGER_MILLET`, `CROP_PEARL_MILLET`, `CROP_FOXTAIL_MILLET`, `CROP_MAIZE`, `CROP_RICE`, `CROP_FABA_BEAN`, `CROP_CHICKPEA`, `CROP_LENTIL`, `CROP_FIELD_PEA`, `CROP_DEKOKO`, `CROP_COWPEA`, `CROP_HARICOT_BEAN`, `CROP_GRASS_PEA`, `CROP_MUNG_BEAN`, `CROP_ADZUKI_BEAN`, `CROP_LIMA_BEAN`, `CROP_COMMON_BEAN`, `CROP_NOUG`, `CROP_LINSEED`, `CROP_RAPESEED`, `CROP_ETHIOPIAN_MUSTARD`, `CROP_SUNFLOWER`, `CROP_SAFFLOWER`, `CROP_SOYBEAN`, `CROP_SESAME`, `CROP_GROUNDNUT`, `CROP_WINE_GRAPE`, `CROP_PEACH`, `CROP_BANANA`, `CROP_MANGO`, `CROP_PINEAPPLE`, `CROP_AVOCADO`, `CROP_ZIZIPHUS`, `CROP_FIG`, `CROP_PAPAYA`, `CROP_DATE_PALM`, `CROP_GARLIC`, `CROP_SHALLOT`, `CROP_CARROT`, `CROP_LETTUCE`, `CROP_SNAP_BEAN`, `CROP_CAULIFLOWER`, `CROP_SNOW_PEA`, `CROP_PEPPER`, `CROP_TOMATO`, `CROP_ONION`, `CROP_CABBAGE`, `CROP_WATERMELON`, `CROP_MUSKMELON`, `CROP_GREEN_COURGETTE`, `CROP_YELLOW_COURGETTE`, `CROP_BROCCOLI`, `CROP_SNAP_PEA`, `CROP_SWEET_CORN`, `CROP_FINE_BUSH_BEAN`, `CROP_OKRA`, `CROP_ANCHOTE`, `CROP_AMARANTH`, `CROP_PAK_CHOI`, `CROP_EGGPLANT`, `CROP_CUCUMBER`, `CROP_SUMMER_SQUASH`, `CROP_POTATO`, `CROP_SWEET_POTATO`, `CROP_RED_BEET`, `CROP_TARO`, `CROP_CASSAVA`, `CROP_ENSET`, `CROP_YAM`, `CROP_COFFEE`, `CROP_COTTON`, `CROP_KENAF`, `CROP_VERNONIA`, `CROP_CASTOR`, `CROP_CAMELINA`, `CROP_SUGARCANE`, `CROP_TOBACCO`, `CROP_CACAO`, `CROP_SWEET_ANNIE`, `CROP_PYRETHRUM`, `CROP_AFRICAN_MARIGOLD`, `CROP_CHAMOMILE`, `CROP_STEVIA`, `CROP_HIBISCUS`, `CROP_CITRONELLA_GRASS`, `CROP_LEMONGRASS`, `CROP_PEPPERMINT`, `CROP_SPEARMINT`, `CROP_JAPANESE_MINT`, `CROP_SPANISH_MINT`, `CROP_GERANIUM`, `CROP_LEMON_VERBENA`, `CROP_LAVENDER`, `CROP_MARJORAM_OREGANO`, `CROP_SAGE`, `CROP_ROSEMARY`, `CROP_LEMON_SCENTED_EUCALYPTUS`, `CROP_PALMAROSA`, `CROP_BLACK_PEPPER`, `CROP_GINGER`, `CROP_TURMERIC`, `CROP_CARDAMOM`, `CROP_VANILLA`, `CROP_CORIANDER`, `CROP_BLACK_CUMIN`, `CROP_WHITE_CUMIN`, `CROP_FENUGREEK`, `CROP_BASIL`, `CROP_KORARIMA`, `CROP_ROSE`, `CROP_OTHER`, `CROP_OAT`, `CROP_PIGEON_PEA`, `CROP_ALFALFA`, `CROP_BRACHIARIA`

### SEED_VARIETY

Master Data list `SEED_VARIETY`.

Too long to repeat here: use the `value_code` of each value in `packs/ETH-OAN/domains/agriculture/seed_variety.json` of the openg2p-data repository (for example `VAR_TEFF_QUNCHO`).

### SOIL_FERTILITY

Master Data list `SOIL_FERTILITY` as the ETH-OAN pack seeds it.

`SF_HIGH`, `SF_MEDIUM`, `SF_LOW`

### FERTILIZER_TYPE

Master Data list `FERTILIZER_TYPE` as the ETH-OAN pack seeds it.

`FERT_UREA`, `FERT_DAP`, `FERT_NPS`, `FERT_NPSB`, `FERT_NPSZNB`, `FERT_COMPOST`, `FERT_MANURE`, `FERT_BIO_RHIZO`, `FERT_ZINC_BORON`, `FERT_LIME`

### WATER_SOURCE

Master Data list `WATER_SOURCE` as the ETH-OAN pack seeds it.

`WS_RAINFED`, `WS_IRRIGATION_GROUND`, `WS_IRRIGATION_SURFACE`, `WS_WELL_GROUND`, `WS_WATER_HARVESTING`, `WS_SURFACE_WATER`

### PLOT_CATEGORY

Register list `PLOT_CATEGORY`, the codes the registry shows in the staff portal (`translation/domain.json`); the ETH-OAN pack does not carry this list.

`PLOT_CATEGORY_ANNUAL_CROP`, `PLOT_CATEGORY_BIENNIAL_CROP`, `PLOT_CATEGORY_PERENNIAL_CROP`

### OWNERSHIP_TYPE

Register list `OWNERSHIP_TYPE`, the codes the registry shows in the staff portal (`translation/domain.json`); the ETH-OAN pack does not carry this list.

`OWNERSHIP_TYPE_CROP_SHARING`, `OWNERSHIP_TYPE_FAMILY_GIFT`, `OWNERSHIP_TYPE_OWNER`, `OWNERSHIP_TYPE_TENANT`

### WATER_SOURCE_METHOD

Register list `WATER_SOURCE_METHOD`, the codes the registry shows in the staff portal (`translation/domain.json`); the ETH-OAN pack does not carry this list.

`WATER_SOURCE_METHOD_DRIP`, `WATER_SOURCE_METHOD_MANUAL`, `WATER_SOURCE_METHOD_OTHER`, `WATER_SOURCE_METHOD_SPRINKLER`, `WATER_SOURCE_METHOD_SURFACE`

### WATER_SOURCE_FREQUENCY

Register list `WATER_SOURCE_FREQUENCY`, the codes the registry shows in the staff portal (`translation/domain.json`); the ETH-OAN pack does not carry this list.

`WATER_SOURCE_FREQUENCY_AS_NEEDED`, `WATER_SOURCE_FREQUENCY_BIWEEKLY`, `WATER_SOURCE_FREQUENCY_DAILY`, `WATER_SOURCE_FREQUENCY_MONTHLY`, `WATER_SOURCE_FREQUENCY_OTHER`, `WATER_SOURCE_FREQUENCY_WEEKLY`

### MACHINERY

Register list `MACHINERY`, the codes the registry shows in the staff portal (`translation/domain.json`); the ETH-OAN pack does not carry this list.

`MACHINERY_COMBINER`, `MACHINERY_COMBINE_HARVESTER`, `MACHINERY_DEBO_JIGI`, `MACHINERY_EQUINE_OTHER`, `MACHINERY_FAMILY_LABOR`, `MACHINERY_HARVESTER`, `MACHINERY_HIRED_LABOR`, `MACHINERY_MAIZE_SHELLER`, `MACHINERY_MULTI_CROP_TRASHER`, `MACHINERY_OTHER`, `MACHINERY_OXEN_MANUAL`, `MACHINERY_OXEN_TILLAGE`, `MACHINERY_PLANTER`, `MACHINERY_POWER_TILLER`, `MACHINERY_RICE_POLISHER`, `MACHINERY_THRASHING_MACHINE`, `MACHINERY_TRACTOR`, `MACHINERY_TRACTOR_OXEN`, `MACHINERY_TRACTOR_PLOUGHING`

### LAND_PREP_METHOD

Register list `LAND_PREP_METHOD`, the codes the registry shows in the staff portal (`translation/domain.json`); the ETH-OAN pack does not carry this list.

`LAND_PREP_METHOD_BIOLOGICAL_MULCHING`, `LAND_PREP_METHOD_MANUAL_DIGGING`, `LAND_PREP_METHOD_MANUAL_LEVELING`, `LAND_PREP_METHOD_MINIMUM_TILLAGE`, `LAND_PREP_METHOD_RIDGING_FURROWING`, `LAND_PREP_METHOD_SHILSHALO`, `LAND_PREP_METHOD_SOIL_WATER_CONSERVATION_STRUCTURES`, `LAND_PREP_METHOD_TRACTOR_DISC_MOLDBOARD_PLOUGHING`, `LAND_PREP_METHOD_TRADITIONAL_MARESHA_PLOUGHING`

## Where the pieces live

| Piece | Where |
|---|---|
| Import configuration (one row per form) | `meta_data/registry-configurations/g2p_registry_import_file_configurations.sql` |
| Data models `file_import_to_crop_<form>_intake` | `meta_data/data-models/data_models.sql` |
| Key paths (`$.headers.*`, payload `$.body`) | `meta_data/registry-inbound-message-rules/incoming_model_key_paths.sql` |
| Semantic patterns (pass-through enricher) | `meta_data/registry-inbound-message-rules/incoming_model_semantic_patterns.sql` |
| Incoming templates and their documents | `incoming_templates.sql`, `meta_data/register-metadata/g2p_registry_documents.sql` |
| Jinja templates | `templates/crop_file_import_<form>_intake.j2` |
| Tests | `cropsown-extension/tests/test_file_import.py` |

The ODK connector keeps its own data model `odk_to_crop_intake`; file import does not touch it.

## Operating notes

- The import worker sends rows as the sender `Staff Portal`. That sender must exist as an active partner in Partner Management, or the first row aborts the whole file.
- The worker supplies the service token for the approval workflow itself (the Crop Sown extension requests one from the approval engine when a worker has no user token), so the worker needs the `COSS_FARMER_AWE_*` settings.
- Sample rows are not kept here. Sample import files belong in the openg2p-data repository.
