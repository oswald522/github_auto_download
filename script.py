import requests
import yaml
import os
import zipfile
import tarfile
import shutil


def load_yaml(file_path):
    """加载 YAML 文件"""
    with open(file_path, 'r',encoding='utf-8') as file:
        return yaml.safe_load(file)

def save_yaml(data, file_path):
    """保存 YAML 文件"""
    with open(file_path, 'w',encoding='utf-8') as file:
        yaml.safe_dump(data, file)

def get_github_releases(owner, repo, token=None):
    """获取 GitHub Releases 信息"""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    headers = {'Authorization': f'token {token}'} if token else {}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def find_best_asset(releases, file_keywords):
    """根据关键词匹配最佳的 Release Asset"""
    for release in releases:
        for asset in release['assets']:
            for keyword in file_keywords:
                file_keyword, arch = keyword.split(':')  # 分割关键词和架构
                if all(k in asset['name'] for k in file_keyword.split(',')):
                    return asset, arch  # 返回匹配的 Asset 和对应的架构
    return None, None

def download_asset(asset, download_path):
    """下载 Release Asset"""
    url = asset['browser_download_url']
    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(download_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)

def extract_and_classify(download_path, extract_dir, arch):
    """解压文件并分类到 bins/$ARCH"""
    if download_path.endswith('.zip'):
        with zipfile.ZipFile(download_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    elif download_path.endswith(('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
        with tarfile.open(download_path, 'r:*') as tar_ref:
            tar_ref.extractall(extract_dir)

    # 将解压后的文件移动到 bins/$ARCH
    target_dir = os.path.join('bins', arch)
    os.makedirs(target_dir, exist_ok=True)

    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            src_path = os.path.join(root, file)
            dest_path = os.path.join(target_dir, file)
            shutil.move(src_path, dest_path)

def update_yaml_version(yaml_data, name, new_version):
    """更新 YAML 文件中的版本号"""
    for release in yaml_data['releases']:
        if release['name'] == name:
            release['version'] = new_version
            break

def main():
    yaml_file = 'config.yaml'
    yaml_data = load_yaml(yaml_file)

    token = yaml_data.get('github', {}).get('token')  # 可选：GitHub token

    for release_info in yaml_data['releases']:
        owner, repo = release_info['repo'].split('/')
        file_keywords = release_info['file_keywords']

        # 获取 GitHub Releases
        releases = get_github_releases(owner, repo, token)
        best_asset, arch = find_best_asset(releases, file_keywords)

        if best_asset:
            # 下载文件
            download_path = os.path.join('downloads', best_asset['name'])
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            download_asset(best_asset, download_path)
            print(f"Downloaded: {best_asset['name']}")

            # 解压并分类
            extract_dir = 'extracted'
            os.makedirs(extract_dir, exist_ok=True)
            extract_and_classify(download_path, extract_dir, arch)

            # 更新 YAML 文件中的版本号
            new_version = best_asset['name']  # 或者从文件名中提取版本号
            update_yaml_version(yaml_data, release_info['name'], new_version)
            save_yaml(yaml_data, yaml_file)

            # 清理临时文件
            os.remove(download_path)
            shutil.rmtree(extract_dir)
        else:
            print(f"No matching asset found for {release_info['name']}.")

if __name__ == "__main__":
    main()
