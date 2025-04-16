from sympy import simplify
from sympy.parsing.latex import parse_latex


def is_expression_equal(user_input: str, correct_input: str) -> bool:
    try:
        user_expr = simplify(parse_latex(user_input))
        correct_expr = simplify(parse_latex(correct_input))
        return user_expr.equals(correct_expr)
    except Exception as e:
        print("Error in comparison:", e)
        return False