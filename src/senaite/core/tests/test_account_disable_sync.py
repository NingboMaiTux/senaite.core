# -*- coding: utf-8 -*-

import imp
import os
import sys
import types
import unittest


class DummyLogger(object):
    """最小 logger stub"""

    def info(self, message):
        return message

    def warn(self, message):
        return message


class DummySheet(object):
    """模拟可写属性 sheet"""

    def __init__(self):
        self.calls = []

    def hasProperty(self, key):
        return True

    def setProperty(self, user, key, value):
        self.calls.append((user, key, value))


class DummyPlugins(object):
    """模拟 PAS 插件列表"""

    def __init__(self, sheet):
        self.sheet = sheet

    def listPlugins(self, iface):
        return [("dummy", DummyPlugin(self.sheet))]


class DummyPlugin(object):
    """模拟属性插件"""

    def __init__(self, sheet):
        self.sheet = sheet

    def getPropertiesForUser(self, user):
        return self.sheet


class DummyAclUsers(object):
    """模拟 acl_users"""

    def __init__(self, sheet):
        self.plugins = DummyPlugins(sheet)


class DummyMemberDataTool(object):
    """模拟 portal_memberdata 工具"""

    def __init__(self, sheet):
        self._properties = {}
        self.acl_users = DummyAclUsers(sheet)

    def hasProperty(self, key):
        return key in self._properties

    def manage_addProperty(self, key, value, field_type):
        self._properties[key] = (value, field_type)


class DummyUser(object):
    """模拟用户对象"""

    def __init__(self, tool):
        self._tool = tool
        self.member_properties_calls = []
        self.properties_calls = []

    def setMemberProperties(self, mapping):
        self.member_properties_calls.append(mapping)

    def setProperties(self, **kwargs):
        self.properties_calls.append(kwargs)


class TestAccountDisableSync(unittest.TestCase):
    """账号禁用同步回归测试"""

    def setUp(self):
        self._added_modules = {}
        self.module = self._load_module_under_test()

    def tearDown(self):
        # 中文注释：恢复测试过程中临时注入的模块，避免污染其他用例。
        for name, original in self._added_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def _install_module(self, name, module):
        self._added_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _load_module_under_test(self):
        fake_plone_api = types.ModuleType("plone.api")
        fake_plone_api.user = type("DummyUserApi", (), {
            "get": staticmethod(lambda **kwargs: None)
        })()

        fake_plone = types.ModuleType("plone")
        fake_plone.api = fake_plone_api

        fake_pas = types.ModuleType(
            "Products.PluggableAuthService.interfaces.plugins")
        fake_pas.IPropertiesPlugin = object()

        fake_products = types.ModuleType("Products")
        fake_products_pas = types.ModuleType("Products.PluggableAuthService")
        fake_products_pas_interfaces = types.ModuleType(
            "Products.PluggableAuthService.interfaces")

        fake_senaite = types.ModuleType("senaite")
        fake_core = types.ModuleType("senaite.core")
        fake_core.logger = DummyLogger()
        fake_senaite.core = fake_core

        self._install_module("plone", fake_plone)
        self._install_module("plone.api", fake_plone_api)
        self._install_module("Products", fake_products)
        self._install_module(
            "Products.PluggableAuthService", fake_products_pas)
        self._install_module(
            "Products.PluggableAuthService.interfaces",
            fake_products_pas_interfaces)
        self._install_module(
            "Products.PluggableAuthService.interfaces.plugins",
            fake_pas)
        self._install_module("senaite", fake_senaite)
        self._install_module("senaite.core", fake_core)

        module_name = "account_disable_sync_under_test"
        self._added_modules[module_name] = sys.modules.get(module_name)
        module_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "browser", "user", "account_status.py"))
        return imp.load_source(module_name, module_path)

    def test_set_user_property_updates_fallback_interfaces(self):
        """写入账号禁用属性时应同步更新兼容接口"""
        sheet = DummySheet()
        tool = DummyMemberDataTool(sheet)
        user = DummyUser(tool)

        result = self.module._set_user_property(user, "account_disabled", "1")

        self.assertTrue(result)
        self.assertEqual(len(sheet.calls), 1)
        self.assertEqual(
            user.member_properties_calls,
            [{"account_disabled": "1"}])
        self.assertEqual(
            user.properties_calls,
            [{"account_disabled": "1"}])

    def test_disable_checkbox_should_not_be_locked_by_delete_permission(self):
        """禁用勾选框不应再受删除权限控制"""
        template_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "browser", "usergroup", "templates",
            "usergroups_usersoverview.pt"))

        with open(template_path, "r") as handle:
            template = handle.read()

        self.assertNotIn(
            "disabled python:user['can_delete'] and default or 'disabled'",
            template)


def test_suite():
    from unittest import TestSuite
    from unittest import makeSuite

    suite = TestSuite()
    suite.addTest(makeSuite(TestAccountDisableSync))
    return suite
