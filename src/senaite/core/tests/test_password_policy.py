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
import re
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


class DummyTransaction(object):
    """模拟 transaction：只记录 commit / abort 次数"""

    def __init__(self):
        self.commits = 0
        self.aborts = 0

    def commit(self):
        self.commits += 1

    def abort(self):
        self.aborts += 1


class DummyMessage(unicode):
    """模拟 zope.i18nmessageid.Message

    真实 Message 是 unicode 子类，值就是 msgid，另带 domain/default/mapping。
    """

    def __new__(cls, msgid, domain=None, default=None, mapping=None):
        self = unicode.__new__(cls, msgid)
        self.domain = domain
        self.default = default
        self.mapping = mapping
        return self


def make_message_factory(domain):
    """模拟 zope.i18nmessageid.MessageFactory"""
    def factory(msgid, mapping=None, default=None, **kw):
        return DummyMessage(msgid, domain=domain, default=default,
                            mapping=mapping)
    return factory


class FakeTranslator(object):
    """模拟 zope.i18n.translate

    忠实复现真实实现的三个行为（对着 zope.i18n 4.9.0 源码写的）：

      * Message 的 domain / default / mapping 由消息本身携带
      * 目录里查得到就用 msgstr，查不到就回落 default
      * 最后一步把 ${...} 占位符按 mapping 替换

    测翻译的时候给 catalog 塞几条 msgstr 就行。
    """

    def __init__(self):
        self.catalog = {}
        self.calls = []

    def __call__(self, msgid, domain=None, mapping=None, context=None,
                 target_language=None, default=None, **kw):
        self.calls.append(unicode(msgid))
        if isinstance(msgid, DummyMessage):
            domain = msgid.domain
            default = msgid.default
            mapping = msgid.mapping
        text = self.catalog.get(unicode(msgid))
        if text is None:
            text = default if default is not None else unicode(msgid)
        if mapping:
            for key, value in mapping.items():
                text = text.replace(u"${%s}" % key, unicode(value))
        return text


def fake_get_tool_by_name(context, name, default=None):
    """模拟 Products.CMFCore.utils.getToolByName"""
    return getattr(context, name, default)


class DummyControlPanelAction(object):
    def __init__(self, action_id):
        self._id = action_id

    def getId(self):  # noqa camelCase (Plone API)
        return self._id


class DummyControlPanelTool(object):
    """模拟 portal_controlpanel"""

    def __init__(self, ids=(), explode=False):
        self._actions = [DummyControlPanelAction(i) for i in ids]
        self.registered = []
        self.explode = explode

    def listActions(self):
        if self.explode:
            raise ValueError("boom")
        return list(self._actions)

    def registerConfiglet(self, **kw):  # noqa camelCase (Plone API)
        self.registered.append(kw)
        self._actions.append(DummyControlPanelAction(kw["id"]))


class DummySite(object):
    """模拟 Plone 站点根：有 id，可能带 portal_controlpanel"""

    def __init__(self, site_id, tool=None, with_tool=True):
        self._id = site_id
        if with_tool:
            self.portal_controlpanel = tool

    def getId(self):  # noqa camelCase (Plone API)
        return self._id


class DummyApp(object):
    def __init__(self, sites):
        self._sites = list(sites)

    def objectValues(self):
        return list(self._sites)


class DummyConnection(object):
    def __init__(self, app):
        self._app = app
        self.closed = False

    def root(self):
        return {"Application": self._app}

    def close(self):
        self.closed = True


class DummyDatabase(object):
    def __init__(self, sites):
        self.connection = DummyConnection(DummyApp(sites))

    def open(self):
        return self.connection


class DummyEvent(object):
    """模拟 zope.processlifetime.IDatabaseOpenedWithRoot 事件"""

    def __init__(self, database):
        self.database = database


def read_source(path):
    with open(path, "r") as handle:
        return handle.read()


