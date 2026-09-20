import unittest
from unittest.mock import Mock

from diskutil import DiskUtil, Partition


def partition(name, kind, uuid):
    return Partition(name, 0, 1073741824, False, kind, uuid)


class PartitionSelectionTests(unittest.TestCase):
    def setup_disk(self, added):
        disk = DiskUtil()
        disk.disk_parts = {}
        existing = [partition('disk0s4', 'EFI', 'existing-efi'),
                    partition('disk0s7', 'Linux Filesystem', 'existing-linux')]
        disk.get_partitions = Mock(side_effect=[existing, existing + added])
        disk.action = Mock()
        disk.get_list = Mock()
        disk.get_partition_info = Mock(side_effect=lambda name, **kwargs:
                                       next(p for p in added if p.name == name))
        return disk

    def test_linux_alias_with_inserted_helper_and_existing_linux(self):
        wanted = partition('disk0s6', 'Linux Filesystem', 'new-linux')
        disk = self.setup_disk([partition('disk0s5', 'Apple_Boot', 'helper'), wanted])
        self.assertIs(disk.addPartition('disk0s4', '%Linux%', '%noformat%', 1073741824), wanted)
        disk.action.assert_called_once_with('addPartition', 'disk0s4', '%Linux%',
                                            '%noformat%', '1073741824', verbose=True)

    def test_other_types_and_linux_spelling(self):
        for requested, actual in [('apfs', 'Apple_APFS'), ('%EFI%', 'EFI'),
                                  ('%linux%', 'Linux'), ('%Linux Filesystem%', 'Linux Filesystem')]:
            with self.subTest(requested=requested):
                wanted = partition('disk0s5', actual, 'new')
                disk = self.setup_disk([wanted])
                self.assertIs(disk.addPartition('disk0s4', requested, 'name', 1073741824), wanted)

    def test_missing_or_ambiguous_candidates_fail_closed(self):
        for added in [[], [partition('disk0s5', 'Apple_Boot', 'helper')],
                      [partition('disk0s5', 'Linux Filesystem', 'existing-linux')],
                      [partition('disk0s5', 'Linux Filesystem', 'one'),
                       partition('disk0s6', 'Linux Filesystem', 'two')]]:
            with self.subTest(added=added):
                disk = self.setup_disk(added)
                with self.assertRaisesRegex(Exception, 'Could not uniquely identify'):
                    disk.addPartition('disk0s4', '%Linux%', '%noformat%', 1073741824)
                disk.get_partition_info.assert_not_called()
