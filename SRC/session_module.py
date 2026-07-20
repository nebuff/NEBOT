import os
import json
import datetime
from filesystem_module import FSNode, create_default_root
from configuration_module import FG_RED, FG_CYAN, FG_WHITE, BOLD, RESET, FG_BRIGHT_BLACK

class ShellSession:
    def __init__(self, user_id: int, channel_id: int):
        self.user_id = user_id
        self.channel_id = channel_id
        self.root = create_default_root()
        self.cwd: list[str] = ["home", "user"]
        self.last_activity = datetime.datetime.utcnow()
        self.warning_started_at: datetime.datetime | None = None
        self.warning_message_id: int | None = None
        self.installed_packages: set[str] = set()
        self.history: list[str] = []
        self.env: dict[str, str] = {
            "HOME":  "/home/user",
            "USER":  "user",
            "SHELL": "/bin/ne-shell",
            "PATH":  "/usr/local/bin:/usr/bin:/bin",
            "TERM":  "discord-ansi",
        }
        self.start_time = datetime.datetime.utcnow()
        self.editor: dict | None = None
        self.is_persistent = False

    def touch_activity(self):
        self.last_activity = datetime.datetime.utcnow()
        self.warning_started_at = None
        self.warning_message_id = None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "cwd": self.cwd,
            "installed_packages": list(self.installed_packages),
            "history": self.history,
            "env": self.env,
            "start_time": self.start_time.isoformat(),
            "root": self.root.to_dict(),
            "is_persistent": self.is_persistent
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ShellSession":
        s = cls(user_id=d["user_id"], channel_id=d["channel_id"])
        s.cwd = d.get("cwd", ["home", "user"])
        s.installed_packages = set(d.get("installed_packages", []))
        s.history = d.get("history", [])
        s.env = d.get("env", s.env)
        if "start_time" in d:
            s.start_time = datetime.datetime.fromisoformat(d["start_time"])
        if "root" in d:
            s.root = FSNode.from_dict(d["root"])
        s.is_persistent = d.get("is_persistent", False)
        return s

    def pwd_path(self) -> str:
        return "/" if not self.cwd else "/" + "/".join(self.cwd)

    def _abs_parts(self, path: str | None) -> list[str]:
        if not path or path in (".", "~"):
            base = list(self.cwd)
            segs: list[str] = []
        elif path == "/":
            return []
        elif path.startswith("/"):
            base = []
            segs = [s for s in path.split("/") if s and s != "."]
        else:
            base = list(self.cwd)
            segs = [s for s in path.split("/") if s and s != "."]
        for s in segs:
            if s == "..":
                if base:
                    base.pop()
            else:
                base.append(s)
        return base

    def _get_node(self, parts: list[str]) -> "FSNode | None":
        node = self.root
        for seg in parts:
            if seg not in node.children:
                return None
            node = node.children[seg]
        return node

    def _resolve(self, path: str | None) -> "FSNode | None":
        return self._get_node(self._abs_parts(path))

    def _resolve_parent_leaf(self, path: str) -> "tuple[FSNode | None, str]":
        parts = self._abs_parts(path)
        if not parts:
            return None, ""
        return self._get_node(parts[:-1]), parts[-1]

    def _abs_str(self, path: str | None) -> str:
        p = self._abs_parts(path)
        return "/" if not p else "/" + "/".join(p)

    def mkdir(self, path: str, parents: bool = False) -> str:
        if not path:
            return f"{FG_RED}mkdir: missing operand{RESET}"
        parts = self._abs_parts(path)
        if not parts:
            return f"{FG_RED}mkdir: invalid path{RESET}"
        if parents:
            node = self.root
            for part in parts:
                if part not in node.children:
                    node.children[part] = FSNode(part, is_dir=True)
                node = node.children[part]
            return ""
        parent = self._get_node(parts[:-1])
        if parent is None or not parent.is_dir:
            return f"{FG_RED}mkdir: cannot create directory '{path}': No such file or directory{RESET}"
        leaf = parts[-1]
        if leaf in parent.children:
            return f"{FG_RED}mkdir: cannot create directory '{path}': File exists{RESET}"
        parent.children[leaf] = FSNode(leaf, is_dir=True)
        return ""

    def touch(self, path: str) -> str:
        parent, leaf = self._resolve_parent_leaf(path)
        if parent is None or not parent.is_dir:
            return f"{FG_RED}touch: cannot touch '{path}': No such file or directory{RESET}"
        if leaf not in parent.children:
            parent.children[leaf] = FSNode(leaf, is_dir=False, content="")
        else:
            parent.children[leaf].modified = datetime.datetime.utcnow()
        return ""

    def ls(self, path: str | None = None, long: bool = False) -> str:
        node = self._resolve(path)
        target = path or ""
        if node is None:
            return f"{FG_RED}ls: cannot access '{target}': No such file or directory{RESET}"
        if not node.is_dir:
            if long:
                ts = node.modified.strftime("%b %d %H:%M")
                return f"-rw-r--r-- 1 user user {node.size():>6}  {ts}  {node.name}"
            return node.name
        names = sorted(node.children.keys())
        if not names:
            return ""
        if not long:
            parts: list[str] = []
            for name in names:
                child = node.children[name]
                color = FG_CYAN + BOLD if child.is_dir else FG_WHITE
                suffix = "/" if child.is_dir else ""
                parts.append(f"{color}{name}{suffix}{RESET}")
            return "  ".join(parts)
        rows: list[str] = [f"{FG_BRIGHT_BLACK}total {len(names)}{RESET}"]
        for name in names:
            child = node.children[name]
            ts = child.modified.strftime("%b %d %H:%M")
            if child.is_dir:
                rows.append(f"drwxr-xr-x 2 user user      -  {ts}  {FG_CYAN}{BOLD}{name}/{RESET}")
            else:
                rows.append(f"-rw-r--r-- 1 user user {child.size():>6}  {ts}  {name}")
        return "\n".join(rows)

    def cd(self, path: str | None) -> str:
        parts = self._abs_parts(path if path else "~")
        node = self._get_node(parts)
        if node is None:
            return f"{FG_RED}bash: cd: {path}: No such file or directory{RESET}"
        if not node.is_dir:
            return f"{FG_RED}bash: cd: {path}: Not a directory{RESET}"
        self.cwd = parts
        return ""

    def cat(self, path: str) -> str:
        node = self._resolve(path)
        if node is None:
            return f"{FG_RED}cat: {path}: No such file or directory{RESET}"
        if node.is_dir:
            return f"{FG_RED}cat: {path}: Is a directory{RESET}"
        return node.content or ""

    def write_file(self, path: str, content: str) -> str:
        parent, leaf = self._resolve_parent_leaf(path)
        if parent is None or not parent.is_dir:
            return f"{FG_RED}cannot write '{path}': No such directory{RESET}"
        if leaf in parent.children and parent.children[leaf].is_dir:
            return f"{FG_RED}cannot write '{path}': Is a directory{RESET}"
        parent.children[leaf] = FSNode(leaf, is_dir=False, content=content)
        return ""

    def cp(self, src: str, dst: str) -> str:
        src_node = self._resolve(src)
        if src_node is None:
            return f"{FG_RED}cp: cannot stat '{src}': No such file or directory{RESET}"
        if src_node.is_dir:
            return f"{FG_RED}cp: omitting directory '{src}'{RESET}"
        dst_node = self._resolve(dst)
        if dst_node and dst_node.is_dir:
            parent = dst_node
            leaf = src_node.name
        else:
            parent, leaf = self._resolve_parent_leaf(dst)
            if parent is None or not parent.is_dir:
                return f"{FG_RED}cp: cannot create '{dst}': No such file or directory{RESET}"
        parent.children[leaf] = FSNode(leaf, is_dir=False, content=src_node.content)
        return ""

    def mv(self, src: str, dst: str) -> str:
        src_parts = self._abs_parts(src)
        if not src_parts:
            return f"{FG_RED}mv: cannot move root{RESET}"
        src_parent = self._get_node(src_parts[:-1])
        src_leaf = src_parts[-1]
        if src_parent is None or src_leaf not in src_parent.children:
            return f"{FG_RED}mv: cannot stat '{src}': No such file or directory{RESET}"
        src_node = src_parent.children[src_leaf]
        dst_node = self._resolve(dst)
        if dst_node and dst_node.is_dir:
            dst_node.children[src_leaf] = src_node
        else:
            dst_parent, dst_leaf = self._resolve_parent_leaf(dst)
            if dst_parent is None or not dst_parent.is_dir:
                return f"{FG_RED}mv: cannot move to '{dst}': No such file or directory{RESET}"
            dst_parent.children[dst_leaf] = src_node
            src_node.name = dst_leaf
        del src_parent.children[src_leaf]
        if self._get_node(self.cwd) is None:
            self.cwd = []
        return ""

    def rm_rf(self, path: str, recursive: bool = False, force: bool = False) -> list[str]:
        lines: list[str] = []
        if not path:
            lines.append(f"{FG_RED}rm: missing operand{RESET}")
            return lines
        if path == "/":
            lines.append(f"{FG_RED}rm: it is dangerous to operate recursively on '/'{RESET}")
            lines.append(f"{FG_RED}rm: use --no-preserve-root to override this failsafe{RESET}")
            return lines
        parts = self._abs_parts(path)
        parent = self._get_node(parts[:-1])
        leaf = parts[-1] if parts else ""
        if not parts or parent is None or leaf not in parent.children:
            if not force:
                lines.append(f"{FG_RED}rm: cannot remove '{path}': No such file or directory{RESET}")
            return lines
        target = parent.children[leaf]
        if target.is_dir and not recursive:
            lines.append(f"{FG_RED}rm: cannot remove '{path}': Is a directory{RESET}")
            return lines

        def walk(n: FSNode, p: list[str]):
            this = "/" + "/".join(p) if p else "/"
            if n.is_dir:
                for cn, ch in list(n.children.items()):
                    walk(ch, p + [cn])
                if this != "/":
                    lines.append(f"{FG_BRIGHT_BLACK}rm: removing directory '{this}'{RESET}")
            else:
                lines.append(f"{FG_BRIGHT_BLACK}rm: removing '{this}'{RESET}")

        walk(target, parts)
        del parent.children[leaf]
        if self._get_node(self.cwd) is None:
            self.cwd = []
        return lines

    def grep(self, pattern: str, path: str) -> str:
        node = self._resolve(path)
        if node is None:
            return f"{FG_RED}grep: {path}: No such file or directory{RESET}"
        if node.is_dir:
            return f"{FG_RED}grep: {path}: Is a directory{RESET}"
        results: list[str] = []
        for i, line in enumerate(node.content.splitlines(), 1):
            if pattern.lower() in line.lower():
                idx = line.lower().find(pattern.lower())
                hl = (line[:idx]
                       + f"{FG_RED}{line[idx:idx+len(pattern)]}{RESET}"
                       + line[idx+len(pattern):])
                results.append(f"{FG_BRIGHT_BLACK}{i}:{RESET} {hl}")
        return "\n".join(results) if results else f"{FG_BRIGHT_BLACK}(no matches){RESET}"

    def head(self, path: str, n: int = 10) -> str:
        node = self._resolve(path)
        if node is None:
            return f"{FG_RED}head: {path}: No such file or directory{RESET}"
        if node.is_dir:
            return f"{FG_RED}head: {path}: Is a directory{RESET}"
        return "\n".join(node.content.splitlines()[:n])

    def tail(self, path: str, n: int = 10) -> str:
        node = self._resolve(path)
        if node is None:
            return f"{FG_RED}tail: {path}: No such file or directory{RESET}"
        if node.is_dir:
            return f"{FG_RED}tail: {path}: Is a directory{RESET}"
        return "\n".join(node.content.splitlines()[-n:])

    def wc(self, path: str) -> str:
        node = self._resolve(path)
        if node is None:
            return f"{FG_RED}wc: {path}: No such file or directory{RESET}"
        if node.is_dir:
            return f"{FG_RED}wc: {path}: Is a directory{RESET}"
        lns = node.content.splitlines()
        words = node.content.split()
        return f"  {len(lns):>4}  {len(words):>4}  {len(node.content):>4} {path}"

    def df(self) -> str:
        return "\n".join([
            f"{FG_BRIGHT_BLACK}Filesystem      Size   Used  Avail Use%  Mounted on{RESET}",
            "nebuff          8.0G   1.2G  6.8G  15%   /",
            "tmpfs           512M      0  512M   0%   /tmp",
            "devtmpfs        256M      0  256M   0%   /dev",
        ])

    def free(self) -> str:
        return "\n".join([
            f"{FG_BRIGHT_BLACK}              total        used        free      shared  buff/cache   available{RESET}",
            "Mem:           2048         312        1421          12         314        1736",
            "Swap:          1024           0        1024",
        ])

    def ps(self) -> str:
        return "\n".join([
            f"{FG_BRIGHT_BLACK}  PID TTY          TIME CMD{RESET}",
            "    1 ?        00:00:01 init",
            "   42 ?        00:00:00 ne-shell",
            "  137 ?        00:00:00 session_watcher",
        ])

    def uptime_str(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        now = datetime.datetime.utcnow().strftime("%H:%M:%S")
        return f" {now} up {h}:{m:02d}, 1 user, load average: 0.00, 0.00, 0.00"

sessions: dict[tuple[int | None, int, int | str], ShellSession] = {}

def get_session(guild_id: int | None, channel_id: int, user_id: int | str) -> ShellSession:
    key = (guild_id, channel_id, user_id)
    if key not in sessions:
        sessions[key] = ShellSession(user_id=user_id if isinstance(user_id, int) else 0, channel_id=channel_id)
    return sessions[key]

def save_session_data():
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clear database sessions first so that deleted persistent sessions are cleaned up
        cursor.execute("DELETE FROM sessions;")
        
        for k, s in sessions.items():
            if s.is_persistent:
                gid_str = str(k[0]) if k[0] is not None else "DM"
                key_str = f"{gid_str}:{k[1]}:{k[2]}"
                cursor.execute("""
                INSERT OR REPLACE INTO sessions (
                    session_id, user_id, channel_id, cwd, installed_packages, history, env, start_time, root, is_persistent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    key_str,
                    s.user_id,
                    s.channel_id,
                    json.dumps(s.cwd),
                    json.dumps(list(s.installed_packages)),
                    json.dumps(s.history),
                    json.dumps(s.env),
                    s.start_time.isoformat(),
                    json.dumps(s.root.to_dict()),
                    s.is_persistent
                ))
        conn.commit()
    except Exception as e:
        print(f"Error saving session data to DB: {e}")

def load_session_data():
    from db_service import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sessions;")
        rows = cursor.fetchall()
        for r in rows:
            s_dict = {
                "user_id": r["user_id"],
                "channel_id": r["channel_id"],
                "cwd": json.loads(r["cwd"]),
                "installed_packages": json.loads(r["installed_packages"]),
                "history": json.loads(r["history"]),
                "env": json.loads(r["env"]),
                "start_time": r["start_time"],
                "root": json.loads(r["root"]),
                "is_persistent": bool(r["is_persistent"])
            }
            s = ShellSession.from_dict(s_dict)
            key_str = r["session_id"]
            parts = key_str.split(":")
            if len(parts) == 3:
                gid = int(parts[0]) if parts[0] != "DM" else None
                cid = int(parts[1])
                uid = int(parts[2]) if parts[2].isdigit() else parts[2]
                sessions[(gid, cid, uid)] = s
            else:
                sessions[(None, s.channel_id, s.user_id)] = s
    except Exception as e:
        print(f"Error loading session data from DB: {e}")