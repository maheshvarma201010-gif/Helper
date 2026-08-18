import ast
import json
import re
from typing import Dict, Any, List, Optional

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

    # Attempt 2: Full or Statement-by-Statement Python AST Parsing
    try:
        tree = ast.parse(content)
        _extract_ast_nodes(tree, env_dict)
    except Exception:
        lines = content.splitlines()
        stmt_buffer = []
        for line in lines:
            stmt_buffer.append(line)
            try:
                sub_tree = ast.parse("\n".join(stmt_buffer))
                _extract_ast_nodes(sub_tree, env_dict)
                stmt_buffer = []
            except Exception:
                if len(stmt_buffer) > 30:
                    stmt_buffer.pop(0)

    # Attempt 3: Line-by-Line Regex Parser (complements AST)
    for line in content.splitlines():
        line_s = line.strip()
        if not line_s or line_s.startswith("#") or line_s.startswith("//") or line_s.startswith(";"):
            continue

        define_match = re.match(r"^\s*define\s*\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*,\s*(.+)\s*\)\s*;?\s*$", line_s)
        if define_match:
            k = define_match.group(1)
            if k not in env_dict:
                v = _clean_value_string(define_match.group(2), env_dict)
                env_dict[k] = v
            continue

        kv_match = re.match(r"^\s*(?:export\s+|\$|const\s+|var\s+)?([A-Za-z0-9_]+)\s*[:=]\s*(.+)$", line_s)
        if kv_match:
            k = kv_match.group(1)
            v_raw = kv_match.group(2)
            if k not in env_dict:
                v = _clean_value_string(v_raw, env_dict)
                env_dict[k] = v

    return _format_env_dict(env_dict)

def _extract_ast_nodes(tree: ast.AST, env_dict: Dict[str, str]):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                key = None
                if isinstance(target, ast.Name):
                    key = target.id
                elif isinstance(target, ast.Attribute):
                    key = target.attr

                if key and not key.startswith("__"):
                    val = _get_ast_value(node.value, env_dict)
                    if val is not None and val != "Call()":
                        env_dict[key] = str(val)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and not node.target.id.startswith("__") and node.value is not None:
                key = node.target.id
                val = _get_ast_value(node.value, env_dict)
                if val is not None and val != "Call()":
                    env_dict[key] = str(val)

def _get_ast_value(node: ast.AST, env_dict: Optional[Dict[str, str]] = None) -> Any:
    if node is None:
        return ""
    if env_dict is None:
        env_dict = {}

    try:
        if isinstance(node, ast.Constant):
            return str(node.value)

        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elements = [_get_ast_value(elt, env_dict) for elt in node.elts]
            return json.dumps(elements)

        elif isinstance(node, ast.Dict):
            d = {}
            for k_node, v_node in zip(node.keys, node.values):
                k = _get_ast_value(k_node, env_dict) if k_node else ""
                v = _get_ast_value(v_node, env_dict)
                d[k] = v
            return json.dumps(d)

        elif isinstance(node, ast.Name):
            # Lookup in env_dict if already defined
            if node.id in env_dict:
                return env_dict[node.id]
            elif node.id in ["True", "False", "None"]:
                return node.id
            return node.id

        elif isinstance(node, ast.Attribute):
            return f"{node.value.id}.{node.attr}" if isinstance(node.value, ast.Name) else node.attr

        elif isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            # Case A: getenv / environ.get Call
            if func_name in ["getenv", "get"]:
                if len(node.args) >= 2:
                    return _get_ast_value(node.args[1], env_dict)
                elif len(node.args) == 1:
                    val = _get_ast_value(node.args[0], env_dict)
                    return f"${{{val}}}"
                return ""

            # Case B: Type cast functions like int(...), str(...), float(...), bool(...)
            if func_name in ["int", "str", "float", "bool", "list", "dict", "set", "getattr"]:
                if node.args:
                    return _get_ast_value(node.args[0], env_dict)
                return ""

            # Case C: Any other function call - search args for default literals
            if node.args:
                for arg in reversed(node.args):
                    v = _get_ast_value(arg, env_dict)
                    if v and v != "Call()":
                        return v

            return ""

        elif isinstance(node, ast.IfExp):
            val = _get_ast_value(node.body, env_dict)
            if not val or val == "Call()":
                val = _get_ast_value(node.test, env_dict)
            return val or "False"

        elif isinstance(node, ast.Compare):
            left_val = _get_ast_value(node.left, env_dict)
            comparand = _get_ast_value(node.comparators[0], env_dict) if node.comparators else ""
            if left_val and comparand:
                return str(left_val == comparand)
            return left_val or "False"

        else:
            return str(ast.literal_eval(node))
    except Exception:
        # Fallback string extraction for unhandled AST nodes
        return ""

def _clean_value_string(val_str: str, env_dict: Optional[Dict[str, str]] = None) -> str:
    if env_dict is None:
        env_dict = {}

    val_str = val_str.strip()
    val_str = re.sub(r'[;,]$', '', val_str).strip()

    # If it references a known key
    if val_str in env_dict:
        return env_dict[val_str]

    # Handle getenv/environ.get regex extraction
    getenv_match = re.search(r'(?:getenv|environ\.get)\s*\(\s*["\'][^"\']+["\']\s*,\s*(.+)\s*\)', val_str)
    if getenv_match:
        default_part = getenv_match.group(1).strip()
        return _clean_value_string(default_part, env_dict)

    # Strip surrounding quotes
    if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
        val_str = val_str[1:-1]

    if val_str.lower() in ["true", "false"]:
        val_str = val_str.capitalize() if val_str.lower() == "true" else "False"

    return val_str

def parse_env_input(text: str) -> Dict[str, str]:
    """
    Parses environment variables from any input text (including comments, export statements,
    config.py files, JSON, YAML, or raw .env format) into a dictionary of KEY -> value.
    """
    if not text or not text.strip():
        return {}

    converted = convert_to_env(text)
    res = {}
    for line in converted.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            if " //" in v:
                v = v.split(" //", 1)[0].strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k:
                res[k] = v
    return res

def _format_env_dict(env_dict: Dict[str, str]) -> str:
    lines = []
    for k, v in env_dict.items():
        clean_v = str(v).replace("\n", " ")
        lines.append(f"{k}={clean_v}")
    return "\n".join(lines)
