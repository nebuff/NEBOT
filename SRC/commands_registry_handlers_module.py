import datetime
import random
import aiohttp
import discord
import ipaddress
import socket
import asyncio
from urllib.parse import urlparse
from session_module import ShellSession, sessions, save_session_data
from packages_module import FAKE_PACKAGES, color_apt_line, build_apt_remove_lines, build_apt_list_lines, build_apt_search_lines, build_apt_show_lines, build_rm_rf_lines
from utility_module import safe_send, send_animated_output, build_prompt_line, build_help_message
from editor_module import update_editor_message
from configuration_module import FG_RED, FG_GREEN, FG_YELLOW, FG_BLUE, FG_MAGENTA, FG_CYAN, FG_BRIGHT_BLACK, BOLD, RESET

class CommandContext:
    def __init__(self, message: discord.Message, session: ShellSession, cmd: str, parts: list[str], raw_cmdline: str, used_sudo: bool):
        self.message = message
        self.session = session
        self.cmd = cmd
        self.parts = parts
        self.raw = raw_cmdline
        self.used_sudo = used_sudo
        self.prompt_line = build_prompt_line(message, session, raw_cmdline)

    async def send(self, text: str):
        await safe_send(self.message.channel, f"{self.prompt_line}\n{text}")

    async def send_plain(self, text: str):
        await safe_send(self.message.channel, text)

class SafeTCPConnector(aiohttp.TCPConnector):
    async def _resolve_host(self, host, port, traces=None):
        addrs = await super()._resolve_host(host, port, traces=traces)
        for addr in addrs:
            ip_str = addr['host']
            try:
                ip = ipaddress.ip_address(ip_str.split('%')[0])
                if not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                    raise ValueError(f"Access to IP {ip_str} is denied.")
            except ValueError as e:
                if "Access to IP" in str(e):
                    raise
        return addrs

async def is_safe_url(url):
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        loop = asyncio.get_running_loop()
        addrs = await loop.getaddrinfo(hostname, None)
        for addr in addrs:
            ip_str = addr[4][0]
            try:
                ip = ipaddress.ip_address(ip_str.split('%')[0])
                if not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                    return False
            except ValueError:
                pass
        return True
    except Exception:
        return False

COMMANDS = {}

def register_command(name: str):
    def decorator(func):
        COMMANDS[name] = func
        return func
    return decorator

@register_command("help")
async def cmd_help(ctx: CommandContext):
    pl = build_prompt_line(ctx.message, ctx.session, "")
    await ctx.send_plain(build_help_message(pl, ctx.message.author.display_name, ctx.session, "!nebot"))