class PolicyModules(object):
    """把 passwordpolicy / passwordpolicy_service 用桩加载进来"""

    def __init__(self):
        self.registry = DummyRegistry()
        self.logger = DummyLogger()
        self.transaction = DummyTransaction()
        self.translator = FakeTranslator()
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
        # bika.lims.api + bika.lims.senaiteMessageFactory
        api = types.ModuleType("bika.lims.api")
        api.get_url = lambda context: "http://nohost/plone"
        api.get_tool = lambda name: None
        api.get_request = lambda: None
        self._module("bika")
        lims = self._module(
            "bika.lims", senaiteMessageFactory=make_message_factory(
                "senaite.core"))
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

        # Products.CMFCore.utils.getToolByName
        cmfcore = self._module("Products.CMFCore")
        cmfcore_utils = self._module(
            "Products.CMFCore.utils", getToolByName=fake_get_tool_by_name)
        cmfcore.utils = cmfcore_utils

        # transaction
        self._module("transaction", commit=self.transaction.commit,
                     abort=self.transaction.abort)

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

        # zope.schema / zope.component / zope.interface / zope.i18n
        zope_pkg = self._module("zope")
        schema_module = self._module(
            "zope.schema", Bool=self._fake_field, Int=self._fake_field)
        component = self._module(
            "zope.component",
            getUtility=lambda interface: self.registry)
        interface_module = self._module("zope.interface", Interface=object)
        i18n_module = self._module("zope.i18n", translate=self.translator)
        zope_pkg.schema = schema_module
        zope_pkg.component = component
        zope_pkg.interface = interface_module
        zope_pkg.i18n = i18n_module

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


class TestPasswordPolicyConfiglet(unittest.TestCase):
    """控制面板入口：更新完重启就要出现在「站点设置 → 安全」里

    入口在两处描述：profiles/default/controlpanel.xml（只在安装/新站点生效）
    与 passwordpolicy.register_configlet（已装站点在 ZODB 打开时自愈）。
    这里测的是后者。
    """

    def setUp(self):
        self.modules = PolicyModules()
        self.addCleanup(self.modules.uninstall)
        self.policy = self.modules.policy

    def test_registers_the_entry_when_missing(self):
        """缺了就补上，且补在「安全」那一栏"""
        tool = DummyControlPanelTool()
        site = DummySite("lims", tool)

        self.assertTrue(self.policy.register_configlet(site))

        self.assertEqual(len(tool.registered), 1)
        entry = tool.registered[0]
        self.assertEqual(entry["id"], "senaite.core.passwordpolicy")
        self.assertEqual(entry["category"], "plone-security")
        self.assertEqual(entry["permission"], "senaite.core: Manage Bika")
        self.assertEqual(entry["visible"], 1)
        self.assertEqual(entry["name"], u"Password Policy")
        self.assertIn("@@password-policy-controlpanel", entry["action"])
        self.assertIn("locked.svg", entry["icon_expr"])

    def test_registration_is_idempotent(self):
        """已经有了就一个字节都不动（profile 装过的站点走这条）"""
        tool = DummyControlPanelTool(["senaite.core.passwordpolicy"])
        site = DummySite("lims", tool)

        self.assertFalse(self.policy.register_configlet(site))

        self.assertEqual(tool.registered, [])
        self.assertEqual(len(tool.listActions()), 1)

    def test_registration_keeps_other_entries(self):
        """补入口不能碰别人家的 configlet"""
        tool = DummyControlPanelTool(["senaite.core.registry", "SecuritySettings"])
        site = DummySite("lims", tool)

        self.assertTrue(self.policy.register_configlet(site))

        ids = [action.getId() for action in tool.listActions()]
        self.assertIn("senaite.core.registry", ids)
        self.assertIn("SecuritySettings", ids)
        self.assertEqual(len(ids), 3)

    def test_objects_without_a_control_panel_are_skipped(self):
        """app 根下不是 Plone 站点的对象直接跳过"""
        self.assertFalse(self.policy.register_configlet(
            DummySite("not-a-site", with_tool=False)))

    def test_is_configlet_registered(self):
        tool = DummyControlPanelTool(["senaite.core.passwordpolicy"])
        empty = DummyControlPanelTool()

        self.assertTrue(self.policy.is_configlet_registered(
            DummySite("lims", tool)))
        self.assertFalse(self.policy.is_configlet_registered(
            DummySite("lims", empty)))
        self.assertFalse(self.policy.is_configlet_registered(
            DummySite("lims", with_tool=False)))

    def test_startup_registers_on_every_site(self):
        """ZODB 打开时把每个站点都补一遍，只 commit 一次"""
        tool_a = DummyControlPanelTool()
        tool_b = DummyControlPanelTool()
        event = DummyEvent(DummyDatabase([
            DummySite("lims", tool_a), DummySite("care", tool_b)]))

        added = self.policy.ensure_configlet_on_startup(event)

        self.assertEqual(sorted(added), ["care", "lims"])
        self.assertEqual(len(tool_a.registered), 1)
        self.assertEqual(len(tool_b.registered), 1)
        self.assertEqual(self.modules.transaction.commits, 1)
        self.assertEqual(self.modules.transaction.aborts, 0)

    def test_startup_does_not_commit_when_nothing_was_added(self):
        """没有变化就不写库（每次重启都写一遍是不可接受的）"""
        tool = DummyControlPanelTool(["senaite.core.passwordpolicy"])
        event = DummyEvent(DummyDatabase([DummySite("lims", tool)]))

        self.assertEqual(self.policy.ensure_configlet_on_startup(event), [])
        self.assertEqual(self.modules.transaction.commits, 0)

    def test_startup_skips_sites_that_are_already_done(self):
        """一个站点已有、另一个没有：只补缺的那个，added 只报缺的"""
        done = DummySite("lims", DummyControlPanelTool(
            ["senaite.core.passwordpolicy"]))
        missing = DummySite("care", DummyControlPanelTool())
        event = DummyEvent(DummyDatabase([done, missing]))

        self.assertEqual(self.policy.ensure_configlet_on_startup(event), ["care"])

    def test_startup_survives_a_broken_site(self):
        """一个站点出错不能拖垮其它站点，也不能让实例起不来"""
        broken = DummyControlPanelTool(explode=True)
        good = DummyControlPanelTool()
        event = DummyEvent(DummyDatabase([
            DummySite("broken", broken), DummySite("lims", good)]))

        added = self.policy.ensure_configlet_on_startup(event)

        self.assertEqual(added, ["lims"])
        self.assertEqual(len(good.registered), 1)
        self.assertTrue(self.modules.logger.warnings)

    def test_startup_without_database_is_a_noop(self):
        """事件里没有 database（或压根没事件）时安静返回"""
        self.assertEqual(self.policy.ensure_configlet_on_startup(None), [])
        self.assertEqual(self.policy.ensure_configlet_on_startup(
            DummyEvent(None)), [])
        self.assertEqual(self.modules.transaction.commits, 0)

    def test_startup_without_application_root_is_a_noop(self):
        """root 里没有 Application 时（比如跑测试）不能抛"""
        database = DummyDatabase([])
        database.connection.root = lambda: {}

        self.assertEqual(self.policy.ensure_configlet_on_startup(
            DummyEvent(database)), [])

    def test_startup_always_closes_the_connection(self):
        """连接必须还回去"""
        database = DummyDatabase([DummySite("lims", DummyControlPanelTool())])

        self.policy.ensure_configlet_on_startup(DummyEvent(database))

        self.assertTrue(database.connection.closed)

    def test_startup_closes_the_connection_on_hard_failure(self):
        """连 open/root 都炸了，也要关连接并 abort"""
        class ExplodingDatabase(object):
            def __init__(self):
                self.connection = DummyConnection(None)
                self.connection.root = self._boom

            def _boom(self):
                raise ValueError("no root")

            def open(self):
                return self.connection

        database = ExplodingDatabase()

        self.assertEqual(self.policy.ensure_configlet_on_startup(
            DummyEvent(database)), [])
        self.assertTrue(database.connection.closed)
        self.assertEqual(self.modules.transaction.aborts, 1)
        self.assertTrue(self.modules.logger.warnings)


