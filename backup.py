import os
import subprocess
import sys
import threading
import time
import psutil
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import webbrowser
import pyperclip

# ------------------------------------------------
# CONFIG / GLOBALS
# ------------------------------------------------

CONFIG_FILE = "config.txt"  # Stores vault path, Obsidian path, setup_done flag, etc.
config_data = {
    "VAULT_PATH": "",
    "OBSIDIAN_PATH": "",
    "SETUP_DONE": "0"
}

SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa.pub")

root = None  # We will create this conditionally
log_text = None
progress_bar = None

# ------------------------------------------------
# CONFIG HANDLING
# ------------------------------------------------

def load_config():
    """
    Reads config.txt into config_data dict.
    Expected lines like: KEY=VALUE
    """
    if not os.path.exists(CONFIG_FILE):
        return
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                key, val = line.split("=", 1)
                config_data[key.strip()] = val.strip()

def save_config():
    """
    Writes config_data dict to config.txt.
    """
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        for k, v in config_data.items():
            f.write(f"{k}={v}\n")

# ------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------

def run_command(command, cwd=None, timeout=None):
    """
    Runs a shell command, returning (stdout, stderr, return_code).
    Safe to call in a background thread.
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired as e:
        return "", str(e), 1
    except Exception as e:
        return "", str(e), 1
    
def ensure_github_known_host():
    """
    Adds GitHub's RSA key to known_hosts if not already present.
    This prevents the 'Are you sure you want to continue connecting?' prompt.
    
    Best Practice Note:
      - We're automatically trusting 'github.com' here.
      - In a more security-conscious workflow, you'd verify the key's fingerprint
        against GitHub's official documentation before appending.
    """
    # Check if GitHub is already in known_hosts
    known_hosts_path = os.path.expanduser("~/.ssh/known_hosts")
    if os.path.exists(known_hosts_path):
        with open(known_hosts_path, "r", encoding="utf-8") as f:
            if "github.com" in f.read():
                # Already have GitHub host key, nothing to do
                return

    safe_update_log("Adding GitHub to known hosts (ssh-keyscan)...", 32)
    # Fetch GitHub's RSA key and append to known_hosts
    scan_out, scan_err, rc = run_command("ssh-keyscan -t rsa github.com")
    if rc == 0 and scan_out:
        # Ensure .ssh folder exists
        os.makedirs(os.path.expanduser("~/.ssh"), exist_ok=True)
        with open(known_hosts_path, "a", encoding="utf-8") as f:
            f.write(scan_out + "\n")
    else:
        # If this fails, we won't block the user; but we warn them.
        safe_update_log("Warning: Could not fetch GitHub host key automatically.", 32)


def is_obsidian_running():
    """
    Checks if Obsidian.exe is currently running.
    """
    for proc in psutil.process_iter(attrs=['name']):
        if proc.info['name'] and proc.info['name'].lower() == "obsidian.exe":
            return True
    return False

def safe_update_log(message, progress=None):
    if log_text and progress_bar and root.winfo_exists():
        def _update():
            log_text.config(state='normal')
            log_text.insert(tk.END, message + "\n")
            log_text.config(state='disabled')
            log_text.yview_moveto(1)
            if progress is not None:
                progress_bar["value"] = progress
        try:
            root.after(0, _update)
        except Exception as e:
            print("Error scheduling UI update:", e)
    else:
        print(message)

def is_network_available():
    """
    Checks if the network is available by trying to connect to github.com over HTTPS.
    Returns True if successful, otherwise False.
    """
    import socket
    try:
        socket.create_connection(("github.com", 443), timeout=5)
        return True
    except Exception:
        return False

def get_unpushed_commits(vault_path):
    """
    Fetches the latest from origin and returns a string listing commits in HEAD that are not in origin/main.
    """
    # Update remote tracking info first.
    run_command("git fetch origin", cwd=vault_path)
    unpushed, _, _ = run_command("git log origin/main..HEAD --oneline", cwd=vault_path)
    return unpushed.strip()

def conflict_resolution_dialog(conflict_files):
    """
    Opens a modal dialog that lists conflicting files and offers three options:
    "Keep Local Changes" (ours), "Keep Remote Changes" (theirs), or "Merge Manually".
    Returns the user's choice as one of the strings: "ours", "theirs", or "manual".
    """
    top = tk.Toplevel(root)
    top.title("Merge Conflict Detected")
    top.geometry("400x220")
    top.grab_set()  # Make modal

    label_text = ("Merge conflict detected in the following file(s):\n" +
                  conflict_files + "\n\n" +
                  "How would you like to resolve these conflicts?\n"
                  "• Keep Local Changes (your version)\n"
                  "• Keep Remote Changes (GitHub version)\n"
                  "• Merge Manually (open and resolve the conflict manually)")
    label = tk.Label(top, text=label_text, justify="left", wraplength=380)
    label.pack(pady=10, padx=10)

    resolution = {"choice": None}

    def set_choice(choice):
        resolution["choice"] = choice
        top.destroy()

    btn_frame = tk.Frame(top)
    btn_frame.pack(pady=10)
    btn_local = tk.Button(btn_frame, text="Keep Local", width=15, command=lambda: set_choice("ours"))
    btn_remote = tk.Button(btn_frame, text="Keep Remote", width=15, command=lambda: set_choice("theirs"))
    btn_manual = tk.Button(btn_frame, text="Merge Manually", width=15, command=lambda: set_choice("manual"))
    btn_local.grid(row=0, column=0, padx=5)
    btn_remote.grid(row=0, column=1, padx=5)
    btn_manual.grid(row=0, column=2, padx=5)

    top.wait_window()
    return resolution["choice"]

# ------------------------------------------------
# GITHUB SETUP FUNCTIONS
# ------------------------------------------------
def is_git_repo(folder_path):
    """
    Checks if a folder is already a Git repository.
    Returns True if the folder is a Git repo, otherwise False.
    """
    out, err, rc = run_command("git rev-parse --is-inside-work-tree", cwd=folder_path)
    return rc == 0

def initialize_git_repo(vault_path):
    """
    Initializes a Git repository in the selected vault folder if it's not already a repo.
    Also sets the branch to 'main'.
    """
    if not is_git_repo(vault_path):
        safe_update_log("Initializing Git repository in vault...", 15)
        out, err, rc = run_command("git init", cwd=vault_path)
        if rc == 0:
            run_command("git branch -M main", cwd=vault_path)
            safe_update_log("Git repository initialized successfully.", 20)
        else:
            safe_update_log("Error initializing Git repository: " + err, 20)
    else:
        safe_update_log("Vault is already a Git repository.", 20)

def set_github_remote(vault_path):
    """
    Prompts the user to link an existing GitHub repository,
    handling the case where 'origin' already exists.
    Returns True if successful or skipped gracefully, False if an error occurs.
    """

    # First, check if a remote named 'origin' is already set
    existing_remote_url, err, rc = run_command("git remote get-url origin", cwd=vault_path)
    if rc == 0:
        # 'origin' remote already exists
        safe_update_log(f"A remote named 'origin' already exists: {existing_remote_url}", 25)
        override = messagebox.askyesno(
            "Existing Remote",
            f"A remote 'origin' already points to:\n{existing_remote_url}\n\n"
            "Do you want to override it with a new URL?"
        )
        if not override:
            # User wants to keep the existing remote; just skip reconfiguration
            safe_update_log("Keeping the existing 'origin' remote. Skipping new remote configuration.", 25)
            return True
        else:
            # User wants to override the existing 'origin'
            out, err, rc = run_command("git remote remove origin", cwd=vault_path)
            if rc != 0:
                safe_update_log(f"Error removing existing remote: {err}", 25)
                return False
            safe_update_log("Existing 'origin' remote removed.", 25)

    # If we reach here, there's either no 'origin' or we've just removed it
    use_existing_repo = messagebox.askyesno(
        "GitHub Repository",
        "Do you want to link to an existing GitHub repository now?"
    )
    if use_existing_repo:
        repo_url = simpledialog.askstring(
            "GitHub Repository",
            "Enter your GitHub repository URL (e.g., git@github.com:username/repo.git):",
            parent=root
        )
        if repo_url:
            out, err, rc = run_command(f"git remote add origin {repo_url}", cwd=vault_path)
            if rc == 0:
                safe_update_log(f"Git remote 'origin' set to: {repo_url}", 25)
            else:
                safe_update_log(f"Error setting Git remote: {err}", 25)
                return False
        else:
            messagebox.showerror("Error", "Repository URL not provided. Please try again.")
            return False
    else:
        safe_update_log("Skipping GitHub remote setup. You can set this up later manually.", 25)

    return True

def ensure_placeholder_file(vault_path):
    """
    Creates a placeholder file (README.md) in the vault if it doesn't already exist.
    This ensures that there's at least one file to commit.
    """
    import os
    placeholder_path = os.path.join(vault_path, "README.md")
    if not os.path.exists(placeholder_path):
        with open(placeholder_path, "w", encoding="utf-8") as f:
            f.write("# Welcome to your Obsidian Vault\n\nThis placeholder file was generated automatically by Obsidian Sync to initialize the repository.")
        safe_update_log("Placeholder file 'README.md' created, as the vault was empty.", 5)
    else:
        safe_update_log("Placeholder file 'README.md' already exists.", 5)




# ------------------------------------------------
# WIZARD STEPS (Used Only if SETUP_DONE=0)
# ------------------------------------------------

def find_obsidian_path():
    """
    Attempts to locate Obsidian's installation path in common Windows locations.
    If not found, prompts user to locate manually.
    Returns path or None.
    """
    possible_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Obsidian\Obsidian.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Obsidian\Obsidian.exe")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path

    # Prompt user to select
    response = messagebox.askyesno("Obsidian Not Found",
                                   "Obsidian not detected in standard locations.\n"
                                   "Locate the Obsidian.exe manually?")
    if response:
        selected_path = filedialog.askopenfilename(
            title="Select Obsidian Executable",
            filetypes=[("Obsidian Executable", "*.exe")]
        )
        if selected_path:
            return selected_path
    return None

def select_vault_path():
    """
    Asks user to select Obsidian Vault folder. Returns path or None if canceled.
    """
    selected = filedialog.askdirectory(title="Select Obsidian Vault Folder")
    return selected if selected else None

def is_git_installed():
    """
    Returns True if Git is installed, else False.
    """
    out, err, rc = run_command("git --version")
    return rc == 0

def test_ssh_connection_sync():
    """
    Synchronously tests SSH to GitHub. Returns True if OK, False otherwise.
    """
    out, err, rc = run_command("ssh -T git@github.com")
    print("DEBUG: SSH OUT:", out)
    print("DEBUG: SSH ERR:", err)
    print("DEBUG: SSH RC:", rc)
    if "successfully authenticated" in (out + err).lower():
        return True
    return False

def re_test_ssh():
    """
    Re-tests the SSH connection in a background thread.
    If successful, automatically performs an initial commit/push if none exists yet.
    """
    def _test_thread():
        safe_update_log("Re-testing SSH connection to GitHub...", 35)
        ensure_github_known_host()  # ensures no prompt for 'yes/no'

        if test_ssh_connection_sync():
            safe_update_log("SSH connection successful!", 40)
            
            # Perform the initial commit/push if there are no local commits yet
            perform_initial_commit_and_push(config_data["VAULT_PATH"])

            # Mark setup as done
            config_data["SETUP_DONE"] = "1"
            save_config()

            safe_update_log("Setup complete! You can now close this window or start sync.", 100)
        else:
            safe_update_log("SSH connection still failed. Check your GitHub key or generate a new one.", 40)

    threading.Thread(target=_test_thread, daemon=True).start()


def perform_initial_commit_and_push(vault_path):
    """
    Checks if the local repository has any commits.
    If not, creates an initial commit and pushes it to the remote 'origin' on the 'main' branch.
    """
    out, err, rc = run_command("git rev-parse HEAD", cwd=vault_path)
    if rc != 0:
        # rc != 0 implies 'git rev-parse HEAD' failed => no commits (unborn branch)
        safe_update_log("No local commits detected. Creating initial commit...", 50)

        # Stage all files
        run_command("git add .", cwd=vault_path)

        # Commit
        out_commit, err_commit, rc_commit = run_command('git commit -m "Initial commit"', cwd=vault_path)
        if rc_commit == 0:
            # Push and set upstream
            out_push, err_push, rc_push = run_command("git push -u origin main", cwd=vault_path)
            if rc_push == 0:
                safe_update_log("Initial commit pushed to remote repository successfully.", 60)
            else:
                safe_update_log(f"Error pushing initial commit: {err_push}", 60)
        else:
            safe_update_log(f"Error committing files: {err_commit}", 60)
    else:
        # We already have at least one commit in this repo
        safe_update_log("Local repository already has commits. Skipping initial commit step.", 50)


# -- SSH Key Generation in Background

def generate_ssh_key():
    """
    Prompts for the user's email and starts a background thread for SSH key generation.
    """
    user_email = simpledialog.askstring(
        "SSH Key Generation",
        "Enter your email address for the SSH key:",
        parent=root
    )
    if not user_email:
        messagebox.showerror("Email Required", "No email address provided. SSH key generation canceled.")
        return

    threading.Thread(target=generate_ssh_key_async, args=(user_email,), daemon=True).start()


def generate_ssh_key_async(user_email):
    """
    Runs in a background thread to:
      1) Generate an SSH key if it doesn't already exist.
      2) Copy the public key to the clipboard.
      3) Show an info dialog on the main thread.
      4) After the user closes the dialog, open GitHub's SSH settings in the browser.
    """
    key_path_private = SSH_KEY_PATH.replace("id_rsa.pub", "id_rsa")

    # 1) Generate key if it doesn't exist
    if not os.path.exists(SSH_KEY_PATH):
        safe_update_log("Generating SSH key...", 25)
        out, err, rc = run_command(f'ssh-keygen -t rsa -b 4096 -C "{user_email}" -f "{key_path_private}" -N ""')
        if rc != 0:
            safe_update_log(f"SSH key generation failed: {err}", 25)
            return
        safe_update_log("SSH key generated successfully.", 30)
    else:
        safe_update_log("SSH key already exists. Overwriting is not performed here.", 30)

    # 2) Read public key and copy to clipboard
    try:
        with open(SSH_KEY_PATH, "r", encoding="utf-8") as key_file:
            public_key = key_file.read().strip()
            pyperclip.copy(public_key)
        safe_update_log("Public key copied to clipboard.", 35)
    except Exception as e:
        safe_update_log(f"Error reading SSH key: {e}", 35)
        return

    # 3 & 4) Show dialog, then open GitHub in the main thread
    def show_dialog_then_open_browser():
        # Show the info dialog first
        messagebox.showinfo(
            "SSH Key Generated",
            "Your SSH key has been generated (if needed) and copied to your clipboard.\n\n"
            "Click OK to open GitHub's SSH keys page in your browser.\n"
            "Then, paste the key and click 'Re-test SSH' to confirm connectivity."
        )
        # After the user closes the dialog, open the browser
        webbrowser.open("https://github.com/settings/keys")

    root.after(0, show_dialog_then_open_browser)


def copy_ssh_key():
    """
    Copies the SSH key to clipboard and opens GitHub SSH settings.
    """
    if os.path.exists(SSH_KEY_PATH):
        with open(SSH_KEY_PATH, "r", encoding="utf-8") as key_file:
            ssh_key = key_file.read().strip()
            pyperclip.copy(ssh_key)
        webbrowser.open("https://github.com/settings/keys")
        messagebox.showinfo("SSH Key Copied",
                            "Your SSH key has been copied to the clipboard.\n"
                            "Paste it into GitHub.")
    else:
        messagebox.showerror("Error", "No SSH key found. Generate one first.")

# ------------------------------------------------
# AUTO-SYNC (Used if SETUP_DONE=1)
# ------------------------------------------------

def auto_sync():
    """
    This function is executed if setup is complete.
    It performs the following steps:
      1. Ensures that the vault has at least one commit (creating an initial commit if necessary, 
         including generating a placeholder file if the vault is empty).
      2. Checks network connectivity.
         - If online, it verifies that the remote branch ('main') exists (pushing the initial commit if needed)
           and pulls the latest updates from GitHub (using rebase and prompting for conflict resolution if required).
         - If offline, it skips remote operations.
      3. Stashes any local changes before pulling.
      4. Reapplies stashed changes.
      5. Opens Obsidian for editing and waits until it is closed.
      6. Upon Obsidian closure, stages and commits any changes.
      7. If online, pushes any unpushed commits to GitHub.
      8. Displays a final synchronization completion message.
    """
    vault_path = config_data["VAULT_PATH"]
    obsidian_path = config_data["OBSIDIAN_PATH"]

    if not vault_path or not obsidian_path:
        safe_update_log("Vault path or Obsidian path not set. Please run setup again.", 0)
        return

    def sync_thread():
        # Step 1: Ensure a local commit exists
        out, err, rc = run_command("git rev-parse HEAD", cwd=vault_path)
        if rc != 0:
            safe_update_log("No existing commits found in your vault. Verifying if the vault is empty...", 5)
            ensure_placeholder_file(vault_path)
            safe_update_log("Creating an initial commit to initialize the repository...", 5)
            run_command("git add -A", cwd=vault_path)
            out_commit, err_commit, rc_commit = run_command('git commit -m "Initial commit (auto-sync)"', cwd=vault_path)
            if rc_commit == 0:
                safe_update_log("Initial commit created successfully.", 5)
            else:
                safe_update_log(f"❌ Error creating initial commit: {err_commit}", 5)
                return
        else:
            safe_update_log("Local repository already contains commits.", 5)

        # Step 2: Check network connectivity
        network_available = is_network_available()
        if not network_available:
            safe_update_log("No internet connection detected. Skipping remote sync operations and proceeding in offline mode.", 10)
        else:
            safe_update_log("Internet connection detected. Proceeding with remote synchronization.", 10)
            # Verify remote branch 'main'
            ls_out, ls_err, ls_rc = run_command("git ls-remote --heads origin main", cwd=vault_path)
            if not ls_out.strip():
                safe_update_log("Remote branch 'main' not found. Pushing initial commit to create the remote branch...", 10)
                out_push, err_push, rc_push = run_command("git push -u origin main", cwd=vault_path)
                if rc_push == 0:
                    safe_update_log("Initial commit has been successfully pushed to GitHub.", 15)
                else:
                    safe_update_log(f"❌ Error pushing initial commit: {err_push}", 15)
                    network_available = False
            else:
                safe_update_log("Remote branch 'main' found. Proceeding to pull updates from GitHub...", 10)

        # Step 3: Stash local changes
        safe_update_log("Stashing any local changes...", 15)
        run_command("git stash", cwd=vault_path)

        # Step 4: If online, pull the latest updates (with conflict resolution)
        if network_available:
            safe_update_log("Pulling the latest updates from GitHub...", 20)
            out, err, rc = run_command("git pull --rebase origin main", cwd=vault_path)
            if rc != 0:
                if "Could not resolve hostname" in err or "network" in err.lower():
                    safe_update_log("❌ Unable to pull updates due to a network error. Local changes remain safely stashed.", 30)
                elif "CONFLICT" in (out + err):
                    safe_update_log("❌ A merge conflict was detected during the pull operation.", 30)
                    # Retrieve the list of conflicting files
                    conflict_files, _, _ = run_command("git diff --name-only --diff-filter=U", cwd=vault_path)
                    if not conflict_files.strip():
                        conflict_files = "Unknown files"
                    # Prompt user for resolution choice
                    choice = conflict_resolution_dialog(conflict_files)
                    if choice == "ours":
                        safe_update_log("Resolving conflict by keeping local changes...", 30)
                        run_command("git checkout --ours .", cwd=vault_path)
                        run_command("git add -A", cwd=vault_path)
                        rc_rebase, err_rebase, _ = run_command("git rebase --continue", cwd=vault_path)
                        if rc_rebase != 0:
                            safe_update_log(f"Error continuing rebase: {err_rebase}", 30)
                            run_command("git rebase --abort", cwd=vault_path)
                            network_available = False
                    elif choice == "theirs":
                        safe_update_log("Resolving conflict by using remote changes...", 30)
                        run_command("git checkout --theirs .", cwd=vault_path)
                        run_command("git add -A", cwd=vault_path)
                        rc_rebase, err_rebase, _ = run_command("git rebase --continue", cwd=vault_path)
                        if rc_rebase != 0:
                            safe_update_log(f"Error continuing rebase: {err_rebase}", 30)
                            run_command("git rebase --abort", cwd=vault_path)
                            network_available = False
                    elif choice == "abort":
                        safe_update_log("Aborting rebase as per user choice.", 30)
                        run_command("git rebase --abort", cwd=vault_path)
                        network_available = False
                    else:
                        safe_update_log("No valid conflict resolution chosen. Aborting rebase.", 30)
                        run_command("git rebase --abort", cwd=vault_path)
                        network_available = False
                else:
                    safe_update_log(f"❌ Pull operation failed: {err}", 30)
                run_command("git stash pop", cwd=vault_path)
                network_available = False
            else:
                safe_update_log("Pull operation completed successfully. Your vault is updated with the latest changes from GitHub.", 30)
                if out.strip():
                    for line in out.splitlines():
                        safe_update_log(f"✓ {line}", None)
        else:
            safe_update_log("Skipping pull operation due to offline mode.", 20)

        # Step 5: Reapply stashed changes
        out, err, rc = run_command("git stash pop", cwd=vault_path)
        if rc != 0 and "No stash" not in err:
            if "CONFLICT" in (out + err):
                safe_update_log("❌ A merge conflict occurred while reapplying stashed changes. Please resolve manually.", 35)
                return
            else:
                safe_update_log(f"Stash pop operation failed: {err}", 35)
                return
        safe_update_log("Successfully reapplied stashed local changes.", 35)

        # Step 6: Open Obsidian for editing
        safe_update_log("Launching Obsidian. Please edit your vault and close Obsidian when finished.", 40)
        try:
            subprocess.Popen([obsidian_path], shell=True)
        except Exception as e:
            safe_update_log(f"Error launching Obsidian: {e}", 40)
            return
        safe_update_log("Waiting for Obsidian to close...", 45)
        while is_obsidian_running():
            time.sleep(0.5)

        # Step 7: Pull any new changes from GitHub after Obsidian closes
        safe_update_log("Obsidian has been closed. Checking for new remote changes before committing...", 50)

        # Re-check network connectivity before pulling
        network_available = is_network_available()
        if network_available:
            safe_update_log("Pulling any new updates from GitHub before committing...", 50)
            out, err, rc = run_command("git pull --rebase origin main", cwd=vault_path)
            if rc != 0:
                if "Could not resolve hostname" in err or "network" in err.lower():
                    safe_update_log("❌ Unable to pull updates due to network error. Continuing with local commit.", 50)
                elif "CONFLICT" in (out + err):  # Detect merge conflicts
                    safe_update_log("❌ Merge conflict detected in new remote changes.", 50)
                    # Retrieve the list of conflicting files
                    conflict_files, _, _ = run_command("git diff --name-only --diff-filter=U", cwd=vault_path)
                    if not conflict_files.strip():
                        conflict_files = "Unknown files"
                    # Prompt user for conflict resolution
                    choice = conflict_resolution_dialog(conflict_files)
                    if choice == "ours":
                        safe_update_log("Resolving conflict by keeping local changes...", 50)
                        run_command("git checkout --ours .", cwd=vault_path)
                        run_command("git add -A", cwd=vault_path)
                        rc_rebase, err_rebase, _ = run_command("git rebase --continue", cwd=vault_path)
                        if rc_rebase != 0:
                            safe_update_log(f"Error continuing rebase: {err_rebase}", 50)
                            run_command("git rebase --abort", cwd=vault_path)
                    elif choice == "theirs":
                        safe_update_log("Resolving conflict by using remote changes...", 50)
                        run_command("git checkout --theirs .", cwd=vault_path)
                        run_command("git add -A", cwd=vault_path)
                        rc_rebase, err_rebase, _ = run_command("git rebase --continue", cwd=vault_path)
                        if rc_rebase != 0:
                            safe_update_log(f"Error continuing rebase: {err_rebase}", 50)
                            run_command("git rebase --abort", cwd=vault_path)
                    elif choice == "manual":
                        safe_update_log("Please resolve the conflicts manually. After resolving, click OK to continue.", 50)
                        messagebox.showinfo("Manual Merge", "Please resolve the conflicts in the affected files manually and then click OK.")
                        run_command("git add -A", cwd=vault_path)
                        rc_rebase, err_rebase, _ = run_command("git rebase --continue", cwd=vault_path)
                        if rc_rebase != 0:
                            safe_update_log(f"Error continuing rebase after manual merge: {err_rebase}", 50)
                            run_command("git rebase --abort", cwd=vault_path)
                    else:
                        safe_update_log("No valid conflict resolution chosen. Aborting rebase.", 50)
                        run_command("git rebase --abort", cwd=vault_path)
                else:
                    safe_update_log("New remote updates have been successfully pulled.", 50)
                    # Log pulled files
                    for line in out.splitlines():
                        safe_update_log(f"✓ Pulled: {line}", 50)
        else:
            safe_update_log("No network detected. Skipping remote check and proceeding with local commit.", 50)

        # Step 8: Commit changes after Obsidian closes
        safe_update_log("Obsidian has been closed. Committing any local changes...", 50)
        run_command("git add -A", cwd=vault_path)
        out, err, rc = run_command('git commit -m "Auto sync commit"', cwd=vault_path)
        committed = True
        if rc != 0 and "nothing to commit" in (out + err).lower():
            safe_update_log("No changes detected during this session. Nothing to commit.", 55)
            committed = False
        elif rc != 0:
            safe_update_log(f"❌ Commit operation failed: {err}", 55)
            return
        else:
            safe_update_log("Local changes have been committed successfully.", 55)
            commit_details, err_details, rc_details = run_command("git diff-tree --no-commit-id --name-status -r HEAD", cwd=vault_path)
            if rc_details == 0 and commit_details.strip():
                for line in commit_details.splitlines():
                    safe_update_log(f"✓ {line}", None)

        # Step 9: Push changes if network is available
        network_available = is_network_available()
        if network_available:
            unpushed = get_unpushed_commits(vault_path)
            if unpushed:
                safe_update_log("Pushing all unpushed commits to GitHub...", 60)
                out, err, rc = run_command("git push origin main", cwd=vault_path)
                if rc != 0:
                    if "Could not resolve hostname" in err or "network" in err.lower():
                        safe_update_log("❌ Unable to push changes due to network issues. Your changes remain locally committed and will be pushed once connectivity is restored.", 70)
                    else:
                        safe_update_log(f"❌ Push operation failed: {err}", 70)
                    return
                safe_update_log("✅ All changes have been successfully pushed to GitHub.", 70)
            else:
                safe_update_log("No new commits to push.", 70)
        else:
            safe_update_log("Offline mode: Changes have been committed locally. They will be automatically pushed when an internet connection is available.", 70)

        # Step 9: Final message
        safe_update_log("Synchronization complete. You may now close this window.", 100)

    threading.Thread(target=sync_thread, daemon=True).start()


# ------------------------------------------------
# ONE-TIME SETUP WORKFLOW
# ------------------------------------------------

def run_setup_wizard():
    """
    Runs the wizard in the main thread:
      1) Ask/find Obsidian.
      2) Ask for Vault.
      3) Check Git installation.
      4) Initialize Git repository and set GitHub remote.
      5) Check/Generate SSH key and Test SSH.
      6) If everything OK, mark SETUP_DONE=1.
    """
    safe_update_log("Running first-time setup...", 0)

    # 1) Find Obsidian
    obsidian_path = find_obsidian_path()
    if not obsidian_path:
        messagebox.showerror("Setup Aborted", "Obsidian not found. Exiting.")
        return
    config_data["OBSIDIAN_PATH"] = obsidian_path
    safe_update_log(f"Obsidian found: {obsidian_path}", 5)

    # 2) Vault path selection
    load_config()  # Load any existing configuration
    if not config_data["VAULT_PATH"]:
        vault = select_vault_path()
        if not vault:
            messagebox.showerror("Setup Aborted", "No vault folder selected. Exiting.")
            return
        config_data["VAULT_PATH"] = vault
    safe_update_log(f"Vault path set: {config_data['VAULT_PATH']}", 10)

    # 3) Check Git installation
    safe_update_log("Checking Git installation...", 15)
    if not is_git_installed():
        messagebox.showerror("Setup Aborted", "Git is not installed. Please install Git and re-run.")
        return
    safe_update_log("Git is installed.", 20)

    # 4) Initialize Git repository in vault if needed
    initialize_git_repo(config_data["VAULT_PATH"])

    # 5) Set up GitHub remote (link an existing repository)
    if not set_github_remote(config_data["VAULT_PATH"]):
        return

    # 6) SSH Key Check/Generation
    safe_update_log("Checking SSH key...", 25)
    if not os.path.exists(SSH_KEY_PATH):
        resp = messagebox.askyesno("SSH Key Missing",
                                   "No SSH key found.\nDo you want to generate one now?")
        if resp:
            generate_ssh_key()  # Runs in a background thread
            safe_update_log("Please add the generated key to GitHub, then click 'Re-test SSH'.", 30)
        else:
            messagebox.showwarning("SSH Key Required", 
                                   "You must generate or provide an SSH key for GitHub sync.")
    else:
        safe_update_log("SSH key found. Make sure it's added to GitHub if you haven't already.", 30)

    # 7) Test SSH connection
    re_test_ssh()

   
# ------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------

def main():
    load_config()

    # If setup is done, run auto-sync in a minimal/no-UI approach
    # But if you still want a log window, we can create a small UI. 
    # We'll do this: if SETUP_DONE=0, show the wizard UI. If =1, show a minimal UI with auto-sync logs.
    if config_data["SETUP_DONE"] == "1":
        # Already set up: run auto-sync with a minimal window or even no window.
        # If you truly want NO window at all, you can remove the UI entirely.
        # But let's provide a small log window for user feedback.
        create_minimal_ui(auto_run=True)
        auto_sync()
    else:
        # Not set up yet: run the wizard UI
        create_wizard_ui()
        run_setup_wizard()

    root.mainloop()

def create_minimal_ui(auto_run=False):
    global root, log_text, progress_bar
    root = tk.Tk()
    root.title("Obsidian Sync" if auto_run else "Obsidian Setup")
    root.geometry("500x300")
    root.configure(bg="#1e1e1e")

    # Create a log area and make it read-only
    log_text = scrolledtext.ScrolledText(root, height=10, width=58, bg="#282828", fg="white")
    log_text.pack(pady=5)
    log_text.config(state='disabled')  # Make it read-only

    progress_bar = ttk.Progressbar(root, orient="horizontal", length=450, mode="determinate")
    progress_bar.pack(pady=5)


    # If you truly want to hide it, do: root.withdraw()

def create_wizard_ui():
    """
    Creates a larger UI with wizard-related buttons.
    """
    global root, log_text, progress_bar
    root = tk.Tk()
    root.title("Obsidian Sync Setup")
    root.geometry("550x400")
    root.configure(bg="#1e1e1e")

    info_label = tk.Label(root, text="Obsidian First-Time Setup", font=("Arial", 14), bg="#1e1e1e", fg="white")
    info_label.pack(pady=5)

    log_text = scrolledtext.ScrolledText(root, height=10, width=60, bg="#282828", fg="white")
    log_text.pack(pady=5)

    progress_bar = ttk.Progressbar(root, orient="horizontal", length=500, mode="determinate")
    progress_bar.pack(pady=5)

    # Optional buttons for SSH key generation or copy
    btn_frame = tk.Frame(root, bg="#1e1e1e")
    btn_frame.pack(pady=5)

    gen_btn = tk.Button(btn_frame, text="Generate SSH Key", command=generate_ssh_key, bg="#663399", fg="white")
    gen_btn.grid(row=0, column=0, padx=5)

    copy_btn = tk.Button(btn_frame, text="Copy SSH Key", command=copy_ssh_key, bg="#0066cc", fg="white")
    copy_btn.grid(row=0, column=1, padx=5)

    exit_btn = tk.Button(root, text="Exit", command=root.destroy, bg="#ff4444", fg="white", width=12)
    exit_btn.pack(pady=5)

    test_ssh_again_btn = tk.Button(
        root, text="Re-test SSH", command=re_test_ssh, 
        bg="#00cc66", fg="white"
    )
    test_ssh_again_btn.pack()

    
# ------------------------------------------------
# EXECUTION
# ------------------------------------------------

if __name__ == "__main__":
    main()