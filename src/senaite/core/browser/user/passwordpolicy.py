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

import transaction
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from plone.registry.interfaces import IRegistry
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core import logger
from zope import schema
from zope.component import getUtility
from zope.i18n import translate as zope_translate
from zope.interface import Interface


REGISTRY_PREFIX = "senaite.core.password_policy"

# Control panel entry. Kept in sync with profiles/default/controlpanel.xml --
# that file only takes effect on install/new site, this module re-adds the
# entry to sites that are already installed (see register_configlet).
#
# The title doubles as its own msgid on purpose: it is what
# `controlpanel.xml` carries, so the entry registered here and the one the
# profile installs resolve to the same translation.
CONFIGLET_ID = "senaite.core.passwordpolicy"
CONFIGLET_TITLE = u"Password Policy"
CONFIGLET_ACTION = "string:${portal_url}/@@password-policy-controlpanel"
CONFIGLET_ICON_EXPR = "string:++plone++senaite.core.static/assets/icons/locked.svg"
CONFIGLET_CATEGORY = "plone-security"
CONFIGLET_PERMISSION = "senaite.core: Manage Bika"
CONFIGLET_APP_ID = "senaite.core"


def translate_message(message):
    """Translates a message for the language of the current request

    `zope.i18n.translate` and not the `senaite.core.i18n` helper: the helper
    flattens the Message to a string first, which drops domain/default/mapping.
    """
    return zope_translate(message, context=api.get_request())


class IPasswordPolicySettings(Interface):
    """密码规则配置 schema。"""

    enabled = schema.Bool(
        title=_(u"label_password_policy_enabled",
                default=u"Enable password policy"),
        description=_(u"help_password_policy_enabled",
                      default=u"Turn the custom password policy on or off."),
        default=True,
        required=False,
    )

    min_length = schema.Int(
        title=_(u"label_password_policy_min_length",
                default=u"Minimum password length"),
        description=_(u"help_password_policy_min_length",
                      default=u"Minimum number of characters required for a "
                              u"password."),
        default=8,
        required=False,
        min=1,
    )

    require_uppercase = schema.Bool(
        title=_(u"label_password_policy_require_uppercase",
                default=u"Require uppercase letter"),
        description=_(u"help_password_policy_require_uppercase",
                      default=u"Password must contain at least one uppercase "
                              u"letter."),
        default=False,
        required=False,
    )

    require_lowercase = schema.Bool(
        title=_(u"label_password_policy_require_lowercase",
                default=u"Require lowercase letter"),
        description=_(u"help_password_policy_require_lowercase",
                      default=u"Password must contain at least one lowercase "
                              u"letter."),
        default=False,
        required=False,
    )

    require_digit = schema.Bool(
        title=_(u"label_password_policy_require_digit",
                default=u"Require digit"),
        description=_(u"help_password_policy_require_digit",
                      default=u"Password must contain at least one number."),
        default=False,
        required=False,
    )

    require_special = schema.Bool(
        title=_(u"label_password_policy_require_special",
                default=u"Require special character"),
        description=_(u"help_password_policy_require_special",
                      default=u"Password must contain at least one special "
                              u"character."),
        default=False,
        required=False,
    )


class PasswordPolicyControlPanelView(BrowserView):
    """管理员密码规则配置页面。"""

    index = ViewPageTemplateFile("templates/password-policy-controlpanel.pt")

    def __call__(self):
        self._ensure_registry_records()
        if self.request.get("saved"):
            self._show_message(translate_message(_(
                u"description_password_policy_saved",
                default=u"Password policy settings saved.")), "info")
        if self.request.get("form.cancel"):
            return self.request.response.redirect(api.get_url(self.context))
        if self.request.get("form.save"):
            return self.handle_save()
        return self.index()

    def _ensure_registry_records(self):
        """确保 registry 字段存在，避免旧站点首次打开时报错。"""
        registry = getUtility(IRegistry)
        try:
            registry.registerInterface(
                IPasswordPolicySettings,
                prefix=REGISTRY_PREFIX,
            )
        except Exception as exc:
            # 不吞掉：注册失败说明 registry 里已有同名但类型不同的记录，
            # 此时面板显示的是默认值，而校验走的是另一套 —— 比报错更难查。
            logger.warning(
                "Unable to register password policy settings: %s" % exc)

    def _show_message(self, message, level="info"):
        api.get_portal().plone_utils.addPortalMessage(message, level)

    def _record_key(self, name):
        return "{}.{}".format(REGISTRY_PREFIX, name)

    def _registry_value(self, name, default=None):
        registry = getUtility(IRegistry)
        record = registry.records.get(self._record_key(name))
        if record is None:
            return default
        return getattr(record, "value", default)

    def _set_registry_value(self, name, value):
        registry = getUtility(IRegistry)
        key = self._record_key(name)
        if key not in registry.records:
            self._ensure_registry_records()
        record = registry.records[key]
        record.value = value

    def enabled(self):
        return bool(self._registry_value("enabled", True))

    def min_length(self):
        return int(self._registry_value("min_length", 8) or 8)

    def require_uppercase(self):
        return bool(self._registry_value("require_uppercase", False))

    def require_lowercase(self):
        return bool(self._registry_value("require_lowercase", False))

    def require_digit(self):
        return bool(self._registry_value("require_digit", False))

    def require_special(self):
        return bool(self._registry_value("require_special", False))

    def handle_save(self):
        """保存密码规则配置。"""
        try:
            min_length = int(self.request.get("min_length", "8") or 8)
        except Exception:
            self._show_message(translate_message(_(
                u"error_password_policy_min_length_not_integer",
                default=u"Minimum password length must be an integer.")),
                "error")
            return self.index()

        if min_length < 1:
            self._show_message(translate_message(_(
                u"error_password_policy_min_length_too_small",
                default=u"Minimum password length must be greater than 0.")),
                "error")
            return self.index()

        self._set_registry_value("enabled", bool(self.request.get("enabled")))
        self._set_registry_value("min_length", min_length)
        self._set_registry_value(
            "require_uppercase",
            bool(self.request.get("require_uppercase")),
        )
        self._set_registry_value(
            "require_lowercase",
            bool(self.request.get("require_lowercase")),
        )
        self._set_registry_value(
            "require_digit",
            bool(self.request.get("require_digit")),
        )
        self._set_registry_value(
            "require_special",
            bool(self.request.get("require_special")),
        )

        return self.request.response.redirect(
            "{}/@@password-policy-controlpanel?saved=1".format(
                api.get_url(self.context)
            )
        )


