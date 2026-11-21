# Apple Silicon: repartitioning and Linux partition encryption (fc44 runbook)

Distilled from a validated end-to-end migration on an Apple Silicon
Mac mini (M4-class) running Gravity Linux release 44 (Fedora 44
based): dual-boot reclaim to single-boot, LUKS2-encrypted root and
data, with the boot chain kept intact at every stage. Intended as reference for installer
integration (`--encrypt`, guided repartition) and as a CLI walkthrough
for users doing it manually.

## Apple Silicon disk facts that constrain everything

- The internal disk uses GPT with several Apple-firmware partitions
  that must never be modified, deleted, or have their numbers/UUIDs
  changed casually:
  - `Apple_APFS_ISC` (type `AF0B`, ~500M) — iBoot system container.
  - `Apple_APFS_Recovery` (type `AF0C`, ~5G) — recoveryOS/1TR: boot
    picker's Options, Disk Utility, `bless`, `bputil`, `kmutil`,
    macOS reinstall, DFU revive. It stays functional even if macOS
    is deleted.
  - The Linux boot chain's APFS stub container (type `AF0A`, ~2-3G)
    created by the installer — holds the personalized boot object
    iBoot loads. Deleting it makes the system unbootable until the
    1TR re-registration (`bless` + `kmutil configure-boot`) is redone.
- Machines cannot boot from external media; the boot picker only
  enumerates internal containers. A "Linux partition" for the rootfs
  is a normal GPT entry, but boot always starts from the APFS stub.
- GPT partition numbers are table slots, not physical positions. A
  partition can be relocated to a different physical offset while
  keeping its number, PARTUUID, and type code — this keeps all boot
  references (`(hd0,gpt5)` in GRUB, BLS paths) valid.
- macOS identifiers (`disk0sN`) and Linux ones (`nvme0n1pN`) do not
  correspond; sizes and type codes are the reliable identifiers.
- APFS containers on Linux are read-only via apfs-fuse; FileVault
  volumes are unreadable by design (keys in the Secure Enclave
  escrow). Encryption questions on the Linux side are therefore
  solved with LUKS, not with anything APFS.

## Repartition

Always start from a full layout listing and match partitions by size
and type, never by order:

```bash
lsblk -o NAME,SIZE,FSTYPE,LABEL /dev/nvme0n1
sudo sgdisk -p /dev/nvme0n1
```

### Shrinking macOS to make room (from macOS)

```bash
diskutil list
diskutil apfs resizeContainer disk0s2 175g
diskutil addPartition disk0s2 APFS development 20g
```

`resizeContainer` takes the container's NEW total size. Container
names (`disk3`) and slice identifiers (`disk0s2`) do not align; re-run
`diskutil list` between commands.

### Deleting the macOS container from Linux (post-migration reclaim)

```bash
sudo dnf install gdisk
sudo sgdisk --delete=2 /dev/nvme0n1
sudo sgdisk --largest-new=2 --typecode=2:8300 /dev/nvme0n1
sudo partprobe /dev/nvme0n1
sudo wipefs -a /dev/nvme0n1p2
sudo dd if=/dev/zero of=/dev/nvme0n1p2 bs=1M count=16 status=none
sudo partprobe /dev/nvme0n1
```

`--largest-new` fills the biggest free gap. The zero-wipe clears stale
APFS signatures (APFS keeps superblock copies at several offsets).

### Relocating partitions to consolidate free space

When freed space is not adjacent (typical case: the old root sits
between `/boot` and Recovery), partitions can be moved instead of
leaving stranded space:

1. Save the GPT and capture identity GUIDs:

```bash
sudo sgdisk --backup=/root/gpt-backup.bin /dev/nvme0n1
for n in 2 3 4 5; do sudo sgdisk -i $n /dev/nvme0n1; done
```

2. Copy partition contents while unmounted:

```bash
sudo umount /boot/efi /boot
sudo dd if=/dev/nvme0n1p3 of=/root/p3.img bs=1M status=none
sudo dd if=/dev/nvme0n1p4 of=/root/p4.img bs=1M status=none
sudo dd if=/dev/nvme0n1p5 of=/root/p5.img bs=1M status=none
```

3. Delete and recreate entries at new offsets with the SAME slot
   numbers, PARTUUIDs, and type codes (compute start/end from
   `sgdisk -p` output; new lengths must equal original lengths):

