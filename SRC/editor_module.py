import discord
from session_module import ShellSession
from utility_module import ansi_block
from configuration_module import FG_CYAN, FG_WHITE, FG_YELLOW, FG_GREEN, FG_BRIGHT_BLACK, FG_RED, RESET

EDITOR_MAX_LINES = 18

def build_editor_view(session: ShellSession) -> str:
    if session.editor is None:
        return ""
    ed = session.editor
    path = ed["file"]
    lines = ed["lines"]
    cursor = ed["cursor"]

    start = max(0, cursor - EDITOR_MAX_LINES // 2)
    end = min(len(lines), start + EDITOR_MAX_LINES)
    start = max(0, end - EDITOR_MAX_LINES)

    bar = FG_BRIGHT_BLACK + "-" * 52 + RESET
    header = (
        f"{bar}\n"
        f"  {FG_CYAN}nano{RESET}  {FG_WHITE}{path}{RESET}"
        f"  {FG_BRIGHT_BLACK}[{len(lines)} lines]{RESET}\n"
        f"{bar}"
    )
    body_rows: list[str] = []
    for i in range(start, end):
        ln = i + 1
        txt = lines[i]
        if ln == cursor:
            body_rows.append(f"{FG_YELLOW}{ln:>4}{RESET}  {FG_GREEN}>{RESET} {txt}")
        else:
            body_rows.append(f"{FG_BRIGHT_BLACK}{ln:>4}{RESET}    {txt}")
    if not lines:
        body_rows.append(f"{FG_BRIGHT_BLACK}    (empty file){RESET}")

    footer = (
        f"{bar}\n"
        f"{FG_BRIGHT_BLACK}:w save  :q quit  :wq save+quit  "
        f":<text> append line  :d <n> del  :r <n> <t> replace  :set <n> goto{RESET}"
    )
    return "\n".join([header] + body_rows + [footer])

async def update_editor_message(channel: discord.abc.Messageable, session: ShellSession) -> None:
    view = build_editor_view(session)
    if not view:
        return
    ed = session.editor
    if ed["msg_id"] is not None:
        try:
            msg = await channel.fetch_message(ed["msg_id"])
            await msg.edit(content=ansi_block(view))
            return
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            pass
    sent = await channel.send(ansi_block(view))
    ed["msg_id"] = sent.id

async def handle_editor_command(message: discord.Message, session: ShellSession, raw: str) -> None:
    ed = session.editor
    cmd = raw.strip()

    if cmd == ":w":
        content = "\n".join(ed["lines"]) + ("\n" if ed["lines"] else "")
        err = session.write_file(ed["file"], content)
        if err:
            await message.channel.send(ansi_block(f"{FG_RED}{err}{RESET}"), delete_after=4)
        else:
            await message.channel.send(
                ansi_block(f"{FG_GREEN}'{ed['file']}' written ({len(ed['lines'])} lines){RESET}"),
                delete_after=3
            )
        await update_editor_message(message.channel, session)
        return

    if cmd in (":q", ":quit"):
        session.editor = None
        await message.channel.send(ansi_block(f"{FG_BRIGHT_BLACK}# Editor closed without saving{RESET}"), delete_after=3)
        return

    if cmd in (":wq", ":x"):
        content = "\n".join(ed["lines"]) + ("\n" if ed["lines"] else "")
        err = session.write_file(ed["file"], content)
        session.editor = None
        if err:
            await message.channel.send(ansi_block(f"{FG_RED}{err}{RESET}"), delete_after=4)
        else:
            await message.channel.send(ansi_block(f"{FG_GREEN}Saved and closed '{ed['file']}'{RESET}"), delete_after=3)
        return

    if cmd.startswith(":set "):
        try:
            n = int(cmd.split()[1])
            ed["cursor"] = max(1, min(n, max(len(ed["lines"]), 1)))
            await update_editor_message(message.channel, session)
        except (ValueError, IndexError):
            await message.channel.send(ansi_block(f"{FG_RED}:set requires a line number{RESET}"), delete_after=3)
        return

    if cmd.startswith(":d "):
        try:
            n = int(cmd.split()[1])
            if 1 <= n <= len(ed["lines"]):
                del ed["lines"][n - 1]
                ed["cursor"] = max(1, min(ed["cursor"], max(len(ed["lines"]), 1)))
                await update_editor_message(message.channel, session)
            else:
                await message.channel.send(ansi_block(f"{FG_RED}line {n} out of range{RESET}"), delete_after=3)
        except (ValueError, IndexError):
            await message.channel.send(ansi_block(f"{FG_RED}:d requires a line number{RESET}"), delete_after=3)
        return

    if cmd.startswith(":r "):
        parts = cmd.split(None, 2)
        if len(parts) < 3:
            await message.channel.send(ansi_block(f"{FG_RED}:r requires a line number and text{RESET}"), delete_after=3)
            return
        try:
            n = int(parts[1])
            if 1 <= n <= len(ed["lines"]):
                ed["lines"][n - 1] = parts[2]
                ed["cursor"] = n
                await update_editor_message(message.channel, session)
            else:
                await message.channel.send(ansi_block(f"{FG_RED}line {n} out of range{RESET}"), delete_after=3)
        except ValueError:
            await message.channel.send(ansi_block(f"{FG_RED}:r requires a line number{RESET}"), delete_after=3)
        return

    text = cmd[1:] if cmd.startswith(":") else cmd
    ed["lines"].append(text)
    ed["cursor"] = len(ed["lines"])
    await update_editor_message(message.channel, session)