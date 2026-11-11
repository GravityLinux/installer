# SPDX-License-Identifier: MIT

# tools/append-boot-logo.sh: magic, then 256x256 and 128x128 RGBA images.
LOGO_MAGIC = b"m1n1_logo_256128"
LOGO_SIZE = (256 * 256 + 128 * 128) * 4

def build(src, dest, vars):
    if isinstance(vars, (list, tuple)):
        vars = b"".join(i.encode("ascii") + b"\n" for i in vars) + b"\0\0\0\0"

    with open(src, "rb") as fd:
        m1n1_data = fd.read()

    # Align the complete boot object, including variables, for T8132 registration.
    boot_object = m1n1_data + vars
    boot_object += b"\0" * (-len(boot_object) % (64 * 1024))

    with open(dest, "wb") as fd:
        fd.write(boot_object)

def extract_vars(src):
    with open(src, "rb") as fd:
        m1n1_data = fd.read()

    try:
        tail = m1n1_data.split(b"STACKBOT", 1)[1]
        # The boot logo payload, if present, sits between m1n1 and its variables.
        if tail.startswith(LOGO_MAGIC):
            tail = tail[len(LOGO_MAGIC) + LOGO_SIZE:]
        vars = tail.split(b"\0")[0].decode("ascii")
    except Exception:
        return None

    return [i for i in vars.split("\n") if i]

def get_version(path):
    data = open(path, "rb").read()
    if b"##m1n1_ver##" in data:
        return data.split(b"##m1n1_ver##")[1].split(b"\0")[0].decode("ascii")
    else:
        return None
