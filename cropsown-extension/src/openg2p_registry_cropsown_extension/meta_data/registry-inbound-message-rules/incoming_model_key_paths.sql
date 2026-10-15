INSERT INTO "public"."incoming_model_key_paths" (
    "key_path_id",
    "data_model_id",
    "key_path_for_message_id",
    "key_path_for_sender",
    "key_path_for_signature",
    "key_path_for_signature_payload",
    "is_list",
    "key_path_for_list_elements"
) VALUES
(
    '4a5d9a8e-ffef-466a-9d00-d8bd39b0337c',
    'c331ba96-ac35-4014-9d13-4ef327f6b79b',
    '$.body.header.message_id',
    '$.body.header.sender_id',
    '$.body.signature',
    '$.body[''header'',''message'']',
    'FALSE',
    ''
),
(
    '5a5d9a8e-ffef-466a-9d00-d8bd39b0337d',
    'e442ca96-ac35-4014-9d13-4ef327f6b79c',
    '$.body.header.message_id',
    '$.body.header.sender_id',
    '$.body.header.signature',
    '$.body.message',
    'FALSE',
    ''
)
ON CONFLICT ("data_model_id") DO NOTHING;
