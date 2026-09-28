from urllib.parse import parse_qsl


def parse_click_form(body: bytes) -> dict[str, str]:
    try:
        encoded = body.decode("utf-8", errors="strict")
        pairs = parse_qsl(
            encoded,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=32,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("Malformed Click form") from error
    if not pairs:
        raise ValueError("Empty Click form")
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("Duplicate Click form field")
        fields[key] = value
    return fields
