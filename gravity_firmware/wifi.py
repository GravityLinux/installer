# SPDX-License-Identifier: MIT
import sys, os, os.path, pprint, statistics, logging
from .core import FWFile

log = logging.getLogger("gravity_firmware.wifi")

# Linux currently requests generic firmware names on the M4 Mac mini.  Keep
# these aliases explicit and machine-scoped: using a generic alias for the
# wrong board can load an incompatible NVRAM or transmit-power configuration.
MACHINE_ALIASES = {
    "j773g": {
        "brcm/brcmfmac4388c0-pcie.bin":
            "C-4388__s-C2/sakhalin.trx",
        "brcm/brcmfmac4388c0-pcie.txt":
            "C-4388__s-C2/P-sakhalin-X0_M-WLMT_V-u__m-4.9.txt",
        "brcm/brcmfmac4388c0-pcie.clm_blob":
            "C-4388__s-C2/sakhalin-X0.clmb",
        "brcm/brcmfmac4388c0-pcie.txcap_blob":
            "C-4388__s-C2/sakhalin-X0.txcb",
        "brcm/brcmfmac4388c0-pcie.sig":
            "C-4388__s-C2/sakhalin.sig",
    },
}

class FWNode(object):
    def __init__(self, this=None, leaves=None):
        if leaves is None:
            leaves = {}
        self.this = this
        self.leaves = leaves

    def __eq__(self, other):
        return self.this == other.this and self.leaves == other.leaves

    def __hash__(self):
        return hash((self.this, tuple(self.leaves.items())))

    def __repr__(self):
        return f"FWNode({self.this!r}, {self.leaves!r})"

    def print(self, depth=0, tag=""):
        print(f"{'  ' * depth} * {tag}: {self.this or ''} ({hash(self)})")
        for k, v in self.leaves.items():
            v.print(depth + 1, k)

class WiFiFWCollection(object):
    EXTMAP = {
        "trx": "bin",
        "txt": "txt",
        "clmb": "clm_blob",
        "txcb": "txcap_blob",
        "sig": "sig",
    }
    DIMS = ["C", "s", "P", "M", "V", "m", "A"]
    def __init__(self, source_path, machine=None):
        if machine is not None and machine not in MACHINE_ALIASES:
            raise ValueError(f"Unknown Wi-Fi firmware machine profile: {machine}")
        self.source_path = source_path
        self.machine = machine
        self.root = FWNode()
        if machine is None:
            self.load(source_path)
            self.prune()

    def load(self, source_path):
        for dirpath, dirnames, filenames in os.walk(source_path):
            if "perf" in dirnames:
                dirnames.remove("perf")
            if "assert" in dirnames:
                dirnames.remove("assert")
            subpath = os.path.relpath(dirpath, source_path)
            for name in sorted(filenames):
                if not any(name.endswith("." + i) for i in self.EXTMAP):
                    continue
                # macOS 14.6/14.8 contains {java,sumatra}_gen* files, possible
                # for generic data. It's not clear how they are used so skip
                # them for now
                if "_gen" in name:
                    continue
                path = os.path.join(dirpath, name)
                relpath = os.path.join(subpath, name)
                if not name.endswith(".txt"):
                    name = "P-" + name
                idpath, ext = os.path.join(subpath, name).rsplit(".", 1)
                props = {}
                for i in idpath.replace("/", "_").split("_"):
                    if not i:
                        continue
                    k, v = i.split("-", 1)
                    if k == "P" and "-" in v:
                        plat, ant = v.split("-", 1)
                        props["P"] = plat
                        props["A"] = ant
                    else:
                        props[k] = v
                ident = [ext]
                for dim in self.DIMS:
                    if dim in props:
                        ident.append(props.pop(dim))
                assert not props

                node = self.root
                for k in ident:
                    node = node.leaves.setdefault(k, FWNode())
                with open(path, "rb") as fd:
                    data = fd.read()

                if name.endswith(".txt"):
                    data = self.process_nvram(data)

                node.this = FWFile(relpath, data)

    def prune(self, node=None, depth=0):
        if node is None:
            node = self.root

        for i in node.leaves.values():
            self.prune(i, depth + 1)

        if node.this is None and node.leaves and depth > 3:
            first = next(iter(node.leaves.values()))
            if all(i == first for i in node.leaves.values()):
                node.this = first.this

        for i in node.leaves.values():
            if not i.this or not node.this:
                break
            if i.this != node.this:
                break
        else:
            node.leaves = {}

    def _walk_files(self, node, ident):
        if node.this is not None:
            yield ident, node.this
        for k, subnode in node.leaves.items():
            yield from self._walk_files(subnode, ident + [k])

    def files(self):
        if self.machine is not None:
            for name, source in MACHINE_ALIASES[self.machine].items():
                path = os.path.join(self.source_path, source)
                try:
                    with open(path, "rb") as fd:
                        data = fd.read()
                except FileNotFoundError:
                    raise FileNotFoundError(
                        f"Missing Wi-Fi firmware for {self.machine}: {source}"
                    ) from None

                if name.endswith(".txt"):
                    data = self.process_nvram(data)

                yield name, FWFile(source, data)
            return

        for ident, fwfile in self._walk_files(self.root, []):
            (ext, chip, rev), rest = ident[:3], ident[3:]
            rev = rev.lower()
            ext = self.EXTMAP[ext]

            if rest:
                rest = "," + "-".join(rest)
            else:
                rest = ""
            filename = f"brcm/brcmfmac{chip}{rev}-pcie.apple{rest}.{ext}"

            yield filename, fwfile

    def process_nvram(self, data):
        data = data.decode("ascii")
        keys = {}
        lines = []
        for line in data.split("\n"):
            if not line:
                continue
            key, value = line.split("=", 1)
            keys[key] = value
            # Clean up spurious whitespace that Linux does not like
            lines.append(f"{key.strip()}={value}\n")

        return "".join(lines).encode("ascii")

    def print(self):
        self.root.print()

if __name__ == "__main__":
    col = WiFiFWCollection(sys.argv[1])
    if len(sys.argv) > 2:
        from .core import FWPackage

        pkg = FWPackage(sys.argv[2])
        pkg.add_files(sorted(col.files()))
        pkg.close()

        for i in pkg.manifest:
            print(i)
    else:
        for name, fwfile in col.files():
            if isinstance(fwfile, str):
                print(name, "->", fwfile)
            else:
                print(name, f"({len(fwfile.data)} bytes)")
