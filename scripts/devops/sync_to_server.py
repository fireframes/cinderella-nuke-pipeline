import os
import shutil
import subprocess
import json
import hashlib

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "../config/cinderella_config.json")
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

nuke_dev_path = config['projects']['cinderella']['tools']['dev']
nuke_prod_path = config['projects']['cinderella']['tools']['prod']
dev_tools_path = nuke_dev_path.replace("/", "\\")
prod_tools_path = nuke_prod_path.replace("/", "\\")

ignore_list = [".gitignore", "scripts/devops/sync_to_server.py", "scripts/devops/switch_nuke_mode.ps1", "README.md"]
extra_list = ["scripts/config/cinderella_config.json"]

def get_file_hash(filepath):
    """Calculate MD5 hash of a file to verify content equality."""
    if not os.path.exists(filepath):
        return None
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None

def get_recently_changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-status", "--find-renames", "HEAD^", "HEAD"],
        capture_output=True,
        text=True
    )
    changes = {}
    for line in result.stdout.splitlines():
        if line.strip():
            parts = line.split(None, 2)
            if len(parts) >= 2:
                status = parts[0]
                if status.startswith('R'):
                    old_file, new_file = parts[1], parts[2]
                    changes[old_file] = 'D'
                    changes[new_file] = 'A'
                else:
                    changes[parts[1]] = status
    return changes

def sync_recent_changes_to_prod(dev_dir, prod_dir):
    recent_changes = get_recently_changed_files()
    actions = []

    def queue_copy_if_different(src, dest, label='COPY'):
        if not os.path.exists(src):
            return
        # Skip if files are identical by content
        if get_file_hash(src) == get_file_hash(dest):
            return
        actions.append((label, src, dest))

    # 1. Evaluate Git changes
    for file, status in recent_changes.items():
        if file in ignore_list:
            continue
        
        dest_path = os.path.normpath(os.path.join(prod_dir, file))
        src_path = os.path.normpath(os.path.join(dev_dir, file))

        if status == 'D':
            if os.path.exists(dest_path):
                actions.append(('DELETE', dest_path, None))
        elif status in ['A', 'M']:
            queue_copy_if_different(src_path, dest_path)

    # 2. Evaluate Extra files
    for file in extra_list:
        src_path = os.path.normpath(os.path.join(dev_dir, file))
        dest_path = os.path.normpath(os.path.join(prod_dir, file))
        queue_copy_if_different(src_path, dest_path, label='COPY_EXTRA')

    if not actions:
        print("\nAll files are already synchronized (content-identical).")
        return

    # 3. User Review Phase
    print("\n" + "="*60)
    print(f"PROPOSED MIGRATION ACTIONS ({len(actions)} total)")
    print("="*60)
    for action_type, src, dest in actions:
        if action_type == 'DELETE':
            print(f"[-] REMOVE: {src}")
        else:
            print(f"[+] {action_type}: {os.path.basename(src)}")
            print(f"    FROM: {src}")
            print(f"    TO:   {dest}")
    print("="*60)

    confirm = input(f"\nProceed with migration? (y/n): ").lower()
    if confirm != 'y':
        print("Migration aborted.")
        return

    # 4. Execution Phase
    for action_type, src, dest in actions:
        try:
            if action_type == 'DELETE':
                os.remove(src)
                print(f"Done: Removed {os.path.basename(src)}")
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest) # copy2 preserves metadata/timestamps
                print(f"Done: Copied {os.path.basename(dest)}")
        except Exception as e:
            print(f"FAILED {action_type} for {src}: {e}")

if __name__ == "__main__":
    sync_recent_changes_to_prod(dev_tools_path, prod_tools_path)
