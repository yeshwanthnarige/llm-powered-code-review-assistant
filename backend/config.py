import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./reviews.db')
    provider: str = os.getenv('REVIEW_PROVIDER', 'demo')
    api_key: str = os.getenv('OPENAI_API_KEY', '')
    model: str = os.getenv('OPENAI_MODEL', 'gpt-4')
    embedding_model: str = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    github_token: str = os.getenv('GITHUB_TOKEN', '')

    @property
    def embedding_id(self):
        return 'local-hash-v1' if self.provider == 'demo' else self.embedding_model + ':256'
