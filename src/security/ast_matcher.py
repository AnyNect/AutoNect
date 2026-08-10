import ast
import sys

def find_dangerous_calls(code: str) -> list[dict]:
    """Return list of dangerous AST nodes with line numbers."""
    dangerous = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return dangerous  # ignore malformed code

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for os.system, os.remove, shutil.rmtree, etc.
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ('system', 'remove', 'rmtree', 'unlink'):
                    dangerous.append({
                        'line': node.lineno,
                        'function': node.func.attr,
                        'args': [ast.unparse(arg) for arg in node.args],
                    })
            elif isinstance(node.func, ast.Name):
                if node.func.id in ('eval', 'exec', '__import__'):
                    dangerous.append({
                        'line': node.lineno,
                        'function': node.func.id,
                        'args': [ast.unparse(arg) for arg in node.args],
                    })
    return dangerous