class TestPasswordPolicyTranslations(unittest.TestCase):
    """中英双语：界面文案必须可翻译，且中文目录里真的翻了

    站点的界面是中文的，功能文案却是硬编码英文 —— 这一组用例就是钉住这件事。
    """

    #: 界面直接用到的 msgid（模板里的字面量、以及两个复用 Plone 的按钮）
    EXTRA_MSGIDS = (
        u"Save",
        u"Cancel",
    )

    def setUp(self):
        self.modules = PolicyModules()
        self.addCleanup(self.modules.uninstall)
        self.service = self.modules.make_service()
        self.translator = self.modules.translator

    # -- 行为：翻译真的会生效 ------------------------------------------

    def test_rules_summary_is_translated_and_interpolated(self):
        """中文目录在时，整句走中文，且 ${count} / ${rules} 被替换掉"""
        self.modules.registry.reset(min_length=10, require_digit=True)
        self.translator.catalog.update({
            u"description_password_policy_rule_min_length":
                u"长度至少 ${count} 位",
            u"description_password_policy_rule_digit": u"至少含 1 个数字",
            u"description_password_policy_rule_separator": u"，",
            u"description_password_policy_summary": u"密码必须${rules}。",
        })

        summary = self.service.rules_summary()

        self.assertEqual(summary, u"密码必须长度至少 10 位，至少含 1 个数字。")
        self.assertNotIn(u"${", summary)

    def test_summary_falls_back_to_english_without_catalog(self):
        """英文站点（目录里没有）回落到默认英文，且占位符同样被替换"""
        self.modules.registry.reset(min_length=8, require_digit=True)

        summary = self.service.rules_summary()

        self.assertEqual(
            summary,
            u"Password must be at least 8 characters long, "
            u"include at least one digit.")
        self.assertNotIn(u"${", summary)

    def test_disabled_summary_is_translated(self):
        self.modules.registry.reset(enabled=False)
        self.translator.catalog[
            u"description_password_policy_disabled"] = u"自定义密码规则已关闭。"

        self.assertEqual(self.service.rules_summary(),
                         u"自定义密码规则已关闭。")

    def test_validation_errors_are_translated(self):
        self.modules.registry.reset(min_length=8, require_digit=True)
        self.translator.catalog.update({
            u"error_password_policy_min_length":
                u"密码长度不能少于 ${count} 位。",
            u"error_password_policy_digit": u"密码必须至少包含 1 个数字。",
        })

        errors = self.service.validate(u"abcdefgh")

        self.assertEqual(errors, [u"密码必须至少包含 1 个数字。"])
        errors = self.service.validate(u"abc")
        self.assertEqual(errors, [
            u"密码长度不能少于 8 位。", u"密码必须至少包含 1 个数字。"])

    def test_panel_messages_are_translated(self):
        """控制面板的提示语也要走翻译（保存成功 / 两个校验错误）"""
        self.translator.catalog.update({
            u"description_password_policy_saved": u"密码规则设置已保存。",
            u"error_password_policy_min_length_not_integer":
                u"密码最短长度必须是整数。",
            u"error_password_policy_min_length_too_small":
                u"密码最短长度必须大于 0。",
        })
        policy = self.modules.policy

        view = self.modules.make_view(saved="1")
        policy.PasswordPolicyControlPanelView.__call__(view)
        self.assertEqual(view.messages, [("info", u"密码规则设置已保存。")])

        view = self.modules.make_view(
            **{"form.save": "Save", "min_length": "abc"})
        view.handle_save()
        self.assertEqual(view.messages,
                         [("error", u"密码最短长度必须是整数。")])

        view = self.modules.make_view(
            **{"form.save": "Save", "min_length": "0"})
        view.handle_save()
        self.assertEqual(view.messages,
                         [("error", u"密码最短长度必须大于 0。")])

    def test_configlet_title_is_a_message(self):
        """入口标题要带域，才能和 profile 那条走同一份翻译"""
        tool = DummyControlPanelTool()
        self.modules.policy.register_configlet(DummySite("lims", tool))

        name = tool.registered[0]["name"]
        self.assertEqual(name, u"Password Policy")
        self.assertEqual(getattr(name, "domain", None), "senaite.core")

    # -- 静态：不留硬编码文案，且中文目录覆盖所有 msgid --------------------

    def _collect_msgids(self):
        """把界面用到的 msgid 全抓出来（模板 + 面板 + 服务 + configlet 标题）"""
        msgids = set(self.EXTRA_MSGIDS)

        template = read_source(TEMPLATE_SOURCE)
        msgids.update(re.findall(r'i18n:translate="([^"]+)"', template))

        for path in (POLICY_SOURCE, SERVICE_SOURCE):
            source = read_source(path)
            msgids.update(re.findall(r'_\(\s*u"([A-Za-z0-9_]+)"', source))
            msgids.update(re.findall(
                r'CONFIGLET_TITLE = u"([^"]+)"', source))

        # controlpanel.xml 的 title 同时也是 msgid
        xml = read_source(CONTROL_PANEL_XML)
        msgids.update(re.findall(
            r'title="(Password Policy)"', xml))
        return msgids

    def _read_catalog(self, language):
        """把 .po 读成 {msgid: msgstr}（拼接续行）"""
        path = os.path.join(
            PACKAGE_DIR, "locales", language, "LC_MESSAGES",
            "senaite.core.po")
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8", "replace")

        catalog = {}
        msgid = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("msgid "):
                msgid = line[6:].strip().strip('"')
                catalog.setdefault(msgid, u"")
            elif line.startswith("msgstr ") and msgid is not None:
                catalog[msgid] = line[7:].strip().strip('"')
                msgid = None
            elif line.startswith('"') and msgid is not None:
                # 多行 msgid 的续行（本功能的 msgid 都是单行，这里只做兼容）
                pass
        return catalog

    def test_template_strings_are_not_hardcoded(self):
        """模板里的文案必须带 i18n:translate，不能是裸文本"""
        template = read_source(TEMPLATE_SOURCE)

        self.assertIn('i18n:domain="senaite.core"', template)
        # 每个 label 都要有 msgid
        self.assertIn('i18n:translate="title_password_policy"', template)
        self.assertIn('i18n:translate="label_password_policy_enabled"',
                      template)
        self.assertIn('i18n:translate="fieldset_password_policy_basic"',
                      template)
        # 提交按钮走 i18n:attributes，复用 Plone 已有的 Save / Cancel
        self.assertEqual(template.count('i18n:attributes="value"'), 2)

    def test_chinese_catalogs_cover_every_msgid(self):
        """zh_CN / zh 两份中文目录必须把每个 msgid 都翻成中文

        这是防漂移的主用例：以后加了新文案却忘了补翻译，这里先红。
        """
        msgids = self._collect_msgids()
        self.assertTrue(len(msgids) > 20, "msgid 抓取异常: %d" % len(msgids))

        for language in ("zh_CN", "zh"):
            catalog = self._read_catalog(language)
            missing = []
            untranslated = []
            for msgid in sorted(msgids):
                if not msgid or msgid not in catalog:
                    missing.append(msgid)
                elif not re.search(u"[^\\x00-\\x7f]", catalog[msgid]):
                    untranslated.append(msgid)
            self.assertEqual(
                missing, [],
                "%s 的 senaite.core.po 缺这些 msgid: %s" % (language, missing))
            self.assertEqual(
                untranslated, [],
                "%s 里这些 msgid 还没翻成中文: %s" % (language, untranslated))

    def test_every_symbolic_msgid_documents_its_english_default(self):
        """符号化 msgid 必须带英文默认值（#. Default:）

        没有默认值的话，没装翻译的站点（英文）看到的就是 `label_...` 这种
        符号名而不是文案。
        """
        path = os.path.join(
            PACKAGE_DIR, "locales", "zh_CN", "LC_MESSAGES",
            "senaite.core.po")
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8", "replace")

        for msgid in sorted(self._collect_msgids()):
            if not re.match(r"^[a-z]", msgid):
                # 这类 msgid 本身就是英文文案（Save / Cancel / Password
                # Policy），默认值是显然的
                continue
            position = text.find('msgid "%s"' % msgid)
            self.assertTrue(position > 0, "po 里找不到 %s" % msgid)
            block = text[text.rfind("\n\n", 0, position):position]
            self.assertIn(
                '#. Default: "', block,
                "%s 缺少 #. Default: 注释（英文站点会看到符号名）" % msgid)


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

    def test_startup_self_heal_is_subscribed(self):
        """入口自愈必须挂在 IDatabaseOpenedWithRoot 上

        只靠 profile 的话，已装站点永远拿不到入口（profile 只在安装/新站点
        时跑），现场表现就是"功能生效了但站点设置里找不到"。
        """
        source = read_source(CONFIGURE_ZCML)

        self.assertIn('for="zope.processlifetime.IDatabaseOpenedWithRoot"',
                      source)
        self.assertIn('handler=".passwordpolicy.ensure_configlet_on_startup"',
                      source)

    def test_runtime_entry_matches_the_profile_entry(self):
        """代码注册的入口必须和 controlpanel.xml 里那份一致

        两条路（profile 导入 / 启动自愈）描述的是同一个入口。任一处漂移，
        就会出现"装过的站点一个样、没装过的另一个样"这种最难查的差异。
        """
        xml = read_source(CONTROL_PANEL_XML)
        policy = read_source(POLICY_SOURCE)

        pairs = (
            ('action_id="senaite.core.passwordpolicy"',
             'CONFIGLET_ID = "senaite.core.passwordpolicy"'),
            ('category="plone-security"',
             'CONFIGLET_CATEGORY = "plone-security"'),
            ('icon_expr="string:++plone++senaite.core.static/assets/icons/'
             'locked.svg"',
             'CONFIGLET_ICON_EXPR = "string:++plone++senaite.core.static/'
             'assets/icons/locked.svg"'),
            ('url_expr="string:${portal_url}/@@password-policy-controlpanel"',
             'CONFIGLET_ACTION = "string:${portal_url}/'
             '@@password-policy-controlpanel"'),
            ('<permission>senaite.core: Manage Bika</permission>',
             'CONFIGLET_PERMISSION = "senaite.core: Manage Bika"'),
            ('title="Password Policy"',
             'CONFIGLET_TITLE = u"Password Policy"'),
        )
        for in_xml, in_python in pairs:
            self.assertIn(in_xml, xml)
            self.assertIn(in_python, policy)

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
    suite.addTest(makeSuite(TestPasswordPolicyConfiglet))
    suite.addTest(makeSuite(TestPasswordPolicyTranslations))
    suite.addTest(makeSuite(TestPasswordPolicyWiring))
    return suite
