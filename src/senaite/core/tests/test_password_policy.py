# -*- coding: utf-8 -*-
"""用户密码规则更新包回归测试

对应 `E:\更新包\用户密码规则更新包`（2026-06-12）落库到 core 的功能：
管理员可在控制面板配置最短密码长度与必需的字符类别，改密与新建用户时生效。

全部用例不依赖 Plone / Zope：视图与服务通过桩模块加载，registry 用
DummyRegistry 顶替（`registerInterface` 建记录、`forInterface` 读值），
这样 `validate()` 的规则逻辑是真的被测到了，而不是只测桩。
"""

import imp
import os
import sys
import types
import unittest


PACKAGE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir))
BROWSER_USER_DIR = os.path.join(PACKAGE_DIR, "browser", "user")

POLICY_SOURCE = os.path.join(BROWSER_USER_DIR, "passwordpolicy.py")
SERVICE_SOURCE = os.path.join(BROWSER_USER_DIR, "passwordpolicy_service.py")
PANEL_SOURCE = os.path.join(BROWSER_USER_DIR, "passwordpanel.py")
REGISTER_SOURCE = os.path.join(BROWSER_USER_DIR, "register.py")
CONFIGURE_ZCML = os.path.join(BROWSER_USER_DIR, "configure.zcml")
TEMPLATE_SOURCE = os.path.join(
    BROWSER_USER_DIR, "templates", "password-policy-controlpanel.pt")
CONTROL_PANEL_XML = os.path.join(
    PACKAGE_DIR, "profiles", "default", "controlpanel.xml")
METADATA_XML = os.path.join(PACKAGE_DIR, "profiles", "default", "metadata.xml")
UPGRADE_ZCML = os.path.join(PACKAGE_DIR, "upgrade", "v02_07_000.zcml")


REGISTRY_PREFIX = "senaite.core.password_policy"

#: 接口里声明的字段与默认值（与 passwordpolicy.IPasswordPolicySettings 对齐）
DEFAULT_SETTINGS = {
    "enabled": True,
    "min_length": 8,
    "require_uppercase": False,
    "require_lowercase": False,
    "require_digit": False,
    "require_special": False,
}


class DummyLogger(object):
    """最小 logger stub"""

    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        return message


class DummySettings(object):
    """模拟 registry.forInterface() 返回的设置命名空间"""

    def __init__(self, **kw):
        values = dict(DEFAULT_SETTINGS)
        values.update(kw)
        for key, value in values.items():
            setattr(self, key, value)


class DummyRecord(object):
    """模拟 plone.registry 的 records[name]"""

    def __init__(self, value):
        self.value = value


class DummyRegistry(object):
    """模拟 plone.registry.interfaces.IRegistry

    `registerInterface` 只记录调用；`reset()` 按传入值重建设置与 records，
    等价于真实 registry 注册过该接口之后的状态。
    """

    def __init__(self, **settings):
        self.registered = []
        self.reset(**settings)

    def reset(self, **settings):
        self.settings = DummySettings(**settings)
        self.records = dict(
            ("%s.%s" % (REGISTRY_PREFIX, key),
             DummyRecord(getattr(self.settings, key)))
            for key in DEFAULT_SETTINGS)

    def registerInterface(self, interface, prefix=None):
        self.registered.append(prefix)

    def forInterface(self, interface, prefix=None, check=True):
        return self.settings


class DummyResponse(object):
    def __init__(self):
        self.redirects = []

    def redirect(self, url):
        self.redirects.append(url)
        return url


class DummyRequest(dict):
    """模拟 request：form 取值走 dict，另有 response"""

    def __init__(self, **kw):
        dict.__init__(self, **kw)
        self.response = DummyResponse()


def read_source(path):
    with open(path, "r") as handle:
        return handle.read()


