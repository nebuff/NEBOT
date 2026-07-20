import datetime

class FSNode:
    def __init__(self, name: str, is_dir: bool = True, content: str = ""):
        self.name = name
        self.is_dir = is_dir
        self.children: dict[str, "FSNode"] = {}
        self.content = content
        self.modified = datetime.datetime.utcnow()

    def size(self) -> int:
        return len(self.content.encode())

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_dir": self.is_dir,
            "content": self.content,
            "modified": self.modified.isoformat(),
            "children": {k: v.to_dict() for k, v in self.children.items()}
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FSNode":
        node = cls(d["name"], is_dir=d["is_dir"], content=d["content"])
        if "modified" in d:
            node.modified = datetime.datetime.fromisoformat(d["modified"])
        if "children" in d:
            for k, v in d["children"].items():
                node.children[k] = cls.from_dict(v)
        return node

def create_default_root() -> FSNode:
    root = FSNode("/", is_dir=True)

    def add_dir(path: str):
        parts = [p for p in path.split("/") if p]
        node = root
        for part in parts:
            if part not in node.children:
                node.children[part] = FSNode(part, is_dir=True)
            node = node.children[part]

    def add_file(path: str, content: str = ""):
        parts = [p for p in path.split("/") if p]
        node = root
        for part in parts[:-1]:
            if part not in node.children:
                node.children[part] = FSNode(part, is_dir=True)
            node = node.children[part]
        leaf = parts[-1]
        node.children[leaf] = FSNode(leaf, is_dir=False, content=content)

    for d in ["bin","boot","dev","etc","home","lib","lib64",
              "media","mnt","opt","proc","root","run","sbin",
              "srv","sys","tmp","usr","var"]:
        add_dir(d)

    add_dir("home/user")
    add_dir("home/user/documents")
    add_dir("home/user/downloads")
    add_dir("mnt/nebuff")
    add_dir("opt/nebot")
    add_dir("usr/local/bin")
    add_dir("var/log")
    add_dir("etc/nebot")

    add_file("etc/nebot/nebot.conf",
             "# Ne-OS configuration\nversion=1.0\nshell=ne-shell\ntheme=dark\n")
    add_file("etc/hostname", "neb-host\n")
    add_file("home/user/readme.txt",
             "Welcome to Ne-OS!\nType your prefix with no command to see usage.\n")
    add_file("var/log/nebot.log",
             "[INFO] Ne-OS booted\n[INFO] ne-shell started\n")
    return root