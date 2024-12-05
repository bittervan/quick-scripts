import subprocess
import sys
from pathlib import Path
from tqdm import tqdm  # 进度条库

def get_all_commits(repo_dir):
    """获取所有的 Git 提交哈希。"""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--all"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        commits = result.stdout.strip().split("\n")
        return commits
    except subprocess.CalledProcessError as e:
        print(f"Error getting commits: {e.stderr}")
        return []

def search_in_commit(repo_dir, commit, regex):
    """在指定的提交中使用 git grep 搜索正则表达式。"""
    try:
        result = subprocess.run(
            ["git", "grep", "-E", regex, commit],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,  # Allow no matches
        )
        if result.stdout.strip():
            return result.stdout.strip()
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error searching in commit {commit}: {e.stderr}")
        return None

def main():
    if len(sys.argv) != 3:
        print("Usage: python search_commits.py <repo_dir> <regex>")
        sys.exit(1)

    # 从命令行获取参数
    repo_dir = sys.argv[1]
    regex = sys.argv[2]

    # 检查目录是否存在并且是一个 Git 仓库
    repo_path = Path(repo_dir)
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        print(f"Error: {repo_dir} is not a valid Git repository.")
        sys.exit(1)

    print(f"Searching in repository: {repo_dir}")
    print(f"Regex: {regex}")

    print("Fetching all commits...")
    commits = get_all_commits(repo_dir)
    if not commits:
        print("No commits found. Exiting.")
        return

    print(f"Found {len(commits)} commits. Starting search...")
    for commit in tqdm(commits, desc="Searching commits", unit="commit"):
        result = search_in_commit(repo_dir, commit, regex)
        if result:
            print(f"\nCommit: {commit}")
            print(result)
            print("-" * 40)

if __name__ == "__main__":
    main()