class PolicyModules(object):
    """把 passwordpolicy / passwordpolicy_service 用桩加载进来"""

    def __init__(self):
        self.registry = DummyRegistry()
        self.logger = DummyLogger()
        self._saved = {}
        self.policy = None
        self.service_module = None
        self._install()

    def _save(self, name):
        self._saved[name] = sys.modules.get(name)

    def _module(self, name, **attrs):
        """创建并注册一个桩模块"""
        self._save(name)
        module = types.ModuleType(name)
        module.__path__ = []
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        return module

    def _install(self):
        # bika.lims.api
        api = types.ModuleType("bika.lims.api")
        api.get_url = lambda context: "http://nohost/plone"
        api.get_tool = lambda name: None
        self._module("bika")
        lims = self._module("bika.lims")
        self._save("bika.lims.api")
        sys.modules["bika.lims.api"] = api
        lims.api = api

        # plone.registry.interfaces.IRegistry
        self._module("plone")
        registry_pkg = self._module("plone.registry")
        registry_ifaces = self._module(
            "plone.registry.interfaces", IRegistry=object)
        registry_pkg.interfaces = registry_ifaces

        # Products.Five.browser(.pagetemplatefile)
        self._module("Products")
        five = self._module("Products.Five")
        five_browser = self._module("Products.Five.browser", BrowserView=object)
        five.browser = five_browser
        five_ptf = self._module(
            "Products.Five.browser.pagetemplatefile",
            ViewPageTemplateFile=lambda filename: filename)
        five_browser.pagetemplatefile = five_ptf

        # senaite.core.logger
        self._module("senaite")
        core = self._module("senaite.core", logger=self.logger)
        core.__path__ = []
        core_browser = self._module("senaite.core.browser")
        core_browser.__path__ = []
        core_user = self._module("senaite.core.browser.user")
        core_user.__path__ = []
        core.browser = core_browser
        core_browser.user = core_user

        # zope.schema / zope.component / zope.interface
        zope_pkg = self._module("zope")
        schema_module = self._module(
            "zope.schema", Bool=self._fake_field, Int=self._fake_field)
        component = self._module(
            "zope.component",
            getUtility=lambda interface: self.registry)
        interface_module = self._module("zope.interface", Interface=object)
        zope_pkg.schema = schema_module
        zope_pkg.component = component
        zope_pkg.interface = interface_module

        # 真的 passwordpolicy / passwordpolicy_service
        self._save("senaite.core.browser.user.passwordpolicy")
        self.policy = imp.load_source(
            "senaite.core.browser.user.passwordpolicy", POLICY_SOURCE)

        self._save("senaite.core.browser.user.passwordpolicy_service")
        self.service_module = imp.load_source(
            "senaite.core.browser.user.passwordpolicy_service", SERVICE_SOURCE)

    @staticmethod
    def _fake_field(**kw):
        return dict(kw)

    def make_service(self):
        return self.service_module.PasswordPolicyService()

    def make_view(self, **form):
        cls = self.policy.PasswordPolicyControlPanelView
        view = cls.__new__(cls)
        view.context = object()
        view.request = DummyRequest(**form)
        view.index = lambda: "rendered"
        view.messages = []
        view._show_message = lambda message, level="info": \
            view.messages.append((level, message))
        return view

    def uninstall(self):
        for name, original in self._saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class PolicyTestCase(unittest.TestCase):
    """公共装配：每个用例一套干净的桩"""

    def setUp(self):
        self.modules = PolicyModules()
        self.addCleanup(self.modules.uninstall)
        self.service = self.modules.make_service()

    def validate(self, password, **settings):
        if settings:
            self.modules.registry.reset(**settings)
        return self.service.validate(password)


