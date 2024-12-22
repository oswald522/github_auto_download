import requests
import yaml
import zipfile
import tarfile
from pathlib import Path

# GitHub API URL template for fetching release information
GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"

# Cache directory to store downloaded files and version info
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def load_yaml(file_path):
    """Load the YAML configuration file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def save_yaml(data, file_path):
    """Save the updated YAML configuration back to the file."""
    with open(file_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def get_latest_release(repo):
    """Fetch the latest release information from GitHub."""
    url = GITHUB_API_URL.format(repo=repo)
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch release info for {repo}: {response.status_code}")
        return None

def download_file(url, save_path):
    """Download a file from a URL and save it to the specified path."""
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
        print(f"Downloaded: {save_path}")
    else:
        print(f"Failed to download {url}: {response.status_code}")

def extract_file(file_path, extract_to):
    """Extract a compressed file to the specified directory."""
    try:
        if file_path.suffix == ".zip":
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                zip_ref.extractall(extract_to)
                print(f"Extracted {file_path} to {extract_to}")
        elif file_path.suffix in [".tar", ".gz", ".bz2", ".xz"]:
            with tarfile.open(file_path, "r:*") as tar_ref:
                tar_ref.extractall(extract_to)
                print(f"Extracted {file_path} to {extract_to}")
        else:
            print(f"File {file_path} is not a recognized archive format. Skipping extraction.")
    except Exception as e:
        print(f"Failed to extract {file_path}: {e}")

def find_best_match(assets, keywords):
    """
    Find the best matching asset based on the keywords.
    The more keywords a file matches, the higher its score.
    """
    best_match = None
    best_score = 0

    for asset in assets:
        score = sum(1 for keyword in keywords if keyword in asset["name"])
        if score > best_score:
            best_match = asset
            best_score = score

    return best_match

def process_releases(config, config_path):
    """Process each release in the YAML configuration."""
    updated = False  # Track if the YAML file needs to be updated

    for release in config.get("releases", []):
        name = release["name"]
        repo = release["repo"]
        version = release.get("version", "")
        file_list = release.get("file_list", [])

        # Fetch the latest release info
        latest_release = get_latest_release(repo)
        if not latest_release:
            continue

        latest_version = latest_release["tag_name"]
        if version and latest_version == version:
            print(f"{name} is up-to-date. Skipping download.")
            continue

        print(f"Updating {name} from version {version} to {latest_version}.")

        # Update the version in the YAML configuration
        release["version"] = latest_version
        updated = True

        # Download files based on file_list
        for file_entry in file_list:
            file_keywords, save_path_suffix = file_entry.split(":")
            keywords = file_keywords.split(",")  # Split keywords by ","
            save_path = Path('bins/'+save_path_suffix)

            # Find the best matching asset
            assets = latest_release.get("assets", [])
            best_match = find_best_match(assets, keywords)

            if best_match:
                # Download the file
                temp_file = CACHE_DIR / best_match["name"]
                download_file(best_match["browser_download_url"], temp_file)

                # Extract the file if it's a compressed file
                extract_file(temp_file, save_path)

                # Clean up the temporary file
                temp_file.unlink()
            else:
                print(f"No matching file found for keywords '{file_keywords}' in release assets for {name}.")

    # Save the updated YAML configuration if changes were made
    if updated:
        save_yaml(config, config_path)
        print(f"Updated YAML configuration saved to {config_path}.")

if __name__ == "__main__":
    # Load the YAML configuration
    config_path = "config.yaml"
    config = load_yaml(config_path)

    # Process the releases
    process_releases(config, config_path)
