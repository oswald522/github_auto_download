import os
import requests
import yaml
import zipfile
import tarfile
from pathlib import Path
from webdav3.client import Client

# WEBDAV3 options
options = {
    'webdav_hostname': os.getenv('WEBDAV_URL'),
    'webdav_login': os.getenv('WEBDAV_USERNAME'),
    'webdav_password': os.getenv('WEBDAV_PASSWORD'),
    'disable_check': True
}

# GitHub API URL template for fetching release information
GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"

# Cache directory to store downloaded files and version info
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def load_yaml(file_path):
    """Load the YAML configuration file."""
    with open(file_path, "r", encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_latest_releases(config):
    """获取所有仓库的最新版本信息"""
    latest_releases = {}
    for release in config.get("releases", []):
        repo = release["repo"]
        url = GITHUB_API_URL.format(repo=repo)
        response = requests.get(url)
        if response.status_code == 200:
            latest_releases[repo] = response.json()
        else:
            print(f"Failed to fetch release info for {repo}: {response.status_code}")
            latest_releases[repo] = None
    return latest_releases

def check_and_update_versions(config, latest_releases, config_path="config.yaml", update=False) -> bool:
    """
    检查并可选地更新配置文件中的版本信息
    参数:
        config: 配置信息
        latest_releases: 最新版本信息
        config_path: 配置文件路径
        update: 是否更新配置文件
    返回:
        bool: 是否有版本更新
    """
    has_updates = False
    
    for release in config.get("releases", []):
        repo = release["repo"]
        latest_release = latest_releases[repo]
        if not latest_release:
            continue
            
        current_version = release.get("version")
        latest_version = latest_release["tag_name"]
        
        if latest_version != current_version:
            print(f"New version available for {release['name']}: {current_version} -> {latest_version}")
            has_updates = True
            
            if update:
                release["version"] = latest_version
                print(f"Updated {release['name']} version in config")
    
    # 如果需要更新且有更新内容，则写入配置文件
    if update and has_updates:
        with open(config_path, "w", encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        print("Config file updated successfully")
    elif update and not has_updates:
        print("All versions are up to date")
    
    return has_updates

def find_best_match(assets, keywords):
    """Find the best matching asset based on the keywords."""
    best_match = None
    best_score = 0

    for asset in assets:
        score = sum(1 for keyword in keywords if keyword in asset["name"].lower())
        if score > best_score:
            best_match = asset
            best_score = score

    return best_match

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

def process_releases(config, latest_releases):
    """Process each release in the YAML configuration."""
    for release in config.get("releases", []):
        name = release["name"]
        repo = release["repo"]
        file_list = release.get("file_list", [])
        
        latest_release = latest_releases[repo]
        if not latest_release:
            continue

        for file_entry in file_list:
            file_keywords, save_path_suffix = file_entry.split(":")
            keywords = [k.lower() for k in file_keywords.split(",")]
            save_path = Path('bin/'+save_path_suffix)

            assets = latest_release.get("assets", [])
            best_match = find_best_match(assets, keywords)

            if best_match:
                temp_file = CACHE_DIR / best_match["name"]
                download_file(best_match["browser_download_url"], temp_file)
                extract_file(temp_file, save_path)
                temp_file.unlink()
            else:
                print(f"No matching file found for keywords '{file_keywords}' in release assets for {name}.")

def upload_directory(client, local_path="bin", remote_base_path="Github_Software"):
    """上传本地目录到WebDAV服务器"""
    for file_path in Path(local_path).rglob('*'):
        if not file_path.is_file():
            continue
            
        remote_path = f"{remote_base_path}/{file_path.relative_to(local_path)}"
        
        try:
            client.mkdir(str(Path(remote_path).parent))
            client.upload_sync(remote_path=remote_path, local_path=str(file_path))
            print(f"Uploaded: {file_path.relative_to(local_path)}")
        except Exception as e:
            print(f"Upload failed for {file_path.name}: {e}")

def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='GitHub Release Downloader')
    parser.add_argument('--update-config', action='store_true', 
                      help='Update versions in config.yaml')
    parser.add_argument('--download', action='store_true',
                      help='Download and process releases')
    parser.add_argument('--upload', action='store_true',
                      help='Upload to WebDAV')
    parser.add_argument('--all', action='store_true',
                      help='Execute all operations')
    parser.add_argument('--force', action='store_true',
                      help='Force execution even if no updates')
    args = parser.parse_args()

    if not any([args.update_config, args.download, args.upload, args.all]):
        args.all = True

    try:
        # 加载配置并获取所有最新版本信息
        config = load_yaml("config.yaml")
        latest_releases = get_latest_releases(config)
        
        # 检查版本更新(同时根据参数决定是否更新配置文件)
        has_updates = check_and_update_versions(
            config, 
            latest_releases, 
            update=(args.update_config or args.all)
        )

        # 如果没有更新且不强制执行，直接退出
        if not has_updates and not args.force:
            print("No new versions available. Use --force to execute anyway.")
            return

        # 下载处理
        if args.download or args.all:
            print("Processing downloads...")
            process_releases(config, latest_releases)

        # 上传处理
        if args.upload or args.all:
            print("Starting upload...")
            if all(key in os.environ for key in ['WEBDAV_URL', 'WEBDAV_USERNAME', 'WEBDAV_PASSWORD']):
                client = Client(options)
                upload_directory(client)
            else:
                print("Error: WebDAV credentials not found in environment variables")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()