@register_command("apt")
async def cmd_apt(ctx: CommandContext):
    parts = ctx.parts
    session = ctx.session
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "install" and len(parts) >= 3:
        pkgs_to_install = parts[2:]
        async with ctx.message.channel.typing():
            install_lines = []
            if ctx.used_sudo:
                install_lines.append((f"{FG_BRIGHT_BLACK}# sudo session opened on nebot{RESET}", 0.1))
            install_lines.extend([
                (color_apt_line("Reading package lists... Done"), 0.15),
                (color_apt_line("Building dependency tree... Done"), 0.15),
                (color_apt_line("Reading state information... Done"), 0.15),
            ])
            to_install = []
            for pkg_name in pkgs_to_install:
                pkg = FAKE_PACKAGES.get(pkg_name)
                if pkg is None:
                    install_lines.append((color_apt_line(f"E: Unable to locate package {pkg_name}"), 0.1))
                elif pkg_name in session.installed_packages:
                    install_lines.append((color_apt_line(f"{pkg_name} is already the newest version ({pkg['version']})."), 0.1))
                else:
                    to_install.append(pkg_name)
            if to_install:
                install_lines.append(("", 0.1))
                install_lines.append((color_apt_line("The following NEW packages will be installed:"), 0.1))
                install_lines.append((f"  {' '.join(to_install)}", 0.1))
                install_lines.append((color_apt_line(f"0 upgraded, {len(to_install)} newly installed, 0 to remove and 0 not upgraded."), 0.1))
                install_lines.append(("", 0.1))
                for idx, p in enumerate(to_install, 1):
                    install_lines.append((color_apt_line(f"Get:{idx} http://nebuff.xyz/neb stable main {p} amd64"), 0.2))
                    session.installed_packages.add(p)
                for p in to_install:
                    install_lines.append((color_apt_line(f"Unpacking {p} ..."), 0.2))
                    install_lines.append((color_apt_line(f"Setting up {p} ..."), 0.2))
                    install_lines.append((color_apt_line(f"* {p} installed"), 0.1))
            await send_animated_output(ctx.message, ctx.raw, install_lines, session)
        return
    if sub == "remove" and len(parts) >= 3:
        await send_animated_output(ctx.message, ctx.raw, build_apt_remove_lines(session, parts[2]), session)
        return
    if sub == "list":
        await send_animated_output(ctx.message, ctx.raw, build_apt_list_lines(session, "--installed" in parts), session)
        return
    if sub == "search" and len(parts) >= 3:
        await send_animated_output(ctx.message, ctx.raw, build_apt_search_lines(parts[2]), session)
        return
    if sub == "show" and len(parts) >= 3:
        await send_animated_output(ctx.message, ctx.raw, build_apt_show_lines(parts[2], session), session)
        return
    if sub == "update":
        await send_animated_output(ctx.message, ctx.raw, [
            (f"{FG_BRIGHT_BLACK}Hit:1 http://nebuff.xyz/neb stable InRelease{RESET}", 0.5),
            (f"{FG_BRIGHT_BLACK}Reading package lists... Done{RESET}", 0.6),
            (f"{FG_GREEN}All packages are up to date.{RESET}", 0.4),
        ], session)
        return
    await ctx.send(f"{FG_RED}E: Unknown apt subcommand '{sub}'{RESET}")

@register_command("git")
async def cmd_git(ctx: CommandContext):
    if "git" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: git: command not found\nhint: apt install git{RESET}")
        return
    sub = ctx.parts[1] if len(ctx.parts) > 1 else ""
    if sub == "init":
        ctx.session.mkdir(".git", parents=True)
        await ctx.send(f"Initialized empty Git repository in {ctx.session.pwd_path()}/.git/")
    elif sub == "status":
        dot_git = ctx.session._resolve(".git")
        if not dot_git:
            await ctx.send("fatal: not a git repository (or any of the parent directories): .git")
        else:
            await ctx.send("On branch main\n\nNo commits yet\n\nnothing to commit (create/copy files and use \"git add\" to track)")
    elif sub == "version" or "--version" in ctx.parts:
        await ctx.send("git version 2.39.2")
    else:
        await ctx.send("usage: git [--version] [--help] <command> [<args>]\n\nAvailable subcommands: init, status, add, commit, push, pull")

@register_command("python3")
async def cmd_python3(ctx: CommandContext):
    if "python3" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: python3: command not found\nhint: apt install python3{RESET}")
        return
    if len(ctx.parts) > 1:
        node = ctx.session._resolve(ctx.parts[1])
        if node and not node.is_dir:
            await ctx.send(f"{FG_BRIGHT_BLACK}# executing {ctx.parts[1]}...{RESET}\n{FG_GREEN}Python 3.11.4 simulation running...{RESET}\n[Output]: simulated execution of {len(node.content)} bytes successful.")
        else:
            await ctx.send(f"{FG_RED}python3: can't open file '{ctx.parts[1]}': [Errno 2] No such file or directory{RESET}")
    else:
        await ctx.send("Python 3.11.4 (main, Jun 10 2023, 05:25:59) [GCC 12.2.0] on linux\nType \"help\", \"copyright\", \"credits\" or \"license\" for more information.\n>>> ")

@register_command("nebscan")
async def cmd_nebscan(ctx: CommandContext):
    if "nebscan" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: nebscan: command not found\nhint: apt install nebscan{RESET}")
        return
    lines = [
        (f"{FG_CYAN}nebscan 1.2.0 starting...{RESET}", 0.2),
        (f"Scanning local subnet 192.168.1.0/24...", 0.5),
        (f"Host: 192.168.1.1 (neb-gateway) - {FG_GREEN}UP{RESET}", 0.3),
        (f"Host: 192.168.1.42 (neb-host) - {FG_GREEN}UP{RESET} (Self)", 0.2),
        (f"Host: 192.168.1.137 (neb-storage) - {FG_GREEN}UP{RESET}", 0.4),
        (f"Scan complete: 254 IP addresses scanned, 3 hosts up.", 0.2),
    ]
    await send_animated_output(ctx.message, "nebscan", lines, ctx.session)

