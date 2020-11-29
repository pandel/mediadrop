# This file is a part of MediaDrop (http://www.mediadrop.video),
# Copyright 2009-2015 MediaDrop contributors
# For the exact contribution history, see the git revision log.
# The source code contained in this file is licensed under the GPLv3 or
# (at your option) any later version.
# See LICENSE.txt in the main project directory, for more information.

import re

from repoze.who.classifiers import default_request_classifier
from repoze.who.middleware import PluggableAuthenticationMiddleware
from repoze.who.plugins.auth_tkt import AuthTktCookiePlugin
from repoze.who.plugins.friendlyform import FriendlyFormPlugin
from repoze.who.plugins.sa import SQLAlchemyAuthenticatorPlugin
from webob.request import Request

from mediadrop.config.routing import login_form_url, login_handler_url, \
    logout_handler_url, post_login_url, post_logout_url

from mediadrop.lib.auth.permission_system import MediaDropPermissionSystem



__all__ = ['add_auth', 'classifier_for_flash_uploads', 'session_validity']

days_as_seconds = lambda days: days * 24*60*60
session_validity = days_as_seconds(30) # session expires after 30 days

class MediaDropAuthenticatorPlugin(SQLAlchemyAuthenticatorPlugin):
    def authenticate(self, environ, identity):
        login = super(MediaDropAuthenticatorPlugin, self).authenticate(environ, identity)
        if login is None:
            return None
        user = self.get_user(login)
        # The return value of this method is used to identify the user later on.
        # As the username can be changed, that's not really secure and may 
        # lead to confusion (user is logged out unexpectedly, best case) or 
        # account take-over (impersonation, worst case).
        # The user ID is considered constant and likely the best choice here.
        return user.id
    
    @classmethod
    def by_attribute(cls, attribute_name=None):
        from mediadrop.model import DBSession, User
        authenticator = MediaDropAuthenticatorPlugin(User, DBSession)
        if attribute_name:
            authenticator.translations['user_name'] = attribute_name
        return authenticator


class MediaDropCookiePlugin(AuthTktCookiePlugin):
    def __init__(self, secret, **kwargs):
        if kwargs.get('userid_checker') is not None:
            raise TypeError("__init__() got an unexpected keyword argument 'userid_checker'")
        kwargs['userid_checker'] = self._check_userid
        super(MediaDropCookiePlugin, self).__init__(secret, **kwargs)
    
    def _check_userid(self, user_id):
        # only accept numeric user_ids. In MediaCore < 0.10 the cookie contained
        # the user name, so invalidate all these old sessions.
        if re.search('[^0-9]', user_id):
            return False
        return True

    # IIdentifier
    def identify(self, environ):
        identity = super(MediaDropCookiePlugin, self).identify(environ)
        if identity and self.timeout:
            identity['max_age'] = self.timeout
        return identity


class MediaDropLoginForm(FriendlyFormPlugin):
    def identify(self, environ):
        credentials = super(MediaDropLoginForm, self).identify(environ)
        if credentials is None:
            return None
        if credentials:
            credentials['max_age'] = session_validity
        return credentials


def mediadrop_challenge_decider(environ, status, headers):
    is_xhr = environ.get('HTTP_X_REQUESTED_WITH', '') == 'XMLHttpRequest'
    if is_xhr:
        return False
    return status.startswith('401 ')


def who_args(config):
    auth_by_username = MediaDropAuthenticatorPlugin.by_attribute('user_name')
    
    form = MediaDropLoginForm(
        login_form_url,
        login_handler_url,
        post_login_url,
        logout_handler_url,
        post_logout_url,
        rememberer_name='cookie',
        charset='utf-8',
    )
    cookie_secret = config['sa_auth.cookie_secret']
    cookie = MediaDropCookiePlugin(cookie_secret,
        cookie_name='authtkt', 
        timeout=session_validity, # session expires after 30 days
        reissue_time=session_validity/2, # reissue cookie after 15 days
    )
    
    who_args = {
        'authenticators': [
            ('auth_by_username', auth_by_username)
        ],
        'challenge_decider': mediadrop_challenge_decider,
        'challengers': [('form', form)],
        'classifier': classifier_for_flash_uploads,
        'identifiers': [('main_identifier', form), ('cookie', cookie)],
        'mdproviders': [],
    }
    return who_args


def authentication_middleware(app, config):
    return PluggableAuthenticationMiddleware(app, **who_args(config))


class AuthorizationMiddleware(object):
    def __init__(self, app, config):
        self.app = app
        self.config = config
    
    def __call__(self, environ, start_response):
        environ['mediadrop.perm'] = \
            MediaDropPermissionSystem.permissions_for_request(environ, self.config)
        return self.app(environ, start_response)


def add_auth(app, config):
    authorization_app = AuthorizationMiddleware(app, config)
    return authentication_middleware(authorization_app, config)


def classifier_for_flash_uploads(environ):
    """Normally classifies the request as browser, dav or xmlpost.

    When the Flash uploader is sending a file, it appends the authtkt session
    ID to the POST data so we spoof the cookie header so that the auth code
    will think this was a normal request. In the process, we overwrite any
    pseudo-cookie data that is sent by Flash.

    TODO: Currently overwrites the HTTP_COOKIE, should ideally append.
    """
    classification = default_request_classifier(environ)
    if classification != 'browser':
        return classification
    user_agent = environ.get('HTTP_USER_AGENT', '')
    requested_with = environ.get('HTTP_X_REQUESTED_WITH', '')
    if environ['REQUEST_METHOD'] == 'POST' and (
            ('Flash' in user_agent) or ('Flash' in requested_with)):
        session_key = environ['repoze.who.plugins']['cookie'].cookie_name
        # Construct a temporary request object since this is called before
        # pylons.request is populated. Re-instantiation later comes cheap.
        request = Request(environ)
        try:
            session_id = str(request.POST[session_key])
            environ['HTTP_COOKIE'] = '%s=%s' % (session_key, session_id)
        except (KeyError, UnicodeEncodeError):
            pass
    return classification