```bash
sudo sgdisk --delete=3 --delete=4 --delete=5 /dev/nvme0n1
sudo sgdisk --new=3:<start3>:<end3> --typecode=3:af0a --partition-guid=3:$UUID3 /dev/nvme0n1
sudo sgdisk --new=4:<start4>:<end4> --typecode=4:ef00 --partition-guid=4:$UUID4 /dev/nvme0n1
sudo sgdisk --new=5:<start5>:<end5> --partition-guid=5:$UUID5 /dev/nvme0n1
sudo partprobe /dev/nvme0n1
sudo dd if=/root/p3.img of=/dev/nvme0n1p3 bs=1M status=none
sudo dd if=/root/p4.img of=/dev/nvme0n1p4 bs=1M status=none
sudo dd if=/root/p5.img of=/dev/nvme0n1p5 bs=1M status=none
sudo partprobe /dev/nvme0n1
sudo fsck -f /dev/nvme0n1p5
```

Growing a partition is the same pattern: `--delete` then `--new`
with a bigger end, same start, same GUID.

## Encryption: LUKS2 + btrfs

Boot chain constraint: the APFS stub, EFI, and `/boot` stay
unencrypted (required — GRUB and the stub run before any unlock).
Encrypt root and data only.

### New data partition

```bash
sudo cryptsetup luksFormat --type luks2 /dev/nvme0n1pN
sudo cryptsetup open /dev/nvme0n1pN name
sudo mkfs.btrfs -L name /dev/mapper/name
sudo mkdir /data && sudo mount /dev/mapper/name /data
echo "name UUID=$(sudo blkid -s UUID -o value /dev/nvme0n1pN) none luks,discard" | sudo tee -a /etc/crypttab
echo "/dev/mapper/name /data btrfs defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo dracut --force --regenerate-all
```

`luks,discard` in crypttab makes fstrim/discard work through dm-crypt;
without it `fstrim` fails with "the discard operation is not
supported". Enable on an already-open mapper without reboot:

```bash
sudo cryptsetup refresh --allow-discards name
```

Forgotten LUKS passphrases are unrecoverable — no escrow exists.

### Migrating an existing install into encryption (no reinstall)

An existing filesystem cannot be wrapped in place; copy it into a new
LUKS container and boot both until the encrypted one is proven:

```bash
sudo cryptsetup luksFormat --type luks2 /dev/nvme0n1pX
sudo cryptsetup open /dev/nvme0n1pX gravity
sudo mkfs.btrfs -L gravity /dev/mapper/gravity
sudo mount -o subvol=root /dev/mapper/gravity /mnt/newroot
sudo mount -o subvol=home /dev/mapper/gravity /mnt/newroot/home
sudo rsync -aHAXx / /mnt/newroot/ --exclude=proc --exclude=sys --exclude=dev --exclude=run --exclude=mnt --exclude=tmp --exclude=boot --exclude=home
sudo rsync -aHAXx /home/ /mnt/newroot/home/
```

The copy needs replacement mountpoints that rsync excluded:

```bash
sudo mkdir -p /mnt/newroot/{dev,proc,sys,run,tmp,var/tmp}
```

Chroot, re-point fstab at the mapper, and regenerate an initramfs with
LUKS support into a NEW filename (never overwrite the working one):

```bash
for d in dev proc sys run; do sudo mount --bind /$d /mnt/newroot/$d; done
sudo mount /dev/nvme0n1p5 /mnt/newroot/boot
sudo mount /dev/nvme0n1p4 /mnt/newroot/boot/efi
sudo chroot /mnt/newroot
LUKS_UUID=$(blkid -s UUID -o value /dev/nvme0n1pX)
sed -i "s|$(awk '$2==\"/\" {print $1}' /etc/fstab)|/dev/mapper/gravity|g" /etc/fstab
grep -q '^gravity ' /etc/crypttab || echo "gravity UUID=$LUKS_UUID none luks,discard" >> /etc/crypttab
KVER=$(basename /boot/vmlinuz-$(uname -r) | sed 's/vmlinuz-//')
dracut --force /boot/initramfs-$KVER-luks.img $KVER
```

Add a BLS entry copied from the working one, pointing at the LUKS
initramfs and root:

```bash
SRC=$(grep -l "vmlinuz-$KVER" /boot/loader/entries/*.conf | head -1)
cp "$SRC" /boot/loader/entries/gravity-luks.conf
sed -i "s|^title \(.*\)|title \1 (LUKS)|" /boot/loader/entries/gravity-luks.conf
sed -i "s|^initrd .*|initrd /initramfs-$KVER-luks.img|" /boot/loader/entries/gravity-luks.conf
sed -i "s|root=UUID=[^ ]*|root=/dev/mapper/gravity|" /boot/loader/entries/gravity-luks.conf
sed -i "s|\(options .*\)|\1 rd.luks.uuid=$LUKS_UUID|" /boot/loader/entries/gravity-luks.conf
```

