from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import bootstrap


class SetupTests(unittest.TestCase):
    def test_existing_changed_checkout_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'external/stonkfly').mkdir(parents=True)
            with patch.object(bootstrap, 'ROOT', root), patch.object(bootstrap.shutil, 'which', return_value='git'), \
                    patch.object(bootstrap.subprocess, 'check_output', side_effect=['pinned\n', ' M neural.py\n']), \
                    patch.object(bootstrap, 'run') as mutate:
                with self.assertRaisesRegex(RuntimeError, 'clean pinned revision'):
                    bootstrap.checkout('stonkfly', {'commit': 'pinned', 'url': 'https://github.com/nftechie/stonkfly.git'})
                mutate.assert_not_called()

    def test_existing_wrong_revision_is_rejected_without_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'external/FastFly').mkdir(parents=True)
            with patch.object(bootstrap, 'ROOT', root), patch.object(bootstrap.shutil, 'which', return_value='git'), \
                    patch.object(bootstrap.subprocess, 'check_output', side_effect=['different\n', '']), \
                    patch.object(bootstrap, 'run') as mutate:
                with self.assertRaisesRegex(RuntimeError, 'clean pinned revision'):
                    bootstrap.checkout('FastFly', {'commit': 'pinned', 'url': 'https://github.com/eonfathom/FastFly.git'})
                mutate.assert_not_called()
