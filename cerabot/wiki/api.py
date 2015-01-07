import re
import sys
import time
import itertools
try:
    import json
except Exception:
    import simplejson as json
try:
    import gzip
except Exception:
    gzip = False
from threading import Lock
from copy import deepcopy
from StringIO import StringIO
from cookielib import CookieJar
from urllib import quote_plus
from cerabot import exceptions
from urlparse import urlparse
from platform import python_version as pyv
from urllib2 import build_opener, HTTPCookieProcessor, URLError

from .page import Page
from .category import Category
from .user import User
from .file import File

class Site(object):
    """Main point for which interaction with a MediaWiki
    API is made."""
    GITHUB = "https://github.com/ceradon/cerabot"
    USER_AGENT = "Cerabot/{0!r} (wikibot; Python/{1!r}; {2!r})"
    USER_AGENT = USER_AGENT.format("0.1", pyv(), GITHUB)
    config = {"throttle":10,
              "maxlag":10,
              "max_retries":3}

    def __init__(self, name=None, base_url="//en.wikipedia.org",
            project=None, lang=None, namespaces={}, login=(None, None),
            secure=False, config=None, user_agent=None, article_path=None,
            script_path="/w"):
        self._name = name
        if not project and not lang:
            self._base_url = base_url
            self._project = None
            self._lang = None
        else:
            self._lang = lang
            self._project = project
            self._base_url = "http://{0!r}.{1!r}".format(self._lang,
                    self._project)
        self._article_path = article_path
        self._script_path = script_path
        self._namespaces = namespaces
        if config:
            self._config = config
        else:
            self._config = self.config
        self._login_data = login
        self._secure = secure
        self._tokens = {}
        if user_agent:
            self._user_agent = user_agent
        else:
            self._user_agent = self.USER_AGENT

        self._throttle, self._maxlag, self._max_retries = self._config.values()
        self._last_query_time = 0
        self.cookie_jar = CookieJar()
        self.api_lock = Lock()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.opener.addheaders = [("User-Agent", self._user_agent),
                                  ("Accept-Encoding", "gzip")]
        if self._login_data[0] and self._login_data[1]:
            self.login(login)
        self._load()

    def urlencode(self, params):
        """Implement urllib.urlencode() with support for unicode input.
        Thanks to Earwig (Ben Kurtovic) for this code."""
        enc = lambda s: s.encode("utf8") if isinstance(s, unicode) else str(s)
        args = []
        for key, val in params.iteritems():
            key = quote_plus(enc(key))
            val = quote_plus(enc(val))
            args.append(key + "=" + val)
        return "&".join(args)

    def _query(self, params, query_continue=False, tries=0, idle=5, 
            non_stop=False, prefix=None):
        """Queries the site's API."""
        last_query = time.time() - self._last_query_time
        if last_query < self._throttle:
            throttle = self._throttle - last_query
            print "Throttling: waiting {0} seconds".format(round(throttle, 2))
            time.sleep(throttle)
        params.setdefault("maxlag", self._maxlag)
        params.setdefault("format", "json")
        params["continue"] = ""
        try:
            if type(prefix).__name__ in ["tuple", "list"]:
                for p in prefix:
                    params[p + "limit"] = "max"
            else:
                params[prefix + "limit"] = "max"
        except TypeError:
            pass
        protocol = "https:" if self._secure else "http:"
        url = ''.join((protocol, self._base_url, self._script_path, "/api.php"))
        data = self.urlencode(params)
        try:
            reply = self.opener.open(url, data)
        except URLError as e:
            if hasattr(e, "code"):
                exc = "API query could not be completed: Error code: {0}"
                exc = exc.format(e.code)
            elif hasattr(e, "reason"):
                exc = "API query could not be completed. Reason: {0}"
                exc = exc.format(e.reason)
            else:
                exc = "API query could not be completed."
            raise exceptions.APIError(exc)
        
        result = reply.read()
        if reply.headers.get("Content-Encoding") == "gzip":
            stream = StringIO(result)
            zipper = gzip.GzipFile(fileobj=stream)
            result = zipper.read()
        
        try:
            res = json.loads(result)
        except ValueError:
            e = "API query failed: JSON could not be loaded"
            raise exceptions.APIError(e)
        
        try:
            code = res["error"]["code"]
            info = res["error"]["info"]
        except (TypeError, ValueError, KeyError):
            if "continue" in res and query_continue:
                continue_data = self._handle_query_continue(params, res, 
                    max_continues=5 if not non_stop else "max")
                res.update(continue_data)
            return res
        
        if code == "maxlag":
            if tries >= self._max_retries:
                e = "Maximum amount of allowed retries has been exhausted."
                raise exception.APIError(e)
            tries += 1
            time.sleep(idle)
            return self._query(params, tries=tries, idle=idle*2)
        else:
            e = "An unknown error occured. Here is the data from the API: {0}"
            return_data = "({0}, {1})".format(code, info)
            error = exceptions.APIError(e.format(return_data))
            error.code, error.info = code, info
            raise error
    
    def _load(self, force=False):
        """Loads the sites attributes. Called automatically on initiation."""
        attrs = [self._name, self._project, self._lang, self._base_url,
                self._script_path, self._article_path]
        query = {"action":"query", "meta":"siteinfo", "siprop":"general"}

        if not self._namespaces or force:
            query["siprop"] += "|namespaces|namespacealiases"
            result = self._query(query)
            for item in result["query"]["namespaces"].values():
                ns_id = item["id"]
                name = item["*"]
                try:
                    canonical = item["canonical"]
                except KeyError:
                    self._namespaces[ns_id] = [name]
                else:
                    if name != canonical:
                        self._namespaces[ns_id] = [name, canonical]
                    else:
                        self._namespaces[ns_id] = [name]
            
            for item in result["query"]["namespacealiases"]:
                ns_id = item["id"]
                alias = item["*"]
                self._namespaces[ns_id].append(alias)
        elif all(attrs):
            return
        else:
            result = self.query(query)
        
        result = result["query"]["general"]
        self._name = result["wikiid"]
        self._project = result["sitename"].lower()
        self._lang = result["lang"]
        self._base_url = result["server"]
        self._script_path = result["scriptpath"]
        self._article_path = result["articlepath"]

    def _handle_query_continue(self, request, data, max_continues=5):
        """Handle \'query-continues\' in API queries."""
        all_data = {}
        count = 0
        last_continue = {}
        if max_continues == "max":
            # I solemnly doubt there will ever be this many continues
            max_continues = 10000
        while "continue" in data and count < max_continues:
            query = deepcopy(request)
            query.update(last_continue)
            res = self._query(query)
            if "continue" in res:
                last_continue = res["continue"]
            try:
                if not all_data:
                    all_data = res
                else:
                    all_data.update(res)
            except (KeyError, IndexError):
                pass
            count += 1
            data = res
        data.update(all_data)
        return data

    def page(self, title="", pageid=0, follow_redirects=False):
        """Returns an instance of Page for *title* with *follow_redirects* 
        and *pageid* as arguments, unless *title* is a category, then 
        returns a Cateogry instance."""
        return Page(self, title, pageid, follow_redirects)

    def category(self, title="", pageid=0, follow_redirects=False):
        """Returns an instance of Category for *title* with *follow_redirects*
        and *pageid* as arguments."""
        return Category(self, title, pageid, follow_redirects)

    def user(self, name=None):
        """Returns an instance of User for *username*."""
        return User(name)

    def file(self, title, pageid=0, follow_redirects=False):
        """Returns an instance of File for *title* or *pageid*."""
        return File(title, pageid, follow_redirects)

    @property
    def domain(self):
        """Returns the site's web domain, like \"en.wikipedia.org\""""
        return urlparse(self._base_url).netloc

    def get_username(self):
        """Gets the name of the user that is currently logged into the site's API.
        Simple way to ensure that we are logged in."""
        data = self.query({"action":"query", "meta":"userinfo"})
        return data["query"]["userinfo"]["name"]

    def get_cookies(self, name, domain):
        for cookie in self.cookie_jar:
            if cookie.name == name and cookie.domain == domain:
                if cookie.is_expired():
                    break
                return cookie

    def save_cookie_jar(self):
        """Attempts to save all changes to our cookiejar after a 
        successful login or logout."""
        if hasattr(self.cookie_jar, "save"):
            try:
                getattr(self._cookiejar, "save")()
            except (NotImplementedError, ValueError):
                pass

    def query(self, params, query_continue=False, non_stop=False, 
            prefix=None):
        """Queries the site's API."""
        with self.api_lock:
            i = self._query(params, query_continue, non_stop=non_stop,
                prefix=prefix)
        return i

    def _login(self, login, token=None, attempts=0):
        """Logs into the site's API."""
        username, password = login
        if token:
            i = self.query({"action":"login", "lgname":username, 
                            "lgpassword":password, "lgtoken":token})
        else:
            i = self.query({"action":"login", 
                            "lgname":username, 
                            "lgpassword":password})

        res = i["login"]["result"]
        if res == "Success":
            self.save_cookie_jar()
        elif res == "NeedToken" and attempts == 0:
            token = i["login"]["token"]
            return self._login(login, token, attempts=1)
        else:
            if res == "Illegal":
                e = "The provided username is illegal."
            elif res == "NotExists":
                e = "The provided username does not exist."
            elif res == "EmptyPass":
                e = "No password was given."
            elif res == "WrongPass" or res == "WrongPluginPass":
                e = "The given password is incorrect."
            else:
                e = "An unknown error occured, API responded with {0)."
                e = e.format(res)
            raise exceptions.APILoginError(e)

    def login(self, login):
        """Public method for logging in to the API."""
        if not login:
            if self._login[0]:
                login = self._login
            else:
                e = "No login data or insufficient data provided."
                raise exceptions.APILoginError(e)
        if type(login) == tuple:
            self._login(login)
        else:
            e = "Login data must be in tuple format, got {0}"
            raise exceptions.APILoginError(e.format(type(login)))

    def logout(self):
        """Attempts to logout out the API and clear the cookie jar."""
        self.query({"action":"logout"})
        self.cookie_jar.clear()
        self.save_cookie_jar()

    def tokener(self, args=[]):
        i = re.compile("Action (.*?) is not allowed for the current user")
        valid_args = ["block", "delete", "edit", "email", "import", "move",
                      "options", "patrol", "protect", "unblock", "watch"]
        if not args:
            args = valid_args
        if self._tokens:
            m = {}
            for token in args:
                try:
                    m[token] = self._tokens[token]
                except (KeyError, IndexError):
                    m[token] = None
                    continue
            return m

        if not type(args) == list:
            return
        query = {"action":"query", "prop":"info", "titles":"Main Page",
                 "intoken":"|".join(args)}
        result = self.query(query)
        res = result["query"]["pages"]
        _tokens = {}
        c = res.keys()[0]
        possible_tokens = res[c]
        for key, val in possible_tokens.items():
            if key.endswith("token"):
                name = key[:key.find("token")]
                _tokens[name] = val
                args.pop(args.index(name))
        
        if "warnings" in result:
            a = result["warnings"]["info"]["*"].split("\n")
            if len(a) > 1:
                a = [b for b in a if b.lower().startswith("action")]
            for item in a:
                name = i.findall(item)
                name = name[0].strip("'")
                _tokens[name] = None
        self._tokens.update(_tokens)
        return _tokens

    def iterator(self, **kwargs):
        """Iterates over result of api query with *kwargs* as arguments
        and returns a generator."""
        result = None
        if "action" in kwargs.keys():
            kwargs.pop("action", 0)
        kwargs["action"] = "query"
        res = self.query(kwargs)
        if "warnings" in res:
            e = "Unknown error occured while attempting iterator query."
            e += " Got back: {0}".format(res)
            raise exceptions.APIError(e)
        if len(res["query"]) > 1:
            result = {}
            a = {}
            b = list(res["query"])
            for key, val in res["query"].items():
                a[key] = val
            while len(b) > 0:
                key = b.pop(0, False)
                if not key:
                    break
                results[key] = itertools.chain(a[key])
        elif len(res["query"]) == 1:
            result = (i for i in res["query"][list(res["query"])[0]])
        return result 

    def name_to_id(self, name):
        """Returns the associated id to the namespace *name*."""
        for ns_id, names in self._namespaces.items():
            if name.lower() in [i.lower() for i in names]:
                return ns_id

        error = "No such namespace with name {0}."
        raise exceptions.APIError(error)

    def id_to_name(self, ns_id, get_all=False):
        """Returns the associated name to the namespace id *ns_id*."""
        try:
            if get_all:
                return self._namespaces[ns_id]
            else:
                return self._namespaces[ns_id][0]
        except KeyError:
            error = "No such id with namespace {0}."
            raise exceptions.APIError(error)

    def __repr__(self):
        """Returns a coanonical string representation of Site."""
        res = u"Site(name={0}, base_url={1}, project={2}, lang={3}, "+ \
            "namespaces={4}, secure={5}, config={6}, article_path={7}"+ \
            "script_path={8}, user_agent={9}".format(self._name, 
            self._base_url, self._project, self._lang, self._namespaces, 
            self._secure, unicode(self._config), self._article_path,
            self._script_path, self._user_agent)
        if self._login_data[0] and self._login_data[1]:
            res = res + ", username={0}, password=<hidden>".format(
                self._login_data[0])
        return res

    def __str__(self):
        """Returns a prettier string representation of Site."""
        res = u"<Site(site object %s (%s, %s) for site %s"+ \
            " with user %s, config %s and user agent %s."
        if self._login_data[0]:
            res = res % (self._name, self._lang, self._project, self._base_url, 
                self._login_data[0], unicode(self._config), self._user_agent)
            return res.replace("'", "")
        res = res.replace("user %s, ", "")
        res = res % (self._name, self._lang, self._project, self._base_url,
            unicode(self._config), self._user_agent)
        return res.replace("'", "")
