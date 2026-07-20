import asyncio
import discord
from session_module import ShellSession
from configuration_module import FG_GREEN, FG_BRIGHT_BLACK, FG_CYAN, FG_BLUE, BOLD, FG_YELLOW, RESET

def ansi_block(content: str) -> str:
    return f"```ansi\n{content}\n```"

async def safe_send(channel: discord.abc.Messageable, content: str, delete_after: int | None = None):
    limit = 1900
    if len(content) <= limit:
        await channel.send(ansi_block(content), delete_after=delete_after)
        return

    lines = content.splitlines()
    buffer = []
    current_len = 0

    for line in lines:
        if current_len + len(line) + 1 > limit:
            if buffer:
                await channel.send(ansi_block("\n".join(buffer)))
                buffer = []
                current_len = 0
            while len(line) > limit:
                await channel.send(ansi_block(line[:limit]))
                line = line[limit:]
        
        buffer.append(line)
        current_len += len(line) + 1

    if buffer:
        await channel.send(ansi_block("\n".join(buffer)), delete_after=delete_after)

def build_prompt_line(message: discord.Message, session: ShellSession, raw_command: str) -> str:
    username = message.author.display_name if hasattr(message.author, "display_name") else "user"
    cwd = session.pwd_path()
    prompt = (f"{FG_GREEN}{username}{RESET}"
              f"{FG_BRIGHT_BLACK}@{RESET}"
              f"{FG_CYAN}neb-host{RESET}"
              f":{FG_BLUE}{cwd}{RESET}$")
    return f"{prompt} {raw_command}".rstrip()

async def send_animated_output(message: discord.Message, prompt: str, lines: list[tuple[str, float]], session: ShellSession) -> None:
    async with message.channel.typing():
        prompt_line = build_prompt_line(message, session, prompt)
        all_lines = [prompt_line]
        sent = await message.channel.send(ansi_block(all_lines[0]))
        for line, delay in lines:
            await asyncio.sleep(delay)
            all_lines.append(line)
            try:
                await sent.edit(content=ansi_block("\n".join(all_lines)))
            except (discord.Forbidden, discord.HTTPException):
                break
        end_prompt = build_prompt_line(message, session, "")
        all_lines.append(end_prompt)
        try:
            await sent.edit(content=ansi_block("\n".join(all_lines)))
        except (discord.Forbidden, discord.HTTPException):
            pass

def build_help_message(prompt_line: str, username: str, session: ShellSession, full_prefix: str) -> str:
    lines = [
        prompt_line,
        f"{FG_BRIGHT_BLACK}# Ne-OS shell — session created for {username}{RESET}",
        "",
        f"{BOLD}{FG_YELLOW}USAGE:{RESET} {full_prefix} <command> [args]",
        "",
        f"{BOLD}{FG_CYAN}FILESYSTEM{RESET}",
        "  ls [-l] [path]            list directory contents",
        "  cd [path]                 change directory",
        "  pwd                       print working directory",
        "  mkdir [-p] <path>         create directory",
        "  touch <file>              create/update file timestamp",
        "  rm [-rf] <path>           remove file or directory",
        "  cp <src> <dst>            copy a file",
        "  mv <src> <dst>            move or rename a file",
        "  cat <file>                print file contents",
        "  head [-N] <file>          first N lines (default 10)",
        "  tail [-N] <file>          last N lines (default 10)",
        "  grep <pattern> <file>     search for pattern in file",
        "  wc <file>                 word/line/char count",
        "",
        f"{BOLD}{FG_CYAN}TEXT EDITOR{RESET}",
        "  nano/vi/vim/edit <file>   open file in editor",
        f"  {FG_BRIGHT_BLACK}Inside editor — send these as your next message:{RESET}",
        "    :w            save file",
        "    :q            quit without saving",
        "    :wq / :x      save and quit",
        "    :set <n>      jump cursor to line n",
        "    :d <n>        delete line n",
        "    :r <n> <txt>  replace line n with txt",
        "    :<text>       append a new line",
        "    <text>        also appends a new line",
        "",
        f"{BOLD}{FG_CYAN}SYSTEM{RESET}",
        "  echo <text>               print text (supports $VAR)",
        "  printf <fmt>              print with \\n and \\t escapes",
        "  whoami                    show current user",
        "  hostname                  show machine hostname",
        "  uname [-a|-r|-s]          system info",
        "  date                      current UTC date and time",
        "  uptime                    session uptime",
        "  env                       list environment variables",
        "  export KEY=VAL            set environment variable",
        "  unset KEY                 remove environment variable",
        "  ps                        list processes",
        "  top                       process snapshot",
        "  kill <pid>                terminate a process",
        "  df                        disk usage",
        "  free                      memory usage",
        "  history                   show command history",
        "  clear                     clear screen",
        "  exit                      end your session",
        "",
        f"{BOLD}{FG_CYAN}PACKAGES{RESET}",
        "  apt install <pkg>         install a package",
        "  apt remove <pkg>          remove a package",
        "  apt list [--installed]    list packages",
        "  apt search <query>        search packages",
        "  apt show <pkg>            show package details",
        "  apt update                refresh package index",
    ]
    if "nefetch" in session.installed_packages:
        lines += ["", f"{BOLD}{FG_CYAN}EXTRAS{RESET}",
                  "  nefetch                   Ne-OS system info fetch"]
    return "\n".join(lines)