@register_command("htop")
@register_command("nebtop")
async def cmd_top_vars(ctx: CommandContext):
    req = "htop" if ctx.cmd == "htop" else "nebtop"
    if req not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: {ctx.cmd}: command not found\nhint: apt install {req}{RESET}")
        return
    top_out = (
        f"{FG_CYAN}{ctx.cmd} 3.2.2 - {datetime.datetime.utcnow().strftime('%H:%M:%S')}{RESET}\n"
        f"{FG_BLUE}[|||||          25.0%]{RESET} Tasks: 3, 1 running\n"
        f"{FG_GREEN}[||             10.0%]{RESET} Mem:  312M/2048M\n"
        f"{FG_YELLOW}[               0.0%]{RESET} Swp:  0M/1024M\n\n"
        f"{FG_BRIGHT_BLACK}  PID USER      PRI  NI  VIRT  RES  SHR S %CPU %MEM   TIME+  Command{RESET}\n"
        f"    1 user       20   0  4096  512  256 S  0.0  0.0  0:01.03 init\n"
        f"   42 user       20   0  8192 1024  512 S  0.0  0.0  0:00.42 ne-shell\n"
        f"  137 user       20   0  2048  256  128 R  0.3  0.0  0:00.12 session_watcher"
    )
    await ctx.send(top_out)

@register_command("lua")
@register_command("lua5.4")
@register_command("neblua")
async def cmd_lua(ctx: CommandContext):
    if "neblua" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: lua: command not found\nhint: apt install neblua{RESET}")
        return
    await ctx.send("Lua 5.4.6  Copyright (C) 1994-2023 Lua.org, PUC-Rio\n> ")

@register_command("facet")
@register_command("facet-client")
async def cmd_facet(ctx: CommandContext):
    if "facet-client" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: facet: command not found\nhint: apt install facet-client{RESET}")
        return
    await ctx.send(f"{FG_CYAN}Facet Identity Client v0.1.0{RESET}\nUser: {ctx.message.author.display_name}\nStatus: {FG_GREEN}Verified{RESET}\nNode: neb-host-primary")

@register_command("gem")
async def cmd_gem(ctx: CommandContext):
    if "gem-daemon" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: gem: command not found\nhint: apt install gem-daemon{RESET}")
        return
    if len(ctx.parts) > 1:
        await ctx.send(f"{FG_MAGENTA}Gem AI Assistant{RESET}\n{FG_BRIGHT_BLACK}Thinking...{RESET}\nAs a simulated AI, I processed your request: \"{' '.join(ctx.parts[1:])}\"")
    else:
        await ctx.send(f"{FG_MAGENTA}Gem AI Assistant{RESET}\nDaemon status: {FG_GREEN}active{RESET}\nModel: neb-gemini-tiny-v1\nReady for prompts.")

@register_command("nesentials")
async def cmd_nesentials(ctx: CommandContext):
    if "nesentials" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: nesentials: command not found\nhint: apt install nesentials{RESET}")
        return
    await ctx.send(f"{FG_CYAN}Ne-OS Essentials Kit{RESET}\nIncludes core-utils, neb-libs, and system performance tuners.\nAll components optimized.")

@register_command("cowsay")
async def cmd_cowsay(ctx: CommandContext):
    if "cowsay" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: cowsay: command not found\nhint: apt install cowsay{RESET}")
        return
    text = " ".join(ctx.parts[1:]) if len(ctx.parts) > 1 else "Moo!"
    width = len(text)
    balloon = (
        f"  " + "_" * (width + 2) + "\n"
        f"< {text} >\n"
        f"  " + "-" * (width + 2) + "\n"
        f"        \\   ^__^\n"
        f"         \\  (oo)\\_______\n"
        f"            (__)\\       )\\/\\\n"
        "                ||----w |\n"
        "                ||     ||"
    )
    await ctx.send(balloon)

