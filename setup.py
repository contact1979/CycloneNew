from setuptools import find_packages, setup

setup(
    name="crypto-arbitrage",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # Install all dependencies from requirements.txt
        # This includes both runtime and development dependencies
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "arbitrage=arbitrage_bot:main",
            "backtest=backtest:main",
        ],
    },
)
