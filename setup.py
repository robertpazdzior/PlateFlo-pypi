import setuptools

with open('README.md', 'r', encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="plateflo",
    version="0.0.1",
    author="Robert Pazdzior",
    author_email="rpazdzior@protonmail.com",
    description="PlateFlo perfusion system Python tools.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rpazdzior/OmniPerf",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3',
    install_requires=['pyserial']
)
