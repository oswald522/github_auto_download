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
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def get_latest_release(repo):
    """Fetch the latest release information from GitHub."""
    url = GITHUB_API_URL.format(repo=repo)
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch release info for {repo}: {response.status_code}")
        return None

def is_version_updated(name, latest_version):
    """Check if the version is updated compared to the cached version."""
    version_file = CACHE_DIR / f"{name}_version.txt"
    if version_file.exists():
        with open(version_file, "r") as f:
            cached_version = f.read().strip()
        if cached_version == latest_version:
            return False  # No update
    # Update the cached version
    with open(version_file, "w") as f:
        f.write(latest_version)
    return True

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

def process_releases(config):
    """Process each release in the YAML configuration."""
    for release in config.get("releases", []):
        name = release["name"]
        repo = release["repo"]
        file_list = release.get("file_list", [])
        
        # 直接获取最新发布信息
        latest_release = get_latest_release(repo)
        if not latest_release:
            continue

        # 下载文件列表中的文件
        for file_entry in file_list:
            file_keywords, save_path_suffix = file_entry.split(":")
            keywords = file_keywords.split(",")  # Split keywords by ","
            save_path = Path('bin/'+save_path_suffix)

            # 查找最匹配的资源
            assets = latest_release.get("assets", [])
            best_match = find_best_match(assets, keywords)

            if best_match:
                # 下载文件
                temp_file = CACHE_DIR / best_match["name"]
                download_file(best_match["browser_download_url"], temp_file)

                # 解压文件（如果是压缩文件）
                extract_file(temp_file, save_path)

                # 清理临时文件
                temp_file.unlink()
            else:
                print(f"No matching file found for keywords '{file_keywords}' in release assets for {name}.")

def update_config_versions(config_path: str = "config.yaml"):
    """更新配置文件中的版本信息"""
    # 读取当前配置
    with open(config_path, "r", encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    updated = False
    
    # 更新每个发布项的版本
    for release in config.get("releases", []):
        name = release["name"]
        repo = release["repo"]
        
        # 获取最新版本信息
        latest_release = get_latest_release(repo)
        if latest_release:
            latest_version = latest_release["tag_name"]
            current_version = release.get("version")
            
            # 如果版本不同，更新配置
            if current_version != latest_version:
                release["version"] = latest_version
                print(f"Updating {name} version: {current_version} -> {latest_version}")
                updated = True
    
    # 如果有更新，写回文件
    if updated:
        with open(config_path, "w", encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        print("Config file updated successfully")
    else:
        print("All versions are up to date")
    
    return config

def upload_directory(client, local_path: str = "bin", remote_base_path: str = "Github_Software"):
    """上传本地目录到WebDAV服务器"""
    for file_path in Path(local_path).rglob('*'):
        if not file_path.is_file():
            continue
            
        # 构建远程路径
        remote_path = f"{remote_base_path}/{file_path.relative_to(local_path)}"
        
        try:
            # 确保远程目录存在并上传文件
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
    args = parser.parse_args()

    # 如果没有指定任何参数，默认执行所有操作
    if not any([args.update_config, args.download, args.upload, args.all]):
        args.all = True

    try:
        # 首先加载配置
        config = None
        
        # 更新配置或加载现有配置
        if args.update_config or args.all:
            print("Updating config...")
            config = update_config_versions()
        
        if config is None:
            print("Loading existing config...")
            config = load_yaml("config.yaml")

        # 下载处理
        if args.download or args.all:
            print("Processing downloads...")
            process_releases(config)

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