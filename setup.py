from setuptools import setup, find_packages

setup(
    name="saecs",
    version="0.1.0",
    description="Sistema Autónomo de Evolución Continua de Software",
    author="SAECS",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[],
    entry_points={
        "console_scripts": [
            "saecs=saecs.cli:main",
        ],
    },
    extras_require={
        "dev": ["pytest"],
    },
)