@register_command("fortune")
async def cmd_fortune(ctx: CommandContext):
    if "fortune" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: fortune: command not found\nhint: apt install fortune{RESET}")
        return
    quotes = [
        "A clean tie attracts a soup stain.",
        "Experience is what you get when you didn't get what you wanted.",
        "The generation of random numbers is too important to be left to chance.",
        "You will be hungry again in one hour.",
        "Don't fed the trolls.",
        "Everything bows to success, even grammar.",
        "The only way to get rid of a temptation is to yield to it.",
        "Digital signature not found. Proceed anyway? [Y/n]",
    ]
    await ctx.send(f"{FG_YELLOW}\"{random.choice(quotes)}\"{RESET}")

@register_command("sl")
async def cmd_sl(ctx: CommandContext):
    if "sl" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: sl: command not found\nhint: apt install sl{RESET}")
        return
    train_frames = [
        (r"      ====        ___________", 0.3),
        (r"  _][  O  |      |           |", 0.3),
        (r" <_______ |      |  Ne-OS    |", 0.3),
        (r"  /O-O-O\ ======== /O-O-O-O\ ", 0.3),
        ("", 0.2),
        (f"{FG_BRIGHT_BLACK}Choo choo! The Steam Locomotive passes by...{RESET}", 0.3)
    ]
    await send_animated_output(ctx.message, "sl", train_frames, ctx.session)

@register_command("nefetch")
async def cmd_nefetch(ctx: CommandContext):
    if "nefetch" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: nefetch: command not found\nhint: apt install nefetch{RESET}")
        return
    C = FG_CYAN
    R = RESET
    art_lines = [
        C + r" _   _        ___  ____  " + R,
        C + r"| \ | | ___  / _ \/ ___| " + R,
        C + r"|  \| |/ _ \| | | \___ \ " + R,
        C + r"| |\  |  __/| |_| |___) |" + R,
        C + r"|_| \_|\___| \___/|____/ " + R,
    ]
    delta = datetime.datetime.utcnow() - ctx.session.start_time
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    info_lines = [
        "",
        f"{FG_MAGENTA}{BOLD}nebot@neb-host{RESET}",
        f"{FG_BRIGHT_BLACK}{'-' * 24}{RESET}",
        f"{'OS:':<12} {FG_GREEN}Ne-OS 1.0 (Nebot Linux){RESET}",
        f"{'Kernel:':<12} {FG_GREEN}6.1-nebuff{RESET}",
        f"{'Shell:':<12} {FG_GREEN}ne-shell 0.1{RESET}",
        f"{'Uptime:':<12} {FG_GREEN}{h}h {m}m {s}s{RESET}",
        f"{'Packages:':<12} {FG_GREEN}{len(ctx.session.installed_packages)} installed / {len(FAKE_PACKAGES)} total{RESET}",
        f"{'CWD:':<12} {FG_BLUE}{ctx.session.pwd_path()}{RESET}",
        f"{'User:':<12} {FG_YELLOW}{ctx.message.author.display_name}{RESET}",
        f"{'Memory:':<12} {FG_GREEN}312 MB / 2048 MB{RESET}",
        f"{'CPU:':<12} {FG_GREEN}neb-core @ 3.6 GHz{RESET}",
    ]
    body = "\n".join([ctx.prompt_line] + art_lines + info_lines + ["", build_prompt_line(ctx.message, ctx.session, "")])
    await ctx.send_plain(body)

@register_command("ls")
async def cmd_ls(ctx: CommandContext):
    flags = [p for p in ctx.parts[1:] if p.startswith("-")]
    pos_args = [p for p in ctx.parts[1:] if not p.startswith("-")]
    long = any("l" in f for f in flags)
    result = ctx.session.ls(pos_args[0] if pos_args else None, long=long)
    await ctx.send_plain(f"{ctx.prompt_line}\n{result}" if result else ctx.prompt_line)

@register_command("cd")
async def cmd_cd(ctx: CommandContext):
    result = ctx.session.cd(ctx.parts[1] if len(ctx.parts) >= 2 else None)
    await ctx.send_plain(f"{ctx.prompt_line}\n{result}" if result else ctx.prompt_line)

@register_command("pwd")
async def cmd_pwd(ctx: CommandContext):
    await ctx.send(ctx.session.pwd_path())

