from setuptools import setup, find_packages

setup(
    name="crypto-arbitrage",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "numpy",
        "requests",
        "ccxt",
        "scipy",
        "matplotlib",
        "python-dotenv",
        "tabulate",
        "colorama"
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "arbitrage=arbitrage_bot:main",
            "backtest=backtest:main",
        ],
    },
)