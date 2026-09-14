import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

class EnvManager:
    @staticmethod
    def parse_env_content(content: str) -> Dict[str, str]:
        """
        Parses standard .env content line by line into a dictionary.
        Handles quotes, empty lines, and comments (#).
        """
        env_vars = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Strip leading/trailing matching quotes if present
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                if key:
                    env_vars[key] = value
        return env_vars

    @staticmethod
    def mask_env_dict(env_vars: Dict[str, str]) -> Dict[str, str]:
        """
        Returns a dictionary where secret values are masked for safe display.
        """
        masked = {}
        secret_keywords = ["key", "token", "secret", "password", "hash", "uri", "url", "auth"]
        for k, v in env_vars.items():
            k_lower = k.lower()
            if any(keyword in k_lower for keyword in secret_keywords):
                if len(v) <= 4:
                    masked[k] = "****"
                else:
                    masked[k] = f"{v[:2]}****{v[-2:]}"
            else:
                masked[k] = v
        return masked