@register_command("mkdir")
async def cmd_mkdir(ctx: CommandContext):
    flags = [p for p in ctx.parts[1:] if p.startswith("-")]
    pos_args = [p for p in ctx.parts[1:] if not p.startswith("-")]
    if not pos_args:
        await ctx.send(f"{FG_RED}mkdir: missing operand{RESET}")
        return
    result = ctx.session.mkdir(pos_args[0], parents="-p" in flags)
    await ctx.send_plain(f"{ctx.prompt_line}\n{result}" if result else ctx.prompt_line)

@register_command("touch")
async def cmd_touch(ctx: CommandContext):
    if len(ctx.parts) < 2:
        await ctx.send(f"{FG_RED}touch: missing file operand{RESET}")
        return
    result = ctx.session.touch(ctx.parts[1])
    await ctx.send_plain(f"{ctx.prompt_line}\n{result}" if result else ctx.prompt_line)

@register_command("rm")
async def cmd_rm(ctx: CommandContext):
    flags = {p for p in ctx.parts[1:] if p.startswith("-")}
    pos_args = [p for p in ctx.parts[1:] if not p.startswith("-")]
    if not pos_args:
        await ctx.send(f"{FG_RED}rm: missing operand{RESET}")
        return
    has_r = any("r" in f[1:] for f in flags)
    has_f = any("f" in f[1:] for f in flags)
    rm_lines = ctx.session.rm_rf(pos_args[0], recursive=has_r, force=has_f)
    if rm_lines:
        await send_animated_output(ctx.message, ctx.raw, build_rm_rf_lines(rm_lines), ctx.session)
    else:
        await ctx.send_plain(ctx.prompt_line)

@register_command("cat")
async def cmd_cat(ctx: CommandContext):
    if len(ctx.parts) < 2:
        await ctx.send(f"{FG_RED}cat: missing operand{RESET}")
        return
    result = ctx.session.cat(ctx.parts[1])
    await ctx.send(result if result else f"{FG_BRIGHT_BLACK}(empty file){RESET}")

@register_command("cp")
async def cmd_cp(ctx: CommandContext):
    if len(ctx.parts) < 3:
        await ctx.send(f"{FG_RED}cp: missing operand{RESET}")
        return
    result = ctx.session.cp(ctx.parts[1], ctx.parts[2])
    await ctx.send_plain(f"{ctx.prompt_line}\n{result}" if result else ctx.prompt_line)

@register_command("mv")
async def cmd_mv(ctx: CommandContext):
    if len(ctx.parts) < 3:
        await ctx.send(f"{FG_RED}mv: missing operand{RESET}")
        return
    result = ctx.session.mv(ctx.parts[1], ctx.parts[2])
    await ctx.send_plain(f"{ctx.prompt_line}\n{result}" if result else ctx.prompt_line)

@register_command("grep")
async def cmd_grep(ctx: CommandContext):
    if len(ctx.parts) < 3:
        await ctx.send(f"{FG_RED}grep: usage: grep <pattern> <file>{RESET}")
        return
    await ctx.send(ctx.session.grep(ctx.parts[1], ctx.parts[2]))

@register_command("head")
async def cmd_head(ctx: CommandContext):
    flags = [p for p in ctx.parts[1:] if p.startswith("-")]
    pos_args = [p for p in ctx.parts[1:] if not p.startswith("-")]
    if not pos_args:
        await ctx.send(f"{FG_RED}head: missing operand{RESET}")
        return
    n = 10
    for f in flags:
        try:
            n = int(f[1:])
        except ValueError:
            pass
    result = ctx.session.head(pos_args[0], n)
    await ctx.send(result if result else f"{FG_BRIGHT_BLACK}(empty){RESET}")

@register_command("tail")
async def cmd_tail(ctx: CommandContext):
    flags = [p for p in ctx.parts[1:] if p.startswith("-")]
    pos_args = [p for p in ctx.parts[1:] if not p.startswith("-")]
    if not pos_args:
        await ctx.send(f"{FG_RED}tail: missing operand{RESET}")
        return
    n = 10
    for f in flags:
        try:
            n = int(f[1:])
        except ValueError:
            pass
    result = ctx.session.tail(pos_args[0], n)
    await ctx.send(result if result else f"{FG_BRIGHT_BLACK}(empty){RESET}")