class TestPasswordPolicyRules(PolicyTestCase):
    """密码复杂度规则的判定逻辑"""

    def test_min_length_is_enforced(self):
        """短于配置长度的密码必须被拒"""
        errors = self.validate("Ab1", min_length=8)

        self.assertEqual(len(errors), 1)
        self.assertIn("at least 8 characters", errors[0])

    def test_min_length_boundary_passes(self):
        """正好等于配置长度要放行"""
        self.assertEqual(self.validate("Abcdef12", min_length=8), [])

    def test_disabled_policy_accepts_anything(self):
        """关闭后不再做任何校验，长度规则也一并失效"""
        errors = self.validate("a", enabled=False, min_length=8)

        self.assertEqual(errors, [])

    def test_character_class_rules(self):
        """四个字符类别开关各自独立生效"""
        self.assertEqual(
            self.validate("abcdefgh", require_uppercase=True),
            ["Password must contain at least one uppercase letter."])
        self.assertEqual(
            self.validate("ABCDEFGH", require_lowercase=True),
            ["Password must contain at least one lowercase letter."])
        self.assertEqual(
            self.validate("abcdefgh", require_digit=True),
            ["Password must contain at least one digit."])
        self.assertEqual(
            self.validate("abcdefgh", require_special=True),
            ["Password must contain at least one special character."])

    def test_satisfied_rules_report_nothing(self):
        """全部满足时返回空列表"""
        errors = self.validate(
            "Abcdef1!", min_length=8, require_uppercase=True,
            require_lowercase=True, require_digit=True, require_special=True)

        self.assertEqual(errors, [])

    def test_multiple_violations_accumulate(self):
        """多条不满足要一次性全部报出来，而不是只报第一条"""
        errors = self.validate(
            "ab", min_length=8, require_uppercase=True, require_digit=True)

        self.assertEqual(len(errors), 3)
        self.assertIn("at least 8 characters", errors[0])
        self.assertIn("uppercase", errors[1])
        self.assertIn("digit", errors[2])

    def test_special_rule_accepts_non_ascii(self):
        """按现在的实现，非 ASCII 字符也算"特殊字符"

        规则是 `[^A-Za-z0-9]`，中文/全角符号都会命中。这里把行为钉住：
        如果哪天要改成"只认键盘符号"，这条用例会先红。
        """
        password = u"密码" * 4  # 8 个字符，刚好过长度规则

        self.assertEqual(self.validate(password, require_special=True), [])

    def test_empty_password_is_not_accepted_by_length_rule(self):
        """空密码由长度规则兜住（调用方只对有值的密码调用 validate）"""
        self.assertEqual(len(self.validate("", min_length=1)), 1)

    def test_rules_summary_lists_enabled_rules(self):
        """改密/注册页的提示文案要跟着配置走"""
        self.modules.registry.reset(
            min_length=10, require_digit=True, require_special=True)
        summary = self.service.rules_summary()

        self.assertTrue(summary.startswith("Password must "))
        self.assertIn("at least 10 characters", summary)
        self.assertIn("at least one digit", summary)
        self.assertIn("at least one special character", summary)
        self.assertNotIn("uppercase", summary)

    def test_rules_summary_when_disabled(self):
        """关闭时提示文案要明说已关闭"""
        self.modules.registry.reset(enabled=False)

        self.assertEqual(self.service.rules_summary(),
                         "Custom password policy is disabled.")

    def test_service_registers_registry_interface(self):
        """服务构造时确保 registry 记录存在（旧站点首次访问不会炸）"""
        self.assertIn(REGISTRY_PREFIX, self.modules.registry.registered)


