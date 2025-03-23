# Ogresync

![Ogresync Logo](./Ogresync.png)

**Ogresync** is an open-source synchronization tool that automates syncing your Obsidian vault with GitHub using Git and SSH. Developed by **Ogrelix**, a dynamic MSMI-registered startup, Ogresync helps you keep your personal knowledge base safe, versioned, and up-to-date—all with minimal manual intervention.

---

## Features

- **One-Time Setup Wizard**  
  Automatically detects your Obsidian installation, allows you to select your vault folder, and configures Git and SSH (including key generation and detailed manual instructions if needed).

- **Automatic Synchronization**  
  Stashes local changes, pulls remote updates (with conflict resolution if necessary), launches Obsidian for editing, and then commits and pushes your changes automatically.

- **Intelligent Conflict Resolution**  
  If a file is modified both locally and on GitHub, Ogresync detects conflicts and prompts you with user-friendly options to keep local changes, use remote changes, or merge manually.

- **Offline Operation**  
  Works gracefully when offline by committing local changes and queuing them for push when internet connectivity is restored.

- **Cross-Platform Support**  
  Built in Python, Ogresync runs on Windows, Linux (packaged as an AppImage), and macOS (packaged as a .app bundle).

- **Open Source & Community-Driven**  
  We welcome contributions! Ogresync is designed for collaboration and continuous improvement.

---

## Installation

### Prerequisites

- **Git:** Ensure Git is installed and available in your PATH.  
  [Download Git](https://git-scm.com/)

- **SSH:** A valid SSH key is required for GitHub synchronization. If not present, Ogresync can generate one for you.
  
- **Obsidian:** Install Obsidian from [obsidian.md](https://obsidian.md/).  
  *Linux users:* If using clipboard features, please install `xclip` or `xsel`.

### Running from Source

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/Ogrelix/Ogresync.git
   cd Ogresync

(Optional) Create a Virtual Environment:

bash
Copy
python3 -m venv venv
source venv/bin/activate
Install Dependencies:

bash
Copy
pip install -r requirements.txt
Run Ogresync:

bash
Copy
python ogresync.py
Packaged Executables
Download native packages from our Releases page:

Windows: .exe file

macOS: .app bundle

Linux: AppImage

Usage
Initial Setup:

The setup wizard guides you through detecting your Obsidian installation and selecting your vault folder.

Ogresync verifies Git and SSH configuration. If no SSH key exists, it can generate one (with instructions provided if automatic clipboard copying fails).

You will be prompted to link your GitHub repository (create a private repo if needed). This is mandatory for synchronization.

Automatic Synchronization:

On subsequent runs, Ogresync will:

Stash any local changes.

Pull the latest updates from GitHub before launching Obsidian (including handling any conflicts via a dialog if necessary).

Launch Obsidian for editing.

Wait until Obsidian is closed.

Commit any local changes.

Push unpushed commits to GitHub (or queue them if offline).

Conflict Resolution:

If a file is modified both locally and on GitHub (e.g., the same file is edited on another device), a merge conflict is detected.

A dialog box will appear, asking whether to:

Keep Local Changes (Ours)

Use Remote Changes (Theirs)

Merge Manually

Your choice determines how the conflict is resolved before synchronization continues.

Contributing
We welcome contributions from the community! To contribute:

Fork the repository.

Create a branch for your feature or bug fix.

Submit a pull request with your changes.

Please review our CONTRIBUTING.md for detailed guidelines.

Roadmap
Enhanced Conflict Resolution UI:
Improve the merge conflict dialog and integrate external merge tools.

Native Shortcuts & Installers:
Develop desktop/start menu shortcuts and native installers for all platforms.

Cross-Platform Packaging:
Further refine packaging for macOS (.app) and Linux (AppImage) to ensure a seamless user experience.

Additional Features:
Custom commit messages, scheduled syncs, and more.

License
Ogresync is licensed under the GNU General Public License v3.0 (GPLv3). See the LICENSE file for full details.

About Ogrelix
Ogrelix is a dynamic, innovative startup (MSMI registered) with a playful spirit. With two products already launched, we are committed to creating modern, user-friendly solutions that empower individuals in their digital workflows. Ogresync is one of our flagship products aimed at making your note-taking and knowledge management seamless and secure.

Contact
For questions, feedback, or support, please open an issue on GitHub or contact us at contact@ogrelix.com.

Join the Ogresync community and help us build a better, more connected way to manage your Obsidian vault!


---

### **Packaging Instructions:**

Since you plan to distribute native applications for Windows, Linux, and macOS, add this brief note to your README (under a "TODO" section or similar):

```markdown
### 🚧 Future Packaging Enhancements

- We are actively working on packaging Ogresync as native applications for:
  - **Windows:** A standalone `.exe` file.
  - **Linux:** An AppImage for easy distribution.
  - **macOS:** A proper `.app` bundle.
- For now, you can run Ogresync from source, and precompiled binaries will be available in future releases.
