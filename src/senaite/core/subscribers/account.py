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
from bika.lims import _
from bika.lims import api
from Products.statusmessages.interfaces import IStatusMessage
from senaite.core.browser.user.account_status import is_account_disabled


def _expire_auth_cookies(response):
    """清理常见认证 Cookie，避免禁用账号继续沿用旧会话
    """
    response.expireCookie("__ac", path="/")
    response.expireCookie("__ac_name", path="/")


def _reset_credentials(site, request, response):
    """优先走 PAS 标准凭据重置流程
    """
    acl_users = getattr(site, "acl_users", None)
    reset = getattr(acl_users, "resetCredentials", None)
    if callable(reset):
        reset(request, response)


def _switch_request_to_anonymous(request):
    """将当前请求的安全上下文切换为匿名用户
    """
    # 中文注释：仅清 Cookie 只能影响下一次请求；当前这个响应仍可能
    # 保留旧的 AUTHENTICATED_USER，导致主模板把侧栏渲染出来。
    newSecurityManager(request, nobody)
    request["AUTHENTICATED_USER"] = nobody
    environ = getattr(request, "environ", None)
    if isinstance(environ, dict):
        environ["REMOTE_USER"] = ""


def logout_disabled_user(site, event):
    """在请求进入系统前踢出已禁用账号
    """
    request = getattr(event, "request", None)
    if request is None:
        return

    user = api.get_current_user()
    if not user:
        return

    user_id = getattr(user, "getId", lambda: None)()
    if not user_id or user_id == "Anonymous User":
        return
    if not is_account_disabled(user_id):
        return

    response = request.response
    _reset_credentials(site, request, response)
    _expire_auth_cookies(response)
    _switch_request_to_anonymous(request)

    # 登录页本身允许继续打开，避免出现重定向死循环。
    current_url = getattr(request, "ACTUAL_URL", "") or ""
    if current_url.endswith("/login") or current_url.endswith("/@@login"):
        IStatusMessage(request).add(_("This account is disabled."), type="error")
        return

    IStatusMessage(request).add(_("This account is disabled."), type="error")
    response.redirect("{}/login".format(site.absolute_url()))
