from configuration_module import FG_BRIGHT_BLACK, FG_YELLOW, FG_MAGENTA, FG_GREEN, FG_RED, FG_CYAN, RESET
from session_module import ShellSession

FAKE_PACKAGES: dict[str, dict] = {
    "nesentials": {"version": "0.0.1-neb1", "summary": "Base utilities for the Neb environment.", "lines": []},
    "nefetch": {"version": "1.0.0-neb1", "summary": "Fast system fetch for Ne-OS sessions.", "lines": []},
    "facet-client": {"version": "0.1.0-neb1", "summary": "Facet identity client and TUI.", "lines": []},
    "gem-daemon": {"version": "0.3.2-neb1", "summary": "Background daemon for Gem local AI assistant.", "lines": []},
    "nebvim": {"version": "0.9.1-neb1", "summary": "Neb-flavoured vim text editor.", "lines": []},
    "nebtop": {"version": "3.3.0-neb1", "summary": "Interactive process viewer for Ne-OS.", "lines": []},
    "curl": {"version": "7.88.1-neb1", "summary": "Command line tool for transferring data.", "lines": []},
    "git": {"version": "2.39.2-neb1", "summary": "Fast, scalable, distributed revision control.", "lines": []},
    "python3": {"version": "3.11.4-neb1", "summary": "Interactive high-level object-oriented language (v3).", "lines": []},
    "nebscan": {"version": "1.2.0-neb1", "summary": "Ne-OS network and port scanner utility.", "lines": []},
    "htop": {"version": "3.2.2-neb1", "summary": "Interactive process viewer (enhanced top).", "lines": []},
    "neblua": {"version": "5.4.6-neb1", "summary": "Lua 5.4 scripting runtime for Ne-OS.", "lines": []},
    "cowsay": {"version": "3.03-neb1", "summary": "Configurable talking cow.", "lines": []},
    "fortune": {"version": "1.99.1-neb1", "summary": "Provides a random, hopefully interesting, adage.", "lines": []},
    "sl": {"version": "5.02-neb1", "summary": "Correct you if you type 'sl' by mistake.", "lines": []},
    "minesweeper": {"version": "1.0.0-neb1", "summary": "Interactive Minesweeper game client for Ne-OS.", "lines": []},
}

def color_apt_line(line: str) -> str:
    if line.startswith(("Reading ", "Building ", "Listing...")):
        return f"{FG_BRIGHT_BLACK}{line}{RESET}"
    if line.startswith("The following NEW"):
        return f"{FG_YELLOW}{line}{RESET}"
    if line.startswith(("0 upgraded", "Need to get", "After this operation")):
        return f"{FG_BRIGHT_BLACK}{line}{RESET}"
    if line.startswith(("Get:", "Fetched")):
        return f"{FG_MAGENTA}{line}{RESET}"
    if line.startswith(("Selecting previously", "Preparing to unpack", "Unpacking", "Setting up")):
        return f"{FG_BRIGHT_BLACK}{line}{RESET}"
    if line.startswith("*"):
        return f"{FG_GREEN}{line}{RESET}"
    if line.startswith("E: "):
        return f"{FG_RED}{line}{RESET}"
    return line

def build_apt_remove_lines(session: ShellSession, pkg_name: str) -> list[tuple[str, float]]:
    if pkg_name not in session.installed_packages:
        base_lines = [
            "Reading package lists... Done",
            "Building dependency tree... Done",
            "Reading state information... Done",
            f"E: Package '{pkg_name}' is not installed",
        ]
    else:
        session.installed_packages.discard(pkg_name)
        base_lines = [
            "Reading package lists... Done",
            "Building dependency tree... Done",
            "Reading state information... Done",
            "",
            "The following packages will be REMOVED:",
            f"  {pkg_name}",
            "0 upgraded, 0 newly installed, 1 to remove and 0 not upgraded.",
            "",
            f"Removing {pkg_name} ...",
            f"* {pkg_name} removed",
        ]
    result: list[tuple[str, float]] = []
    delay = 0.15
    for line in base_lines:
        result.append((color_apt_line(line), delay))
        delay = min(delay + 0.08, 0.4)
    return result

def build_apt_list_lines(session: ShellSession, installed_only: bool = False) -> list[tuple[str, float]]:
    lines: list[tuple[str, float]] = []
    delay = 0.1
    lines.append((color_apt_line("Listing... Done"), delay))
    delay = min(delay + 0.05, 0.4)
    for name in sorted(FAKE_PACKAGES.keys()):
        inst = name in session.installed_packages
        if installed_only and not inst:
            continue
        meta = FAKE_PACKAGES[name]
        version = str(meta.get("version", "0.0.0"))
        summary = str(meta.get("summary", ""))
        sc = FG_GREEN if inst else FG_YELLOW
        status = f"{sc}[{'installed' if inst else 'available'}]{RESET}"
        lines.append((f"{name:<16} {version:<18} {status}  {summary}", delay))
        delay = min(delay + 0.05, 0.9)
    return lines

def build_apt_search_lines(query: str) -> list[tuple[str, float]]:
    lines: list[tuple[str, float]] = []
    delay = 0.1
    matches = {k: v for k, v in FAKE_PACKAGES.items()
               if query.lower() in k.lower()
               or query.lower() in str(v.get("summary", "")).lower()}
    if not matches:
        lines.append((f"{FG_BRIGHT_BLACK}(no results for '{query}'){RESET}", delay))
        return lines
    for name, meta in sorted(matches.items()):
        version = str(meta.get("version", "0.0.0"))
        summary = str(meta.get("summary", ""))
        lines.append((
            f"{FG_GREEN}{name}{RESET}/{FG_BRIGHT_BLACK}neb{RESET} {version}\n  {summary}",
            delay
        ))
        delay = min(delay + 0.05, 0.4)
    return lines

def build_apt_show_lines(pkg_name: str, session: ShellSession) -> list[tuple[str, float]]:
    pkg = FAKE_PACKAGES.get(pkg_name)
    if pkg is None:
        return [(f"{FG_RED}E: No packages found{RESET}", 0.3)]
    inst = pkg_name in session.installed_packages
    version = str(pkg.get("version", "0.0.0"))
    summary = str(pkg.get("summary", ""))
    sc = FG_GREEN if inst else FG_YELLOW
    rows = [
        f"Package: {FG_CYAN}{pkg_name}{RESET}",
        f"Version: {version}",
        f"Section: neb/utils",
        f"Origin:  nebuff.xyz",
        f"Status:  {sc}{'installed' if inst else 'not installed'}{RESET}",
        f"Desc:    {summary}",
    ]
    return [(r, 0.3) for r in rows]

def build_rm_rf_lines(lines: list[str]) -> list[tuple[str, float]]:
    result: list[tuple[str, float]] = []
    delay = 0.1
    for line in lines:
        result.append((line, delay))
        delay = min(delay + 0.05, 0.3)
    return result