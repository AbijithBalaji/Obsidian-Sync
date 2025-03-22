# Ogresync

![Ogresync Logo](./logo.ico)

**Ogresync** is an open-source synchronization tool that automates syncing your Obsidian vault with GitHub using Git and SSH. Developed by **Ogrelix**, a proudly MSMI-registered startup in India, Ogresync brings seamless version control and backup to your personal knowledge base.

---

## Features

- **One-Time Setup Wizard**  
  Automatically detects your Obsidian installation, lets you select your vault folder, verifies Git installation, and sets up SSH (with key generation and clear manual instructions).

- **Automatic Synchronization**  
  Stashes local changes, pulls remote updates, launches Obsidian for editing, and then commits & pushes your changes automatically.

- **Conflict Resolution**  
  Intelligent conflict detection with user-friendly options: keep local changes, use remote changes, or merge manually.

- **Cross-Platform Support**  
  Designed to work on Windows, Linux (packaged as an AppImage), and macOS (packaged as an .app bundle).

- **Offline Operation**  
  Even if you're offline, Ogresync commits local changes and queues them for push when connectivity is restored.

- **Open Source & Community-Driven**  
  Contributions are welcome! Join our community to help shape the future of Ogresync.

---

## Installation

### Prerequisites

- **Git:** Ensure Git is installed and available in your system's PATH.  
  [Download Git](https://git-scm.com/)

- **SSH:** A valid SSH key is required for GitHub synchronization.  
  *Note:* On Linux, clipboard functionality (for copying your SSH key) may require installing `xclip` or `xsel`.

- **Obsidian:** Must be installed on your system. If Ogresync does not detect Obsidian automatically, you will be prompted to locate it manually.

### Running from Source

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/Ogrelix/Ogresync.git
   cd Ogresync