class TestPasswordPolicyControlPanel(unittest.TestCase):
    """控制面板保存逻辑"""

    def setUp(self):
        self.modules = PolicyModules()
        self.addCleanup(self.modules.uninstall)

    def record_value(self, name):
        return self.modules.registry.records[
            "%s.%s" % (REGISTRY_PREFIX, name)].value

    def test_save_persists_all_settings(self):
        """勾选/填写的内容要逐项落到 registry，并带 saved 标记跳回"""
        view = self.modules.make_view(
            **{"form.save": "Save", "enabled": "1", "min_length": "12",
               "require_uppercase": "1", "require_digit": "1"})

        view.handle_save()

        self.assertTrue(self.record_value("enabled"))
        self.assertEqual(self.record_value("min_length"), 12)
        self.assertTrue(self.record_value("require_uppercase"))
        self.assertTrue(self.record_value("require_digit"))
        # 未勾选的项必须写回 False，不能沿用旧值
        self.assertFalse(self.record_value("require_lowercase"))
        self.assertFalse(self.record_value("require_special"))
        self.assertEqual(
            view.request.response.redirects,
            ["http://nohost/plone/@@password-policy-controlpanel?saved=1"])

    def test_unchecked_boxes_turn_previous_rules_off(self):
        """先全开、再只留 enabled，其余必须清掉（复选框未勾 = 不提交键）"""
        self.modules.registry.reset(
            require_uppercase=True, require_special=True)

        view = self.modules.make_view(**{"form.save": "Save", "enabled": "1",
                                        "min_length": "8"})
        view.handle_save()

        self.assertFalse(self.record_value("require_uppercase"))
        self.assertFalse(self.record_value("require_special"))

    def test_save_rejects_non_integer_min_length(self):
        """非数字的最小长度要报错并且一个字段都不许写"""
        view = self.modules.make_view(
            **{"form.save": "Save", "min_length": "abc"})

        view.handle_save()

        self.assertEqual(view.messages,
                         [("error",
                           "Minimum password length must be an integer.")])
        self.assertEqual(view.request.response.redirects, [])
        self.assertEqual(self.record_value("min_length"),
                         DEFAULT_SETTINGS["min_length"])

    def test_save_rejects_zero_min_length(self):
        """最小长度必须大于 0"""
        view = self.modules.make_view(
            **{"form.save": "Save", "min_length": "0"})

        view.handle_save()

        self.assertEqual(view.messages,
                         [("error",
                           "Minimum password length must be greater than 0.")])
        self.assertEqual(self.record_value("min_length"),
                         DEFAULT_SETTINGS["min_length"])

    def test_cancel_does_not_save(self):
        """取消只跳回，不写任何值"""
        view = self.modules.make_view(**{"form.cancel": "Cancel",
                                         "min_length": "20"})

        self.modules.policy.PasswordPolicyControlPanelView.__call__(view)

        self.assertEqual(view.request.response.redirects,
                         ["http://nohost/plone"])
        self.assertEqual(self.record_value("min_length"),
                         DEFAULT_SETTINGS["min_length"])

    def test_saved_flag_shows_message(self):
        """保存后跳回时提示保存成功"""
        view = self.modules.make_view(saved="1")

        self.modules.policy.PasswordPolicyControlPanelView.__call__(view)

        self.assertEqual(
            view.messages,
            [("info", "Password policy settings saved.")])


