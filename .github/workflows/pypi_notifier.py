import subprocess

# import github
# import os

# # import pytest

# GH = github.Github(os.getenv("GITHUB_ACCESS_TOKEN"))
# GH_REPO = GH.get_repo(os.getenv("GITHUB_REPOSITORY"))

import pathlib
from urllib import request

from urllib.request import urlopen
import json

# importlib.metadata
#####################################################################
import importlib.metadata


def use_importlib_metadata():
    # List all installed distributions???
    distributions = importlib.metadata.distributions()

    # Create a dictionary to store package names and their versions .
    installed_packages = {}

    # Iterate over the distributions and get their name and version .
    for distribution in distributions:
        name = distribution.metadata["Name"]
        version = distribution.version
        installed_packages[name] = version

    # Print pair of package and the version .
    for package, version in installed_packages.items():
        print(f"{package}: {version}")
    #######################################################################


###### pip list way vs. importlib_metadata way ######
def get_installed_packages():
    # Run "pip list" and output in JSON format
    process = subprocess.run(
        ["pip", "list", "--format=json"], capture_output=True, text=True, check=True
    )

    # Parse the JSON output
    packages = json.loads(process.stdout)
    # print(packages)
    return packages


###### pip list way vs. importlib_metadata way ######


# From PyPI, get the latest package version for single package
def get_latest_package_version(package_name):
    with urlopen(f"https://pypi.org/pypi/{package_name}/json") as response:
        data = json.loads(response.read().decode())
        # print(data["info"]["version"]) # debug
        return data["info"]["version"]


# still need to do comparison to find out if theres newer version
# feetch all version from pypi, put them into list, version object, sort list, look at the greatest version found in pypi, then compare

### is it sorted?  there could have been bug fix version


# Iterate through all package we have to fetch latest
def get_entire_latest_package_version(our_packages):
    latest_versions = {}
    for package, _ in our_packages.items():
        latest_versions[package] = get_latest_package_version(package)
    return latest_versions


def mark_version_difference(our_packages, latest_packages):
    different_packages = {}
    # Check to see if there are version differences
    for package, version in our_packages.items():
        if version != latest_packages[package]:
            # If the version doesn't match,
            # store package name and latest version.
            different_packages[package] = latest_packages[package]

    return different_packages


def main():
    # load in list of packages and its version from requirements.txt that is in one directory above
    root_path = pathlib.Path(__file__).parent.parent.parent
    requirement_content = pathlib.Path(root_path, "requirements.txt").read_text(
        encoding="utf-8"
    )

    # stricter ->

    # Dictionary of package name and its version
    packages = {}
    for line in requirement_content.splitlines():
        # print(line)
        # If line has == and \ then perform line split to store package and version
        if "==" in line and line.endswith("\\"):
            requirement = line.removesuffix("\\")
            # dont use split
            # package, version = line.split("==")
            package, _, version = requirement.partition("==")

            # remove \ in version string and blank spaces
            # version = version.replace("\\", "").strip()
            # print(version)
            packages[package] = version

    latest_packages = get_entire_latest_package_version(packages)
    packages_with_difference = mark_version_difference(packages, latest_packages)

    # If package_with_difference is not empty,
    # generate github issue to state we may need to update version of package
    # if packages_with_difference:
    #     issue_body = "The following packages may need to be updated:\n"
    #     for package, version in packages_with_difference.items():
    #         issue_body += f"- {package}: {version}\n"
    #     GH_REPO.create_issue(
    #         title="Packages may need to be updated", body=issue_body, labels=["debt"]
    #     )
    # print("pytest version")
    # print(pytest.__version__)


if __name__ == "__main__":
    main()
    # get_installed_packages()
    use_importlib_metadata()
    # get_latest_package_version("black")

# whenever there is new version look at alpha and beta
# look if exist
# github action: check for new version of x
# (safer) start with issue or PR
# targeted dependabot - instead of all dependencies
# if github action doesnt exist


# tools repo target tool itself

# for python repo target pytest since want to test
