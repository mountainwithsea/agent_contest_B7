from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Config:
    base_url: str
    text_model: str
    vision_model: str
    api_key: str = field(repr=False)

    @classmethod
    def load(cls, path: Path):
        values = {}
        for raw in path.read_text(encoding='utf-8-sig').splitlines():
            line = raw.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        required = ['DASHSCOPE_BASE_URL', 'DASHSCOPE_API_KEY', 'TEXT_MODEL', 'VISION_MODEL']
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError('Missing configuration: ' + ', '.join(missing))
        base = values['DASHSCOPE_BASE_URL'].rstrip('/')
        parsed = urlparse(base)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or not base.endswith('/compatible-mode/v1')):
            raise ValueError('Expected HTTPS OpenAI-compatible Base URL')
        return cls(base, values['TEXT_MODEL'], values['VISION_MODEL'], values['DASHSCOPE_API_KEY'])