Boot-selection notes validated on fc44 images: BLS entries sort by their
`version` field (newest first); a `version` suffix bump makes an entry
both the top of the menu and the fallback default. `grubby --set-default`
does not accept a BLS conf path; select defaults via
`grub2-editenv /boot/grub2/grubenv set saved_entry=<bls-stem-or-title>`.
Menu auto-hiding is driven by `menu_auto_hide` in the grubenv;
`grub2-editenv ... unset menu_auto_hide` plus `GRUB_TIMEOUT_STYLE=menu`
in `/etc/default/grub` shows the menu.

### Deleting the old root and absorbing non-adjacent space

Two options for the freed gap:

a) Second encrypted device appended to the same btrfs (no geometry
   work; single-fs semantics):

```bash
sudo cryptsetup luksFormat --type luks2 /dev/nvme0n1p6
sudo dd if=/dev/urandom of=/etc/luks-second.key bs=4096 count=1 status=none
sudo chmod 600 /etc/luks-second.key
sudo cryptsetup luksAddKey /dev/nvme0n1p6 /etc/luks-second.key
sudo cryptsetup open --key-file /etc/luks-second.key /dev/nvme0n1p6 second
sudo btrfs device add /dev/mapper/second /
echo "second UUID=$(sudo blkid -s UUID -o value /dev/nvme0n1p6) /etc/luks-second.key luks" | sudo tee -a /etc/crypttab
sudo dracut --force --regenerate-all
```

A keyfile on the encrypted root avoids a second passphrase at boot.

b) Physical relocation of the small boot-chain partitions (see above)
   to make the freed space contiguous, then grow:

```bash
sudo sgdisk --delete=2 /dev/nvme0n1
sudo sgdisk --new=2:<old-start>:<new-end> --partition-guid=2:$UUID2 /dev/nvme0n1
sudo partprobe /dev/nvme0n1
sudo cryptsetup resize gravity
sudo btrfs filesystem resize max /
sudo fstrim -v /
```

Stale plaintext from the old partition in the absorbed region is
discarded via `fstrim` through the encrypted mapping (blkdiscard fails
with EBUSY on a mounted mapper).

## Fedora 44 (Anaconda) reference behavior

Fedora 44's own installer is a useful reference despite being GUI-based:

- It offers a single high-level choice ("Encrypt my data" on the
  storage screen); everything below /boot and /boot/efi gets
  encrypted. One template-level toggle, not per-partition granularity.
- The default layout keeps the EFI System Partition and /boot
  unencrypted and wraps the btrfs root in LUKS2; the Web UI actively
  blocks an encrypted /boot without a workaround, matching the
  Apple Silicon constraint that the stub, ESP, and /boot stay
  plaintext for the boot chain.
- Defaults applied at install time: LUKS2, aes-xts-plain64, 512-bit
  key, Argon2id key derivation. Build-side encrypted root images
  should match these.
- Automation is first-class: kickstart `autopart --encrypted
  --passphrase --luks-version=luks2` covers unattended installs. A
  text-mode gap in Anaconda (no interactive encryption option) was
  long-standing; CLI flows should treat the encrypted variant as a
  first-class choice, not an expert-only path.
- Interactive installs use passphrases only; keyfiles come later from
  the running system, which matches the post-install migration flow
  in this document.

## Verification patterns

```bash
cat /proc/cmdline
df -h /
sudo btrfs filesystem show /
sudo cryptsetup status gravity
sudo fstrim -v /
```

Rollback at every stage: the old boot entry and root remain untouched
until the encrypted path is proven over several reboots; the GPT
backup restores with `sgdisk --load=<file>`; content backups
(`dd` images) restore by re-copying.

## Installer integration notes (fc44)

The CLI installer runs on macOS and installs prebuilt partition images
raw onto `diskutil`-created partitions, so it cannot run cryptsetup at
install time. The two clean integrations are:

- Build side: ship an OS template whose Root partition uses type
  `luks` and a prebuilt root image containing the LUKS container, the
  btrfs filesystem, and bootloader entries already carrying the
  image's `rd.luks.uuid`. The installer writes the image raw as it
  does today; no crypto tooling is needed on macOS.
- Installer side (this change): accept `"type": "luks"` in OS
  templates and create the root partition with the Linux LUKS type
  GUID so the partition table describes the encrypted container.

For systems already installed without encryption, the post-install
migration procedure above covers converting to LUKS from the running
Linux system.

`luks,discard` should remain the recommendation for generated
crypttab lines (silent fstrim failures are a common first-day
surprise otherwise); document that a keyfile under `/etc` protects a
migrated data volume only when the root filesystem is itself
encrypted.