# --------------------------------------------------------------------------
# Control panel entry self-heal
#
# The entry is described twice on purpose:
#
#   * profiles/default/controlpanel.xml -- read by the GenericSetup
#     `controlpanel` import step, which only runs on install and on new
#     sites, and on demand from ZMI ("Import" tab) or an upgrade step.
#   * this module -- re-adds the entry on sites that are *already installed*,
#     where nothing ever re-runs that import step.
#
# Without the second half the feature works but is unreachable: the password
# rules apply, yet "Site Setup -> Security" has no entry, and the only way to
# get one is a manual ZMI import -- which is exactly the sort of manual step
# that gets skipped on a customer site. Re-adding is idempotent: an existing
# entry (however it got there) is left untouched.
# --------------------------------------------------------------------------

def is_configlet_registered(portal):
    """Checks whether the control panel already has our entry
    """
    tool = getToolByName(portal, "portal_controlpanel", None)
    if tool is None:
        return False
    return CONFIGLET_ID in [action.getId() for action in tool.listActions()]


def register_configlet(portal):
    """Registers the control panel entry if it is missing

    Signature mirrors what `Products.CMFPlone.exportimport.controlpanel`
    passes to `registerConfiglet` for the very same entry, so an entry made
    here and one made by the import step are indistinguishable.

    :param portal: Plone site root
    :returns: True when the entry was added, False when it was already there
    """
    tool = getToolByName(portal, "portal_controlpanel", None)
    if tool is None:
        return False
    if CONFIGLET_ID in [action.getId() for action in tool.listActions()]:
        return False

    tool.registerConfiglet(
        id=CONFIGLET_ID,
        name=_(CONFIGLET_TITLE),
        action=CONFIGLET_ACTION,
        appId=CONFIGLET_APP_ID,
        condition="",
        category=CONFIGLET_CATEGORY,
        permission=CONFIGLET_PERMISSION,
        visible=1,
        icon_expr=CONFIGLET_ICON_EXPR,
    )
    return True


def ensure_configlet_on_startup(event=None):
    """Ensures every site has the control panel entry, once the ZODB is open

    Subscribed to `zope.processlifetime.IDatabaseOpenedWithRoot`, which fires
    after every product is loaded -- the same hook the `set_field` deferral
    uses. Failures are logged, never raised: a broken entry must not be able
    to keep the instance from starting.

    :param event: IDatabaseOpenedWithRoot event (carries `.database`)
    :returns: list with the ids of the sites that got the entry added
    """
    database = getattr(event, "database", None)
    if database is None:
        return []

    added = []
    connection = database.open()
    try:
        root = connection.root()
        app = root.get("Application") if hasattr(root, "get") else None
        if app is None:
            return []

        for portal in app.objectValues():
            try:
                # non-Plone objects in the app root simply have no such tool
                if register_configlet(portal):
                    added.append(portal.getId())
            except Exception as exc:
                logger.warning(
                    "Cannot register the password policy configlet on %r: %s"
                    % (portal, exc))

        if added:
            transaction.commit()
            logger.info(
                "Registered the password policy configlet on: %s"
                % ", ".join(added))
    except Exception as exc:
        transaction.abort()
        logger.warning(
            "Password policy configlet self-heal failed: %s" % exc)
    finally:
        connection.close()

    return added
