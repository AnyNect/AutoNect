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
            "AutoNect = src.web.launcher:main",
        ],
    },
    author="AnyNect",
    description="Autonomous AI–Shell bridge",
    python_requires=">=3.10",
)