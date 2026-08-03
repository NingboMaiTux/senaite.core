# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.CORE.
#
# SENAITE.CORE is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright 2018-2025 by it's authors.
# Some rights reserved, see README and LICENSE.

import imp
import os
import sys
import types
import unittest


class TestWorksheetPermissionsSubscriber(unittest.TestCase):
    """Worksheet 权限订阅器回归测试"""

    def setUp(self):
        self._added_modules = {}
        self.module = self._load_module_under_test()

    def tearDown(self):
        # 中文注释：测试结束后恢复临时注入的模块，避免污染其他测试。
        for name, original in self._added_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def _install_module(self, name, module):
        self._added_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _load_module_under_test(self):
        fake_api = types.ModuleType("bika.lims.api")
        fake_api.get_portal = lambda: type("DummyPortal", (), {})()

        fake_bika = types.ModuleType("bika")
        fake_lims = types.ModuleType("bika.lims")
        fake_lims.api = fake_api
        fake_bika.lims = fake_lims

        fake_permissions = types.ModuleType("senaite.core.permissions")
        fake_permissions.AddWorksheet = "AddWorksheet"
        fake_permissions.EditWorksheet = "EditWorksheet"
        fake_permissions.ManageWorksheets = "ManageWorksheets"

        fake_senaite = types.ModuleType("senaite")
        fake_core = types.ModuleType("senaite.core")
        fake_core.permissions = fake_permissions
        fake_senaite.core = fake_core

        self._install_module("bika", fake_bika)
        self._install_module("bika.lims", fake_lims)
        self._install_module("bika.lims.api", fake_api)
        self._install_module("senaite", fake_senaite)
        self._install_module("senaite.core", fake_core)
        self._install_module("senaite.core.permissions", fake_permissions)

        module_name = "worksheet_permissions_subscriber_under_test"
        self._added_modules[module_name] = sys.modules.get(module_name)
        module_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "bika", "lims", "subscribers", "setup.py"))
        return imp.load_source(module_name, module_path)

    def test_skip_permission_update_when_portal_has_no_worksheets(self):
        """安装早期 portal 没有 worksheets 容器时不应抛异常"""
        class DummySetup(object):
            def getRestrictWorksheetUsersAccess(self):
                return True

            def getRestrictWorksheetManagement(self):
                return True

            def setRestrictWorksheetManagement(self, value):
                # 中文注释：当前用例只验证缺少 worksheets 容器时不会崩溃，
                # 不需要真正持久化这个值。
                return value

        self.module.update_worksheet_manage_permissions(DummySetup())


def test_suite():
    from unittest import TestSuite
    from unittest import makeSuite

    suite = TestSuite()
    suite.addTest(makeSuite(TestWorksheetPermissionsSubscriber))
    return suite
