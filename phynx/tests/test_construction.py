
from __future__ import absolute_import, with_statement

import posixpath
import time

import numpy as np
from numpy import testing as npt
from .utils import TestCase
from ..exceptions import H5Error
from .. import sorting

import phynx

class TestSorting(TestCase):

    def test_unrecognized_class(self):
        with self.file as f:
            a = f.create_group('a')
            a.attrs['class'] = np.array('Foo')
            assert isinstance(f['a'], phynx.Group)

    def test_unrecognized_nxclass(self):
        with self.file as f:
            a = f.create_group('a')
            a.attrs['nx_class'] = np.array('Foo')
            assert isinstance(f['a'], phynx.Group)

