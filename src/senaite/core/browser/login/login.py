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

from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SpecialUsers import nobody
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from senaite.core import logger
from senaite.core.browser.user.account_status import is_account_disabled
from Products.CMFPlone.browser.login.login import LoginForm as BaseLoginForm
from z3c.form import button


class LoginForm(BaseLoginForm):

    def _logout_current_request(self):
        """立即清理当前请求中的登录态
        """
        request = self.request
        response = request.response
        acl_users = getattr(self.context, "acl_users", None)
        reset = getattr(acl_users, "resetCredentials", None)
        if callable(reset):
            reset(request, response)

        response.expireCookie("__ac", path="/")
        response.expireCookie("__ac_name", path="/")

        # 中文注释：仅清 Cookie 只会影响下一次请求，这里同时把当前请求
        # 的安全上下文切回匿名，避免登录页右上角继续显示已登录用户名。
        newSecurityManager(request, nobody)
        request["AUTHENTICATED_USER"] = nobody
        environ = getattr(request, "environ", None)
        if isinstance(environ, dict):
            environ["REMOTE_USER"] = ""

    def update(self):
        super(LoginForm, self).update()

    def get_icon_class_for(self, widget):
        if widget.name == "__ac_name":
            return "fas fa-user-lock"
        if widget.name == "__ac_password":
            return "fas fa-key"

    def _get_login_credentials(self):
        """从当前表单请求中提取登录名和密码
        """
        auth = self._get_auth()
        if auth:
            username_key = auth.get("name_cookie", "__ac_name")
            password_key = auth.get("pw_cookie", "__ac_password")
        else:
            username_key = "__ac_name"
            password_key = "__ac_password"

        form = self.request.form
        return form.get(username_key, ""), form.get(password_key, "")

    @button.buttonAndHandler(_("Log in"), name="login")
    def handleLogin(self, action):
        """在标准登录按钮处理器中拦截禁用账号
        """
        username, password = self._get_login_credentials()
        if username and password and is_account_disabled(username):
            self._logout_current_request()
            self.context.plone_utils.addPortalMessage(
                _("This account is disabled."),
                "error")
            return
        # 中文注释：z3c.form 的按钮处理器是可调用对象，不是普通实例方法，
        # 这里必须显式把当前表单实例传给基类处理器。
        return BaseLoginForm.handleLogin(self, action)

    def updateWidgets(self):
        super(LoginForm, self).updateWidgets()
        self.widgets["__ac_name"].addClass("form-control form-control-sm")
        self.widgets["__ac_password"].addClass("form-control form-control-sm")

    def updateActions(self):
        super(LoginForm, self).updateActions()
        self.actions["login"].addClass("btn btn-primary btn-sm")

    @property
    def show_lab_name(self):
        setup = api.get_senaite_setup()
        return setup.getShowLabNameInLogin()

    @property
    def lab_name(self):
        try:
            lab = api.get_senaite_setup().laboratory
            return api.get_title(lab)
        except AttributeError as e:
            # This might happen if the upgrade step 2731 in charge of migrating
            # Laboratory AT content type to DX has not been run yet and the
            # setting "ShowLabNameInLogin" was set to True in setup.
            # User cannot login, so is not possible to run the migration step
            # See https://github.com/senaite/senaite.core/pull/2924
            logger.error("setup.laboratory not found: %s" % str(e))
            return ""
