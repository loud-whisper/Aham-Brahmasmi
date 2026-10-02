# Before you start

You need a supported computer, Python, and an assistant that can open local files
and run commands. Git, a memory service, skills and a subscription to a particular
assistant are optional. Use an assistant you already have if it provides those tools.

## Supported systems

| System | What to do |
| --- | --- |
| Linux | Check the installed Python version. Most distributions include Python; otherwise use your distribution's supported package manager after approving installation. |
| macOS | Check Python first. If needed, use Python's official macOS installer and follow its installer windows and certificate step. |
| Native Windows | Use an installed Python 3.14 runtime and a local NTFS folder. The native core lifecycle, access checks and concurrency have passed hosted Windows CI. WSL and network shares have no separate verification claim. |

The Linux/macOS tested Python range is 3.10–3.14; native Windows CI uses 3.14. In your terminal, use the interpreter your
assistant found and run:

```text
PYTHON --version
```

`PYTHON` is a placeholder, not a command to paste literally. An assistant can
identify the actual interpreter and explain how to open your terminal. On supported
systems, it then runs `PYTHON aham.py check` from the framework folder. Without a
chosen workspace, this reports prerequisites and a folder suggestion; it does not
claim that your Brain is ready. `check --workspace WORKSPACE` checks your selection.

Official installation guidance: [Python on Linux/Unix](https://docs.python.org/3/using/unix.html),
[Python on macOS](https://docs.python.org/3.14/using/mac.html),
and [Python on Windows](https://docs.python.org/3.14/using/windows.html).
On Windows, `py list` lists runtimes managed by the current Python Install Manager;
`py -V:3.14` selects an installed 3.14 runtime. Older launcher behavior differs.
If no runtime is installed, a launch command can trigger installation: confirm an
installed runtime or obtain owner approval before proceeding. Prefer its exact
interpreter path for subsequent Aham commands. PowerShell uses `&` before a quoted
executable path; the recovery command printer supplies PowerShell quoting.
macOS's Apple-controlled Python must not be replaced or deleted. Use a separately
installed supported interpreter. The official installer documents its certificate
step and administrator prompt. Check the interpreter again after installation.

## When the assistant hands control to you

The assistant pauses and explains the exact next step when:

- An installer or tool displays a permission window: you read it and decide whether
  to approve; the assistant must not claim it clicked a window it cannot control.
- Installation needs administrator rights: approve that installation before the
  assistant runs an elevated command. Never enter your password into chat.
- Python was just installed: reopen the terminal or assistant as needed, then
  rerun the version check. Installation completion does not prove the old terminal
  has the new interpreter.
- Your assistant asks for file/command permission: allow the intended framework,
  project and private workspace if you want it to operate them, then verify actual
  access. Permission labels differ between tools.

If a prerequisite check fails, stop and keep the exact command and output. Follow
`docs/TROUBLESHOOTING.md`. Do not edit framework code or simulate successful setup.

## Choose a local private folder

Keep the active Brain outside this framework and outside cloud-synced folders.
`aham.py check` suggests a local folder under your user directory; it creates
nothing until you choose a location and run setup. Avoid Desktop and Documents
when they are redirected to sync. The default macOS suggestion uses Application
Support; the Linux suggestion uses a hidden Aham folder under your user directory.

Doctor checks common path roots: Dropbox's usual user folder, macOS CloudStorage
and Mobile Documents, and Desktop/Documents. Windows checks also treat
OneDrive-named folders and environment values as location hints. A path warning
does not prove a sync service is enabled. Renamed/custom sync folders can be missed;
check your sync app's settings before choosing a folder. Do not disable your sync
app just to satisfy a check.

Sources checked 2026-10-01: [Dropbox folder discovery](https://help.dropbox.com/installs/locate-dropbox-folder),
[Dropbox File Provider location](https://help.dropbox.com/installs/fix-domain-conflict-on-mac),
[OneDrive on macOS](https://support.microsoft.com/en-us/onedrive/why-do-i-have-two-versions-of-onedrive-on-my-mac),
[OneDrive default-folder policy](https://learn.microsoft.com/en-us/sharepoint/use-group-policy),
[Apple's archived iCloud container-path documentation](https://developer.apple.com/library/archive/documentation/General/Conceptual/iCloudDesignGuide/Chapters/TestingandDebuggingforiCloud.html),
and [Apple Desktop/Documents sync](https://support.apple.com/en-us/109344).
Environment values are advisory hints, not an authenticated provider API.

POSIX setup creates owner-only directories (0700) and files (0600). Doctor checks
the containing workspace's private access boundary without changing permissions.
The owner can repair that directory's mode if needed. This does not encrypt data
or restrict a fully privileged account. Native Windows setup creates protected
access lists allowing the current user, SYSTEM and Administrators. Existing unsafe
folders are refused; choose a new absent destination or have the owner repair only
the selected folder. Doctor checks access without changing it. Same-user processes
and administrators are not sandboxed.
