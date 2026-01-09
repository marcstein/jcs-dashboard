"""
Setup script for MyCase Automation Agent
"""
from setuptools import setup, find_packages

setup(
    name="mycase-agent",
    version="1.0.0",
    description="AI-powered automation agent for MyCase legal practice management",
    author="Your Firm",
    python_requires=">=3.10",
    py_modules=[
        "config",
        "auth",
        "api_client",
        "templates",
        "database",
        "collections",
        "deadlines",
        "analytics",
        "agent",
    ],
    install_requires=[
        "httpx>=0.25.0",
        "python-dateutil>=2.8.2",
        "jinja2>=3.1.2",
        "click>=8.1.0",
        "rich>=13.0.0",
        "schedule>=1.2.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "mycase-agent=agent:main",
        ],
    },
)
