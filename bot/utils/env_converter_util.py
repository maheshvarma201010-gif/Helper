import ast
import json
import re
from typing import Dict, Any, List

def convert_to_env(content: str) -> str:
    """
    Safely converts config files (config.py, .json, .yaml, .ini, .php, credentials files)
    or text into KEY=value environment variables string.
    """
    if not content or not content.strip():
        return ""

    env_dict: Dict[str, str] = {}

    # Attempt 1: Parse as JSON
    trimmed = content.strip()
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                for k, v in data.items():
                    key_str = str(k).strip()
                    if isinstance(v, (dict, list)):
                        val_str = json.dumps(v)
                    else:
                        val_str = str(v)
                    env_dict[key_str] = val_str
                if env_dict:
                    return _format_env_dict(env_dict)
        except Exception:
            pass

    # Attempt 2: Safe Python AST Parsing
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    key = None
                    if isinstance(target, ast.Name):
                        key = target.id
                    elif isinstance(target, ast.Attribute):
                        key = target.attr

                    if key and not key.startswith("__"):
                        val = _get_ast_value(node.value)
                        if val is not None:
                            env_dict[key] = val
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and not node.target.id.startswith("__"):
                    key = node.target.id
                    val = _get_ast_value(node.value) if node.value else ""
                    if val is not None:
                        env_dict[key] = val

        if env_dict:
            return _format_env_dict(env_dict)
    except Exception:
        pass

    # Attempt 3: Regex Line-by-Line Parser for config.py / INI / PHP / YAML / .env
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//") or line.startswith(";"):
            continue

        # Pattern matches:
        # KEY = "val"
        # KEY = 'val'
        # KEY: "val"
        # export KEY=val
        # $KEY = "val";
        # define('KEY', 'val');
        define_match = re.match(r"^\s*define\s*\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*,\s*(.+)\s*\)\s*;?\s*$", line)
        if define_match:
            k = define_match.group(1)
            v = _clean_value_string(define_match.group(2))
            env_dict[k] = v
            continue

        kv_match = re.match(r"^\s*(?:export\s+|\$|const\s+|var\s+)?([A-Za-z0-9_]+)\s*[:=]\s*(.+)$", line)
        if kv_match:
            k = kv_match.group(1)
            v_raw = kv_match.group(2)
            v = _clean_value_string(v_raw)
            env_dict[k] = v

    return _format_env_dict(env_dict)

def _get_ast_value(node: ast.AST) -> Any:
    if node is None:
        return ""
    try:
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Dict, ast.Set)):
            return json.dumps(ast.literal_eval(node))
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{node.value.id}.{node.attr}" if isinstance(node.value, ast.Name) else node.attr
        elif isinstance(node, ast.Call):
            # E.g. os.getenv("KEY", "default") or str(...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "getenv":
                if node.args and isinstance(node.args[0], ast.Constant):
                    return f"${{{node.args[0].value}}}"
            return "Call()"
        else:
            return str(ast.literal_eval(node))
    except Exception:
        return ""

def _clean_value_string(val_str: str) -> str:
    val_str = val_str.strip()
    # Strip trailing semicolon, comma
    val_str = re.sub(r'[;,]$', '', val_str).strip()

    # Strip surrounding quotes
    if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
        val_str = val_str[1:-1]

    # Handle python/php booleans and nulls
    if val_str.lower() in ["true", "false"]:
        val_str = val_str.capitalize() if val_str.lower() == "true" else "False"

    return val_str

def _format_env_dict(env_dict: Dict[str, str]) -> str:
    lines = []
    for k, v in env_dict.items():
        clean_v = str(v).replace("\n", " ")
        lines.append(f"{k}={clean_v}")
    return "\n".join(lines)