@register_command("wc")
async def cmd_wc(ctx: CommandContext):
    if len(ctx.parts) < 2:
        await ctx.send(f"{FG_RED}wc: missing operand{RESET}")
        return
    await ctx.send(ctx.session.wc(ctx.parts[1]))

@register_command("nano")
@register_command("vi")
@register_command("vim")
@register_command("edit")
async def cmd_editor(ctx: CommandContext):
    if ctx.cmd in ("vi", "vim") and "nebvim" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: {ctx.cmd}: command not found\nhint: apt install nebvim{RESET}")
        return
    if len(ctx.parts) < 2:
        await ctx.send(f"{FG_RED}{ctx.cmd}: missing filename{RESET}")
        return
    file_path = ctx.session._abs_str(ctx.parts[1])
    node = ctx.session._resolve(ctx.parts[1])
    if node and node.is_dir:
        await ctx.send(f"{FG_RED}{ctx.cmd}: {ctx.parts[1]}: Is a directory{RESET}")
        return
    existing = node.content if (node and not node.is_dir) else ""
    ed_lines = existing.splitlines() if existing else []
    ctx.session.editor = {
        "file": file_path,
        "lines": ed_lines,
        "cursor": max(1, len(ed_lines)),
        "msg_id": None,
    }
    await update_editor_message(ctx.message.channel, ctx.session)

@register_command("echo")
async def cmd_echo(ctx: CommandContext):
    raw_echo = ctx.raw[5:].strip() if ctx.raw.lower().startswith("echo") else " ".join(ctx.parts[1:])
    for k, v in ctx.session.env.items():
        raw_echo = raw_echo.replace(f"${k}", v)
    await ctx.send(raw_echo)

@register_command("printf")
async def cmd_printf(ctx: CommandContext):
    text = " ".join(ctx.parts[1:]).replace("\\n", "\n").replace("\\t", "\t")
    for k, v in ctx.session.env.items():
        text = text.replace(f"${k}", v)
    await ctx.send(text)

@register_command("whoami")
async def cmd_whoami(ctx: CommandContext):
    await ctx.send(ctx.message.author.display_name)

@register_command("hostname")
async def cmd_hostname(ctx: CommandContext):
    await ctx.send("neb-host")

@register_command("uname")
async def cmd_uname(ctx: CommandContext):
    if "-a" in ctx.parts:
        await ctx.send("Ne-OS 6.1-nebuff #1 SMP ne-shell 0.1 x86_64 GNU/Linux")
    elif "-r" in ctx.parts:
        await ctx.send("6.1-nebuff")
    elif "-s" in ctx.parts:
        await ctx.send("Ne-OS")
    else:
        await ctx.send("Ne-OS")

@register_command("date")
async def cmd_date(ctx: CommandContext):
    await ctx.send(datetime.datetime.utcnow().strftime("%a %b %d %H:%M:%S UTC %Y"))

@register_command("uptime")
async def cmd_uptime(ctx: CommandContext):
    await ctx.send(ctx.session.uptime_str())

@register_command("env")
async def cmd_env(ctx: CommandContext):
    rows = "\n".join(f"{FG_CYAN}{k}{RESET}={v}" for k, v in sorted(ctx.session.env.items()))
    await ctx.send(rows)

@register_command("export")
async def cmd_export(ctx: CommandContext):
    if len(ctx.parts) < 2 or "=" not in ctx.parts[1]:
        await ctx.send(f"{FG_RED}export: usage: export KEY=VALUE{RESET}")
        return
    k, _, v = ctx.parts[1].partition("=")
    ctx.session.env[k.strip()] = v.strip()
    await ctx.send_plain(ctx.prompt_line)

@register_command("unset")
async def cmd_unset(ctx: CommandContext):
    if len(ctx.parts) < 2:
        await ctx.send(f"{FG_RED}unset: usage: unset KEY{RESET}")
        return
    ctx.session.env.pop(ctx.parts[1], None)
    await ctx.send_plain(ctx.prompt_line)

@register_command("ps")
async def cmd_ps(ctx: CommandContext):
    await ctx.send(ctx.session.ps())

