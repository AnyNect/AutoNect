from setuptools import setup, find_packages

setup(
    name="autonect",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn[standard]",
        "pydantic",
        "markdownify",
        "playwright",
        "patchright",
    ],
    entry_points={
        "console_scripts": [
            # Primary CLI (matches the AnyNect org name)
            "AnyNect = src.web.launcher:main",
            # Backward-compat alias for existing installs
            "AutoNect = src.web.launcher:main",
        ],
    },
    author="AnyNect",
    description="Autonomous AI–Shell bridge",
    python_requires=">=3.10",
)