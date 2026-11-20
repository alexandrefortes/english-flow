from graph_reader import SITUATIONS, TOPICS
from notebook_format import KINDS
from wiki_index import KINDS_OF_MATERIAL, STATES


STRING = {"type": "string"}
SAVE_ENTRY_FIELDS = {
    "kind": {"type": "string", "enum": list(KINDS)}, "title": STRING, "content": STRING,
    "sources": {"type": "array", "items": STRING},
}
SEARCH_WIKI_FIELDS = {
    "kind": {"type": "string", "enum": list(KINDS_OF_MATERIAL)},
    "source": {"type": "string", "enum": ["Doist", "Zulip", "Projeto"]},
    "situation": {"type": "string", "enum": list(SITUATIONS)},
    "topic": {"type": "string", "enum": [*TOPICS, "leitura-contextual"]},
    "function": STRING,
    "text": {"type": "string", "minLength": 1, "maxLength": 200},
    "curation": {"type": "string", "enum": list(STATES)},
    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
}
READ_WIKI_ITEM_FIELDS = {
    "item_id": STRING, "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
    "limit": {"type": "integer", "minimum": 1, "maximum": 20000},
}


def validate(arguments, fields, required=()):
    if not isinstance(arguments, dict) or arguments.keys() - fields.keys() or set(required) - arguments.keys():
        raise ValueError("Invalid arguments.")
    for key, value in arguments.items():
        if fields[key]["type"] == "string" and not isinstance(value, str):
            raise ValueError(f'{key} must be text.')
        field = fields[key]
        if "enum" in field and value not in field["enum"]:
            raise ValueError(f'Invalid value for {key}.')
        if "minLength" in field and (len(value.strip()) < field["minLength"] or len(value) > field["maxLength"]):
            raise ValueError(f'Invalid length for {key}.')
        if field["type"] == "boolean" and type(value) is not bool:
            raise ValueError(f'{key} must be true or false.')
        if field["type"] == "integer" and (
            type(value) is not int or not field["minimum"] <= value <= field["maximum"]
        ):
            raise ValueError(f"Use an integer between {field['minimum']} and {field['maximum']} for {key}.")
        if fields[key]["type"] == "array" and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
            raise ValueError(f'{key} must be a list of strings.')
