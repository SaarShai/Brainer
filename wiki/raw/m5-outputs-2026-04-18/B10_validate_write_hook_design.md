---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round5]
---

```python
import sys
import os

def is_protected_path(file_path):
    """
    Determines if a given file path is protected from modification.
    Protected paths include:
    - Raw data directories (e.g., 'raw/')
    - Git LFS lockfiles (e.g., '.git/lfs/locks/*')
    - System dotfiles (e.g., ~/.bashrc, ~/.ssh/config)
    """
    # Normalize the path to handle relative paths and symlinks
    normalized_path = os.path.realpath(file_path)

    # Check for raw data directory
    if 'raw/' in normalized_path:
        return True

    # Check for Git LFS lockfiles
    if normalized_path.startswith(os.path.expanduser('~/.git/lfs/locks/')):
        return True

    # Check for system dotfiles
    system_dotfiles = [
        os.path.expanduser('~/.bashrc'),
        os.path.expanduser('~/.ssh/config'),
        os.path.expanduser('~/.gitconfig'),
        os.path.expanduser('~/.tmux.conf'),
        os.path.expanduser('~/.vimrc')
    ]
    if normalized_path in system_dotfiles:
        return True

    return False

def main():
    """
    Main function that reads file paths from stdin and checks for protected writes.
    Exits with status code 1 if any protected path is detected.
    """
    # Read all lines from stdin
    file_paths = [line.strip() for line in sys.stdin]

    # Check each file path
    for file_path in file_paths:
        if is_protected_path(file_path):
            print("Error: Attempting to modify protected file or directory.")
            print("Protected paths include raw data, Git LFS lockfiles, and system dotfiles.")
            print("Please use the appropriate workflow for modifying these files.")
            sys.exit(1)

    # If no protected paths are detected
    sys.exit(0)

if __name__ == "__main__":
    main()
```

Exit Code Contract:
- 0: No protected paths modified
- 1: Protected path modification attempted
- 2: Invalid input or arguments

User Feedback Format:
- Error messages printed to stdout in plain text
- Messages explain the nature of the protection and suggest alternative workflows
- Messages are concise but informative