class TestPasswordPolicyWiring(unittest.TestCase):
    """注册与接线（源码标记，防静默失效）"""

    def test_view_is_registered_for_site_root(self):
        """@@password-policy-controlpanel 必须注册，且挂在 ManageBika 权限上"""
        source = read_source(CONFIGURE_ZCML)

        self.assertIn('name="password-policy-controlpanel"', source)
        self.assertIn(
            'class=".passwordpolicy.PasswordPolicyControlPanelView"', source)
        self.assertIn('permission="senaite.core.permissions.ManageBika"',
                      source)
        self.assertIn(
            'for="Products.CMFPlone.interfaces.IPloneSiteRoot"', source)

    def test_configlet_is_registered(self):
        """控制面板入口必须在 controlpanel.xml 里，否则管理员找不到"""
        source = read_source(CONTROL_PANEL_XML)

        self.assertIn('action_id="senaite.core.passwordpolicy"', source)
        self.assertIn(
            'url_expr="string:${portal_url}/@@password-policy-controlpanel"',
            source)
        self.assertIn("<permission>senaite.core: Manage Bika</permission>",
                      source)
        self.assertIn('category="plone-security"', source)

    def test_configlet_title_is_ascii(self):
        """actions/controlpanel 的 title 不许出现非 ASCII（规则 R9b）

        中文 title 会在渲染期炸掉 personal bar，而且镜像/启动日志全都正常，
        只有真人打开页面才现形。
        """
        source = read_source(CONTROL_PANEL_XML)

        self.assertIn('title="Password Policy"', source)
        for line in source.splitlines():
            self.assertTrue(
                all(ord(char) < 128 for char in line),
                "controlpanel.xml 出现非 ASCII 字符: %r" % line)

    def test_upgrade_step_imports_configlet(self):
        """已装站点要靠 upgrade step 才能拿到新 configlet（R3）"""
        source = read_source(UPGRADE_ZCML)

        self.assertIn('title="SENAITE.CORE 2.7.0: Add \'Password Policy\' '
                      'control panel configlet"', source)
        self.assertIn('handler=".v02_07_000.import_controlpanel"', source)
        self.assertIn('destination="2747"', source)
        self.assertIn('source="2746"', source)

    def test_profile_version_matches_upgrade_step(self):
        """profile 版本号必须等于最后一个 step 的 destination，否则升级不触发"""
        metadata = read_source(METADATA_XML)
        upgrade = read_source(UPGRADE_ZCML)

        self.assertIn("<version>2747</version>", metadata)
        self.assertIn('destination="2747"', upgrade)

    def test_password_panel_applies_policy(self):
        """改密页要同时挂提示文案和校验"""
        source = read_source(PANEL_SOURCE)

        self.assertIn("from senaite.core.browser.user.passwordpolicy_service "
                      "import PasswordPolicyService", source)
        self.assertIn("summary = PasswordPolicyService().rules_summary()",
                      source)
        self.assertIn("self.widgets[\"new_password\"].description = summary",
                      source)
        self.assertIn("errors = PasswordPolicyService().validate(new_password)",
                      source)

    def test_password_panel_keeps_pas_validation(self):
        """自定义规则不能顶掉 PAS 插件自身的校验"""
        source = read_source(PANEL_SOURCE)

        self.assertIn("registration.testPasswordValidity(new_password,",
                      source)
        # PAS 报错后要先返回，别把两套错误混在一起重复报
        self.assertIn("notifyWidgetActionExecutionError(action,\n"
                      "                                                 "
                      "\"new_password_ctl\", err_str)\n"
                      "                return", source)

    def test_registration_form_applies_policy(self):
        """新建用户页也要挂提示文案和校验"""
        source = read_source(REGISTER_SOURCE)

        self.assertIn("from senaite.core.browser.user.passwordpolicy_service "
                      "import PasswordPolicyService", source)
        self.assertIn("def validate_registration(self, action, data):", source)
        self.assertIn('for fieldname in ("password", "password_ctl"):', source)
        self.assertIn("self.widgets[fieldname].description = summary", source)
        self.assertIn("errors = PasswordPolicyService().validate(password)",
                      source)

    def test_registration_validation_calls_super(self):
        """覆盖基类校验方法必须先调基类，否则丢掉原生校验"""
        source = read_source(REGISTER_SOURCE)

        self.assertIn('super_method = getattr(super(AddUserForm, self),',
                      source)
        self.assertIn('"validate_registration", None)', source)
        self.assertIn("if callable(super_method):", source)
        self.assertIn("super_method(action, data)", source)

    def test_template_posts_to_the_view_with_authenticator(self):
        """表单必须带 CSRF token，且提交按钮名与视图判断一致"""
        source = read_source(TEMPLATE_SOURCE)

        self.assertIn("context/@@authenticator/authenticator", source)
        self.assertIn('name="form.save"', source)
        self.assertIn('name="form.cancel"', source)
        for name in ("enabled", "min_length", "require_uppercase",
                     "require_lowercase", "require_digit", "require_special"):
            self.assertIn('name="%s"' % name, source)


def test_suite():
    from unittest import TestSuite
    from unittest import makeSuite

    suite = TestSuite()
    suite.addTest(makeSuite(TestPasswordPolicyRules))
    suite.addTest(makeSuite(TestPasswordPolicyControlPanel))
    suite.addTest(makeSuite(TestPasswordPolicyWiring))
    return suite