@register_command("kill")
@register_command("killall")
async def cmd_kill(ctx: CommandContext):
    pid = ctx.parts[1] if len(ctx.parts) > 1 else "?"
    await ctx.send(f"{FG_BRIGHT_BLACK}kill: ({pid}) process terminated{RESET}")

@register_command("top")
async def cmd_top(ctx: CommandContext):
    top_out = (
        f"{FG_BRIGHT_BLACK}top - {datetime.datetime.utcnow().strftime('%H:%M:%S')} "
        f"up {ctx.session.uptime_str().strip()}{RESET}\n"
        f"{FG_BRIGHT_BLACK}Tasks:{RESET}   3 total,   1 running,   2 sleeping\n"
        f"{FG_BRIGHT_BLACK}%Cpu(s):{RESET}  0.3 us,  0.1 sy,  0.0 ni, 99.6 id\n"
        f"{FG_BRIGHT_BLACK}MiB Mem:{RESET} 2048.0 total,  1421.0 free,   312.0 used\n\n"
        f"{FG_BRIGHT_BLACK}  PID USER      PR  NI  VIRT  RES  SHR S %CPU %MEM CMD{RESET}\n"
        f"    1 user      20   0  4096  512  256 S  0.0  0.0 init\n"
        f"   42 user      20   0  8192 1024  512 S  0.0  0.0 ne-shell\n"
        f"  137 user      20   0  2048  256  128 R  0.3  0.0 session_watcher"
    )
    await ctx.send(top_out)

@register_command("df")
async def cmd_df(ctx: CommandContext):
    await ctx.send(ctx.session.df())

@register_command("free")
async def cmd_free(ctx: CommandContext):
    await ctx.send(ctx.session.free())

@register_command("curl")
async def cmd_curl(ctx: CommandContext):
    if "curl" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: curl: command not found\nhint: apt install curl{RESET}")
        return
    if len(ctx.parts) < 2:
        await ctx.send(f"{FG_RED}curl: usage: curl <url> [destination_path]{RESET}")
        return
    url = ctx.parts[1]
    dest = ctx.parts[2] if len(ctx.parts) > 2 else None
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    if not await is_safe_url(url):
        await ctx.send(f"{FG_RED}curl: error fetching URL: Access to local/private network is blocked.{RESET}")
        return

    async with ctx.message.channel.typing():
        try:
            connector = SafeTCPConnector(resolver=SafeResolver())
            async with aiohttp.ClientSession(connector=connector) as web_session:
                async with web_session.get(url, timeout=10, allow_redirects=False) as response:
                    content_type = response.headers.get("Content-Type", "")
                    if "text" in content_type or "markdown" in content_type:
                        data = await response.text()
                        if dest:
                            err = ctx.session.write_file(dest, data)
                            if err:
                                await ctx.send(err)
                            else:
                                size = len(data.encode())
                                await ctx.send(f" % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current\n                                 Dload  Upload   Total   Spent    Left  Speed\n100 {size:>4}  100 {size:>4}    0     0  {size*2:>5}      0 --:--:-- --:--:-- --:--:-- {size*2:>5}\n{FG_GREEN}Stored in {dest}{RESET}")
                        else:
                            if len(data) > 3800:
                                data = data[:3800] + f"\n\n{FG_YELLOW}[Output truncated: This site is way too long for a terminal!]{RESET}"
                            await ctx.send(data)
                    else:
                        await ctx.send(f"{FG_RED}curl: binary or unsupported content-type ({content_type}) rejected.{RESET}")
        except Exception as e:
            await ctx.send(f"{FG_RED}curl: error fetching URL: {str(e)}{RESET}")

@register_command("history")
async def cmd_history(ctx: CommandContext):
    if not ctx.session.history:
        await ctx.send(f"{FG_BRIGHT_BLACK}(no history){RESET}")
        return
    rows = "\n".join(
        f"{FG_BRIGHT_BLACK}{i+1:>4}{RESET}  {h}"
        for i, h in enumerate(ctx.session.history[-20:])
    )
    await ctx.send(rows)

@register_command("clear")
async def cmd_clear(ctx: CommandContext):
    await ctx.send_plain(build_prompt_line(ctx.message, ctx.session, ""))

