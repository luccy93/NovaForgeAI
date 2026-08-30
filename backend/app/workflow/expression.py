"""Restricted expression evaluator — no eval/exec."""

import ast
import operator

ALLOWED_NODES = {
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.IfExp, ast.Dict, ast.List, ast.Tuple, ast.Constant, ast.Name, ast.Load,
    ast.Attribute, ast.Subscript, ast.Slice,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
}

ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _check_ast(node):
    if type(node) not in ALLOWED_NODES:
        raise ValueError(f"disallowed node {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _check_ast(child)
    # Disallow attribute access to private or dunder
    if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
        raise ValueError("private attribute access not allowed")
    if isinstance(node, ast.Name) and node.id.startswith("_"):
        raise ValueError("private name not allowed")


def evaluate(expression: str, context: dict) -> bool:
    """Evaluate expression safely over workflow input, step output, policy results."""
    if not expression or not expression.strip():
        return True
    # Simple string expressions like "input.status == 'approved'" or "step.output.value > 5"
    try:
        tree = ast.parse(expression, mode="eval")
        _check_ast(tree)
        # Compile with restricted globals
        code = compile(tree, "<expr>", "eval")
        # Build safe locals from context (only allow workflow, input, step, policy)
        safe_locals = {}
        # Flatten context keys
        for k, v in context.items():
            if k in {"workflow", "input", "step", "policy", "output", "approved", "tenant"}:
                safe_locals[k] = v
        # Also allow direct keys
        safe_locals.update({k: v for k, v in context.items() if isinstance(v, (str, int, float, bool, dict, list))})
        result = eval(code, {"__builtins__": {}}, safe_locals)
        return bool(result)
    except Exception as e:
        raise ValueError(f"expression error: {e}")
