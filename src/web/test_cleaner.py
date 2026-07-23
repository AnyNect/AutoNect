"""Test script for the DeepSeek markdown cleaner."""

import re
from src.web.server import clean_deepseek_markdown


SAMPLES = [
    {
        "name": "premature docstring close",
        "raw": (
            "Here\u2019s a short Python function that computes the factorial of a non\u2011negative integer "
            "using an iterative approach, complete with a docstring and example usage.\n\n"
            "```python\n"
            "def factorial(n: int) -> int:\n"
            '    """\n'
            "    Compute the factorial of a non-negative integer n.\n"
            "```\n\n"
            "    The factorial of n (denoted as n!) is the product of all positive integers\n"
            "    less than or equal to n. By definition, 0! = 1.\n\n"
            "    Parameters\n"
            "    ----------\n"
            "    n : int\n"
            "        A non-negative integer.\n\n"
            "    Returns\n"
            "    -------\n"
            "    int\n"
            "        The factorial of n.\n\n"
            "    Raises\n"
            "    ------\n"
            "    TypeError\n"
            "        If n is not an integer.\n"
            "    ValueError\n"
            "        If n is negative.\n\n"
            "    Examples\n"
            "    --------\n"
            "    >>> factorial(5)\n"
            "    120\n"
            "    >>> factorial(0)\n"
            "    1\n"
            "    >>> factorial(1)\n"
            '    1\n'
            '    """\n'
            "    if not isinstance(n, int):\n"
            '        raise TypeError("n must be an integer")\n'
            "    if n < 0:\n"
            '        raise ValueError("n must be non-negative")\n\n'
            "    result = 1\n"
            "    for i in range(2, n + 1):\n"
            "        result *= i\n"
            "    return result\n\n\n"
            'if __name__ == "__main__":\n'
            "    # Example usage\n"
            "    print(factorial(5))   # 120\n"
            "    print(factorial(0))   # 1\n"
            "    print(factorial(10))  # 3628800\n"
            "How the Code Works\n\n"
            "Function signature and type hints\n"
            "def factorial(n: int) -> int: indicates that n should be an integer "
            "and the function returns an integer. Type hints are optional but improve "
            "readability and help with static analysis.\n\n"
            "Docstring\n"
            "The docstring (triple-quoted string) explains the purpose, parameters, "
            "return value, exceptions, and provides examples. This is the standard way "
            "to document Python functions, and tools like help(factorial) or Sphinx "
            "will display this information.\n\n"
            "Input validation\n\n"
            "isinstance(n, int) ensures the argument is an integer; otherwise a TypeError is raised.\n\n"
            "if n < 0 checks for negative values; a ValueError is raised because factorial "
            "is defined only for non-negative integers.\n\n"
            "Iterative computation\n\n"
            "result = 1 initialises the product.\n\n"
            "The for loop runs from 2 to n (inclusive). For each i, we multiply result by i. "
            "This avoids recursion and works efficiently even for moderately large n "
            "(within Python's integer limits).\n\n"
            "If n is 0 or 1, the loop does not run, and result remains 1, which is correct.\n\n"
            "Example usage\n"
            'The if __name__ == "__main__": block guards the example calls so they execute '
            "only when the script is run directly, not when imported as a module. "
            "This makes the function reusable while still demonstrating its use.\n\n"
            "This implementation is clear, safe, and follows Python best practices."
        ),
    },
    {
        "name": "bare python at start",
        "raw": (
            "python\n"
            "import math\n\n"
            "def is_prime(n: int) -> bool:\n"
            '    """\n'
            "    Determine whether a given integer is a prime number.\n"
            "    ...\n"
            '    """\n'
            "    if n <= 1:\n"
            "        return False\n"
            "    ...\n\n"
            "# Example usage\n"
            "print(is_prime(7))\n\n"
            "Explanation of how the code works\n\n"
            "The function is_prime(n) determines primality..."
        ),
    },
    {
        "name": "citations and missing backticks",
        "raw": (
            "Based on my research, the website kt200ii.net is not an official source for "
            "the KT200II ECU programmer. It appears to be a third-party reseller or an "
            "unofficial site, not the manufacturer's official store.\n\n"
            "Here's a breakdown of my findings:\n\n"
            "\U0001f4c4 What the Page Is\n\n"
            "The page you linked is a product sales page for the KT200II ECU/TCU Programmer-"
            "1\n. It describes the tool and lists three versions with their prices-"
            "1\n:\n\n"
            "*   **Basic Version**: $700 USD\n\n"
            "*   **Full Version**: $855 USD\n\n"
            "*   **Ultimate Version**: $1330 USD\n\n"
            "The page claims to be an \"Official ECUHELP Product\" site-"
            "1\n-"
            "79\n.\n\n"
            "\u274c Why It's Likely Not Official\n\n"
            "Several signs indicate this is not the official site:\n\n"
            "Official Brand & Store: The KT200II is manufactured by a brand called ECUHELP-"
            "-"
            ". Their official shop is https://www.ecuhelpshop.com/-"
            ", and they also use www.ecuhelp.org for official announcements-"
            "-"
            ". The site you found (kt200ii.net) is not one of these official domains.\n\n"
            "Unofficial Contact Details: The contact information on kt200ii.net uses a Gmail "
            "email address (yunduo191613`@gmail.com`)-"
            "79\n. An official business would typically use a professional email address "
            "associated with its own domain.\n\n"
            "Placeholder Pages: The \"/about\" and \"/contact\" pages on the site show placeholder "
            "content like \"AI & Developer Tools\"-"
            "89\n-"
            "90\n, which is a strong indicator of a low-quality or quickly assembled site, "
            "not a professional, official storefront.\n\n"
            "No Official Endorsement: A search for kt200ii.net on the official ECUHELP shop "
            "(ecuhelpshop.com) and support site (kt200.org) yields no results-"
            ". The official brand does not appear to acknowledge or link to this site.\n\n"
            "\U0001f48e Conclusion\n\n"
            "While the page describes a real product (the KT200II programmer), the website "
            "itself is not the official manufacturer's site. It is most likely run by an "
            "unauthorized third-party reseller. If you are considering a purchase, it would "
            "be safer to buy directly from the official ECUHELP shop at "
            "https://www.ecuhelpshop.com/ to ensure you're getting a genuine product and "
            "proper support."
        ),
    },
]

# A fence delimiter is a line that consists ONLY of ``` with an optional language tag.
_FENCE_RE = re.compile(r"^```(\w*)$")


def validate_fences(text: str) -> list[str]:
    """Stack‑based validator that only counts true fence delimiters."""
    issues = []
    stack = []
    for lineno, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if not _FENCE_RE.match(stripped):
            continue
        if len(stack) > 0:
            stack.pop()
        else:
            stack.append(lineno)
    if stack:
        issues.append(f"Unclosed fence(s) opened at line(s): {stack}")
    return issues


def main():
    for sample in SAMPLES:
        print(f"\n{'='*60}")
        print(f"Test: {sample['name']}")
        raw = sample["raw"]
        cleaned = clean_deepseek_markdown(raw)
        print("--- Cleaned output (first 1200 chars) ---")
        print(cleaned[:1200])
        issues = validate_fences(cleaned)
        if issues:
            print("\n⚠️  Issues detected:")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print("\n✅ Fences are balanced.")
    print("\nDone.")


if __name__ == "__main__":
    main()