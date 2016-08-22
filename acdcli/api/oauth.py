import os
import json
import requests
import time
import logging
import webbrowser
import datetime
import random
import string
from requests.auth import AuthBase
from urllib.parse import urlparse, parse_qs
from threading import Lock

logger = logging.getLogger(__name__)

TOKEN_INFO_URL = 'https://api.amazon.com/auth/o2/tokeninfo'


def create_handler(path: str):
    from .common import RequestError

    try:
        return LocalOAuthHandler(path)
    except (KeyError, RequestError, KeyboardInterrupt, EOFError, SystemExit):
        raise
    except:
        pass
    return AppspotOAuthHandler(path)


class OAuthHandler(AuthBase):
    OAUTH_DATA_FILE = 'oauth_data'

    class KEYS(object):
        EXP_IN = 'expires_in'
        ACC_TOKEN = 'access_token'
        REFR_TOKEN = 'refresh_token'
        EXP_TIME = 'exp_time'  # manually added
        REDIRECT_URI = 'redirect_uri'  # only for local

    def __init__(self, path):
        self.path = path
        self.oauth_data = {}
        self.oauth_data_path = os.path.join(path, self.OAUTH_DATA_FILE)
        self.init_time = time.time()
        self.lock = Lock()

    def __call__(self, r: requests.Request):
        with self.lock:
            r.headers['Authorization'] = self.get_auth_token()
        return r

    @property
    def exp_time(self):
        return self.oauth_data[self.KEYS.EXP_TIME]

    @classmethod
    def validate(cls, oauth: str) -> dict:
        """Deserialize and validate an OAuth string

        :raises: RequestError"""

        from .common import RequestError

        try:
            o = json.loads(oauth)
            o[cls.KEYS.ACC_TOKEN]
            o[cls.KEYS.EXP_IN]
            o[cls.KEYS.REFR_TOKEN]
            return o
        except (ValueError, KeyError) as e:
            logger.critical('Invalid authentication token: Invalid JSON or missing key.'
                            'Token:\n%s' % oauth)
            raise RequestError(RequestError.CODE.INVALID_TOKEN, e.__str__())

    def treat_auth_token(self, time_: float):
        """Adds expiration time to member OAuth dict using specified begin time."""
        exp_time = time_ + self.oauth_data[self.KEYS.EXP_IN] - 120
        self.oauth_data[self.KEYS.EXP_TIME] = exp_time
        logger.info('New token expires at %s.'
                    % datetime.datetime.fromtimestamp(exp_time).isoformat(' '))

    def load_oauth_data(self):
        """Loads oauth data file, validate and add expiration time if necessary"""
        self.check_oauth_file_exists()

        with open(self.oauth_data_path) as oa:
            o = oa.read()
        try:
            self.oauth_data = self.validate(o)
        except:
            logger.critical('Local OAuth data file "%s" is invalid. '
                            'Please fix or delete it.' % self.oauth_data_path)
            raise
        if self.KEYS.EXP_TIME not in self.oauth_data:
            self.treat_auth_token(self.init_time)
            self.write_oauth_data()
        else:
            self.get_auth_token(reload=False)

    def get_auth_token(self, reload=True) -> str:
        """Gets current access token, refreshes if necessary.

        :param reload: whether the oauth token file should be reloaded (external update)"""

        if time.time() > self.exp_time:
            logger.info('Token expired at %s.'
                        % datetime.datetime.fromtimestamp(self.exp_time).isoformat(' '))

            # if multiple instances are running, check for updated file
            if reload:
                with open(self.oauth_data_path) as oa:
                    o = oa.read()
                self.oauth_data = self.validate(o)

            if time.time() > self.exp_time:
                self.refresh_auth_token()
            else:
                logger.info('Externally updated token found in oauth file.')
        return "Bearer " + self.oauth_data[self.KEYS.ACC_TOKEN]

    def write_oauth_data(self):
        """Dumps (treated) OAuth dict to file as JSON."""

        new_nm = self.oauth_data_path + ''.join(random.choice(string.hexdigits) for _ in range(8))
        rm_nm = self.oauth_data_path + ''.join(random.choice(string.hexdigits) for _ in range(8))

        f = open(new_nm, 'w')
        json.dump(self.oauth_data, f, indent=4, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
        f.close()

        if os.path.isfile(self.oauth_data_path):
            os.rename(self.oauth_data_path, rm_nm)
        os.rename(new_nm, self.oauth_data_path)
        try:
            os.remove(rm_nm)
        except OSError:
            pass

    def refresh_auth_token(self):
        """Fetches a new access token using the refresh token."""
        raise NotImplementedError

    def check_oauth_file_exists(self):
        """Checks for OAuth file existence and one-time initialize if necessary. Throws on error."""
        raise NotImplementedError

    def get_access_token_info(self) -> dict:
        """
        :returns:
        int exp: expiration time in sec,
        str aud: client id
        user_id, app_id, iat (exp time)"""

        r = requests.get(TOKEN_INFO_URL,
                         params={'access_token': self.oauth_data['access_token']})
        return r.json()


class AppspotOAuthHandler(OAuthHandler):
    APPSPOT_URL = 'https://tensile-runway-92512.appspot.com/'

    def __init__(self, path):
        super().__init__(path)
        self.load_oauth_data()

        logger.info('%s initialized' % self.__class__.__name__)

    def check_oauth_file_exists(self):
        """Checks for existence of oauth token file and instructs user to visit
        the Appspot page if it was not found.

        :raises: FileNotFoundError if oauth file was not placed into cache directory"""

        if os.path.isfile(self.oauth_data_path):
            return

        input('For the one-time authentication a browser (tab) will be opened at %s.\n'
              % AppspotOAuthHandler.APPSPOT_URL + 'Please accept the request and ' +
              'save the plaintext response data into a file called "%s" ' % self.OAUTH_DATA_FILE +
              'in the directory "%s".\nPress a key to open a browser.\n' % self.path)
        webbrowser.open_new_tab(AppspotOAuthHandler.APPSPOT_URL)

        input('Press a key if you have saved the "%s" file into "%s".\n'
              % (self.OAUTH_DATA_FILE, self.path))

        with open(self.oauth_data_path):
            pass

    def refresh_auth_token(self):
        """:raises: RequestError"""

        logger.info('Refreshing authentication token.')

        ref = {self.KEYS.REFR_TOKEN: self.oauth_data[self.KEYS.REFR_TOKEN]}
        t = time.time()

        from .common import RequestError, ConnectionError

        try:
            response = requests.post(self.APPSPOT_URL, data=ref)
        except ConnectionError as e:
            logger.critical('Error refreshing authentication token.')
            raise RequestError(RequestError.CODE.CONN_EXCEPTION, e.__str__())

        if response.status_code != requests.codes.ok:
            raise RequestError(RequestError.CODE.REFRESH_FAILED,
                               'Error refreshing authentication token: %s' % response.text)

        r = self.validate(response.text)

        self.oauth_data = r
        self.treat_auth_token(t)
        self.write_oauth_data()


class LocalOAuthHandler(OAuthHandler):
    """A local OAuth handler that works with a whitelisted security profile.
    The profile must not be created prior to June 2015. Profiles created prior to this month
    are not able to use the new scope "clouddrive:read_all" that replaces "clouddrive:read".
    https://developer.amazon.com/public/apis/experience/cloud-drive/content/getting-started"""

    CLIENT_DATA_FILE = 'client_data'

    AMAZON_OA_LOGIN_URL = 'https://amazon.com/ap/oa'
    AMAZON_OA_TOKEN_URL = 'https://api.amazon.com/auth/o2/token'
    REDIRECT_URI = 'http://localhost'

    def __init__(self, path):
        super().__init__(path)

        self.client_data = {}

        self.client_id = lambda: self.client_data.get('CLIENT_ID')
        self.client_secret = lambda: self.client_data.get('CLIENT_SECRET')

        self.OAUTH_ST1 = lambda: {'client_id': self.client_id(),
                                  'response_type': 'code',
                                  'scope': 'clouddrive:read_all clouddrive:write',
                                  'redirect_uri': self.REDIRECT_URI}

        self.OAUTH_ST2 = lambda: {'grant_type': 'authorization_code',
                                  'code': None,
                                  'client_id': self.client_id(),
                                  'client_secret': self.client_secret(),
                                  'redirect_uri': self.REDIRECT_URI}

        self.OAUTH_REF = lambda: {'grant_type': 'refresh_token',
                                  'refresh_token': None,
                                  'client_id': self.client_id(),
                                  'client_secret': self.client_secret(),
                                  'redirect_uri': self.REDIRECT_URI}

        self.load_client_data()
        self.load_oauth_data()

        logger.info('%s initialized.' % self.__class__.__name__)

    def load_client_data(self):
        """:raises: IOError if client data file was not found
        :raises: KeyError if client data file has missing key(s)"""

        cdp = os.path.join(self.path, self.CLIENT_DATA_FILE)
        with open(cdp) as cd:
            self.client_data = json.load(cd)

        if self.client_id() == '' or self.client_secret() == '':
            logger.critical('Client ID or client secret empty or key absent.')
            raise KeyError

    def check_oauth_file_exists(self):
        """:raises: Exception"""
        if not os.path.isfile(self.oauth_data_path):
            from urllib.parse import urlencode

            url = self.AMAZON_OA_LOGIN_URL + '?' + urlencode(self.OAUTH_ST1())
            webbrowser.open_new_tab(url)
            print('A window will have opened at %s' % url)
            ret_url = input('Please log in or accept '
                            'and enter the URL you have been redirected to: ')
            ret_q = parse_qs(urlparse(ret_url).query)

            st2 = self.OAUTH_ST2()
            st2['code'] = ret_q['code'][0]

            response = requests.post(self.AMAZON_OA_TOKEN_URL, data=st2)
            self.oauth_data = self.validate(response.text)
            self.write_oauth_data()

    def refresh_auth_token(self):
        """:raises: RequestError"""
        logger.info('Refreshing authentication token.')

        ref = self.OAUTH_REF()
        ref[self.KEYS.REFR_TOKEN] = self.oauth_data[self.KEYS.REFR_TOKEN]

        from .common import RequestError

        t = time.time()
        try:
            response = requests.post(self.AMAZON_OA_TOKEN_URL, data=ref)
        except ConnectionError as e:
            logger.critical('Error refreshing authentication token.')
            raise RequestError(RequestError.CODE.CONN_EXCEPTION, e.__str__())

        if response.status_code != requests.codes.ok:
            raise RequestError(RequestError.CODE.REFRESH_FAILED,
                               'Error refreshing authentication token: %s' % response.text)

        self.oauth_data = self.validate(response.text)
        self.treat_auth_token(t)
        self.write_oauth_data()