@register_command("exit")
async def cmd_exit(ctx: CommandContext):
    guild_id = ctx.message.guild.id if ctx.message.guild else None
    is_shared = not (ctx.message.guild is None) and getattr(ctx, "is_shared", False)
    if is_shared:
        key = (guild_id, ctx.message.channel.id, "shared")
    else:
        key = (guild_id, ctx.message.channel.id, ctx.message.author.id)

    sessions.pop(key, None)
    if ctx.message.guild is None or is_shared:
        save_session_data()
    await ctx.send(
        f"{FG_BRIGHT_BLACK}# Session ended. Goodbye, "
        f"{ctx.message.author.display_name}.{RESET}"
    )

@register_command("minesweeper")
async def cmd_minesweeper(ctx: CommandContext):
    if "minesweeper" not in ctx.session.installed_packages:
        await ctx.send(f"{FG_RED}bash: minesweeper: command not found\nhint: apt install minesweeper{RESET}")
        return
        
    cfg = get_guild_config(ctx.message.guild.id if ctx.message.guild else None)
    if not cfg.get("minesweeper_enabled", False):
        await ctx.send(f"{FG_RED}Error: The Minesweeper package has been disabled by the administrator.{RESET}")
        return
        
    rows, cols = 5, 5
    num_mines = cfg.get("minesweeper_default_mines", 4)
    
    if len(ctx.parts) > 1:
        size_part = ctx.parts[1]
        try:
            if "x" in size_part:
                r_str, c_str = size_part.lower().split("x")
                r, c = int(r_str), int(c_str)
            else:
                r = c = int(size_part)
            if 3 <= r <= 10 and 3 <= c <= 10:
                rows, cols = r, c
            else:
                await ctx.send(f"{FG_RED}Error: Size must be between 3x3 and 10x10.{RESET}")
                return
        except ValueError:
            await ctx.send(f"{FG_RED}Error: Invalid size format. Use e.g. 5x5 or 6.{RESET}")
            return
            
    if len(ctx.parts) > 2:
        try:
            m = int(ctx.parts[2])
            if 1 <= m <= (rows * cols - 1):
                num_mines = m
            else:
                await ctx.send(f"{FG_RED}Error: Number of mines must be between 1 and {rows * cols - 1}.{RESET}")
                return
        except ValueError:
            await ctx.send(f"{FG_RED}Error: Invalid mine count.{RESET}")
            return

    cells = [(r, c) for r in range(rows) for c in range(cols)]
    mine_cells = set(random.sample(cells, num_mines))
    
    emojis = {
        0: ":zero:",
        1: ":one:",
        2: ":two:",
        3: ":three:",
        4: ":four:",
        5: ":five:",
        6: ":six:",
        7: ":seven:",
        8: ":eight:"
    }
    
    grid_lines = []
    for r in range(rows):
        row_cells = []
        for c in range(cols):
            if (r, c) in mine_cells:
                row_cells.append("||:bomb:||")
            else:
                count = sum(
                    1 for dr in [-1, 0, 1] for dc in [-1, 0, 1]
                    if (dr != 0 or dc != 0)
                    and 0 <= r + dr < rows
                    and 0 <= c + dc < cols
                    and (r + dr, c + dc) in mine_cells
                )
                row_cells.append(f"||{emojis[count]}||")
        grid_lines.append(" ".join(row_cells))
        
    board_str = "\n".join(grid_lines)
    header = (
        f"{FG_CYAN}Ne-OS Minesweeper Grid ({rows}x{cols}, {num_mines} mines){RESET}\n"
        f"Click/tap on the spoiler blocks to play!\n\n"
    )
    await ctx.send_plain(f"{ctx.prompt_line}\n{header}{board_str}")

async def process_command(message: discord.Message, session: ShellSession, cmdline: str, is_shared: bool = False):
    used_sudo = False
    work = cmdline
    if work.lower().startswith("sudo "):
        used_sudo = True
        work = work[5:].lstrip()

    parts = work.split()
    if not parts:
        return

    cmd = parts[0].lower()
    ctx = CommandContext(message, session, cmd, parts, cmdline, used_sudo)
    ctx.is_shared = is_shared

    if cmd in COMMANDS:
        await COMMANDS[cmd](ctx)
    else:
        await ctx.send(f"{FG_RED}bash: {cmd}: command not found{RESET}")
    
    if message.guild is None or is_shared:
        save_session_data()