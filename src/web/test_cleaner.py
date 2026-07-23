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
        "name": "citations, lists, domains",
        "raw": (
            "Based on my research, the website kt200ii.net is not the official website for "
            "the KT200II programmer. It appears to be an independent reseller or a third-party "
            "storefront.\n\n"
            "Here is a breakdown of my findings:\n\n"
            "\U0001f9d0 What is on kt200ii.net?\n\n"
            "The page you linked is a product sales page for the KT200II ECU/TCU Programmer , "
            "an automotive diagnostic tool used for reading and writing data on engine and "
            "transmission control units .\n\n"
            "It offers three versions of the tool :\n\n"
            "Basic Version: $700 USD Full Version: $855 USD Ultimate Version: $1330 USD "
            "\U0001f6a9 Why It's Likely Not Official\n\n"
            "The Official Brand is \"ECUHELP\": The KT200II is a product of a brand called "
            "ECUHELP . The official domain names associated with ECUHELP are primarily "
            "ecuhelp.org and kt200.org  .\n\n"
            "kt200ii.net is a Reseller: The site itself lists contact information for "
            "\"ECUHELP\" , but it is operating under a different domain, which is a common "
            "practice for authorized dealers. However, there is no clear indication on the site "
            "that it is the manufacturer's official store.\n\n"
            "Official Support Channels: Official support and updates for the KT200II are "
            "typically found on kt200.org and ecuhelp.org . The kt200ii.net site is not "
            "mentioned in official support circles.\n\n"
            "\U0001f4a1 Recommendations\n\n"
            "For Official Information: Visit the official websites at www.ecuhelp.org or "
            "www.kt200.org for product specs, official software updates, and support  .\n\n"
            "If Considering a Purchase: While kt200ii.net might be a legitimate reseller, it's "
            "always safer to buy directly from the official manufacturer or an authorized "
            "distributor to ensure you receive a genuine product, valid warranty, and proper "
            "after-sales support."
        ),
    },
    {
        "name": "real response with bold lists and already-backticked URLs",
        "raw": (
            "Based on my research, the website `kt200ii.net` appears to be a third-party "
            "reseller or affiliate site, not the official manufacturer's website for the KT200II "
            "programmer.\n\n"
            "\U0001f50d What is on the Page?\n\n"
            "The page you linked is a product sales page for the KT200II ECU/TCU Programmer, "
            "an automotive diagnostic tool used for reading and writing data on Engine Control "
            "Units (ECUs) and Transmission Control Units (TCUs).\n\n"
            "The page lists three versions of the device:\n\n"
            "KT200II Basic ($700 USD): Supports car & truck protocols, suitable for everyday "
            "workshop jobs.\n\n"
            "KT200II Full ($855 USD): Adds support for motorcycles, ATVs, marine, and "
            "agricultural machinery. Includes an offline dongle.\n\n"
            "KT200II Ultimate ($1,330 USD): Includes everything in the Basic and Full "
            "versions, plus the complete KT200PLUS kit and one-click DTC OFF & IMMO OFF "
            "features.\n\n"
            'The site itself claims to be an "Official ECUHELP Product".\n\n'
            "\U0001f3e2 Is it Official?\n\n"
            "Based on available information, it is highly unlikely that `kt200ii.net` is the "
            "official website.\n\n"
            "Here's what my research indicates:\n\n"
            'The Official Brand is "ECUHELP": The KT200II is a product of the brand '
            "ECUHELP. The manufacturer is identified as Shenzhen Kasheng Electronic "
            "Technology Co., LTD.\n\n"
            "Official Website and Support: Multiple sources, including official-looking tech "
            "support pages, point to `https://`www.ecuhelpshop.com`/` as the official shop and "
            "support portal. Another official-looking domain is www.ecuhelp.org.\n\n"
            "Domain is Not Officially Linked: The domain `kt200ii.net` does not appear in "
            "any search results as an official ECUHELP or manufacturer domain. The official "
            "support and technical resources are consistently found on `ecuhelpshop.com`, "
            "`kt200.org`, and ecuhelp.org.\n\n"
            "\u26a0\ufe0f What This Means for You\n\n"
            "Not the Manufacturer: You would be buying from a reseller, not the official "
            "source.\n\n"
            "Warranty & Support: Any warranty or technical support would be handled by this "
            "reseller, not the manufacturer.\n\n"
            "Prices: The prices listed may differ from other sellers.\n\n"
            "\U0001f4dd Recommendations\n\n"
            "Verify with the Manufacturer: For absolute certainty, you can contact the "
            "official support directly via the contact information on "
            "`https://`www.ecuhelpshop.com`/` to confirm if `kt200ii.net` is an authorized "
            "reseller.\n\n"
            "Proceed with Caution: If you choose to purchase from this site, treat it as you "
            "would any other third-party online retailer. It's advisable to research the "
            "site's reputation and understand their return and support policies before making "
            "a purchase."
        ),
    },
]

_FENCE_RE = re.compile(r"^```(\w*)$")


def validate_fences(text: str) -> list[str]:
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
        print("--- Cleaned output (first 2000 chars) ---")
        print(cleaned[:2000])
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