import re
import sys
import mwparserfromhell
from time import strftime, gmtime
from hashlib import md5
from datetime import datetime
from cerabot import exceptions
from dateutil.parser import parse

__all__ = ["Page"]

class Page(object):
    """Object represents a single page on the wiki.
    On initiation, loads information that could be useful."""

    def __init__(self, site, title="", pageid=0, follow_redirects=False,
                 load_content=True):
        self.site = site
        self._title = title
        self._pageid = pageid
        self._do_content = load_content
        self._follow_redirects = follow_redirects

        self._exists = None
        self._last_editor = None
        self._is_redirect = False
        self._is_talkpage = False
        self._last_revid = None
        self._last_edited = None
        self._creator = None
        self._fullurl = None
        self._is_excluded = False
        self._content = None
        self._protection = None
        self._redirect_target = None

        self._extlinks = []
        self._templates = []
        self._links = []
        self._categories = []
        self._files = []
        self._langlinks = {}

        self._prefix = None
        self._namespace = 0

    def load(self, res=None):
        """Loads the attributes of the current page."""
        self._load(res)

        if self._follow_redirects and self.is_redirect:
            self._title = self.get_redirect_target().title
            del self._content
            self._load()

    def _load(self, res=None):
        """Loads the attributes of this page."""
        if self._title:
            prefix = self._title.split(":", 1)[0]
            if prefix != self._title:
                try:
                    id = self.site.name_to_id(prefix)
                except exceptions.APIError:
                    self._namespace = 0
            elif prefix == self._title:
                self._namespace = 0
            else:
                self._namespace = id

        query = {"action":"query", "prop":"info|revisions", "inprop":
            "protection|url", "rvprop":"user", "rvlimit":1, "rvdir":"newer"}
        if self._title:
            query["titles"] = self._title
        elif self._pageid:
            query["pageid"] = self._pageid
        else:
            error = "No page name or id specified"
            raise exceptions.PageError(error)
        a = res if res else self.site.query(query, query_continue=False)
        result = a["query"]["pages"].values()[0]
        if "invalid" in result:
            error = "Invalid page title {0}".format(unicode(
                self._title))
            raise exceptions.PageError(error)
        elif "missing" in result:
            return
        else:
            self._exists = True

        self._title = result["title"]
        self._pageid = int(result["pageid"])
        if result.get("protection", None):
            self._protection = {"move": (None, None),
                                "create": (None, None),
                                "edit": (None, None)}
            for item in result["protection"]:
                level = item["level"]
                expiry = item["expiry"]
                if expiry == "infinity":
                    expiry = datetime
                else:
                    expiry = parse(item["expiry"])
                self._protection[item["type"]] = level, expiry

        self._namespace = result["ns"]
        self._is_redirect = "redirect" in result
        self._is_talkpage = self._namespace % 2 == 1
        self._fullurl = result["fullurl"]
        self._last_revid = result["lastrevid"]
        self._creator = result["revisions"][0]["user"]
        self._starttimestamp = strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())

        #Now, find out what the current user can do to the page:
        self._tokens = {}
        for permission, token in self.site.tokener().items():
            if token:
                self._tokens[permission] = token
            else:
                continue

        if self._do_content:
            self._load_content()

    def assert_ability(self, action):
        """Asserts whether or not the user can perform *action*."""
        possible_actions = [i.lower() for i in self._tokens.keys()]
        for one in possible_actions:
            if action.lower() == one:
                return
            else:
                continue
        error = "You do not have permission to perform `{0}`"
        raise exceptions.PermissionsError(error.format(action))

    def _load_content(self):
        """Loads the content of the current page."""
        query = {"action":"query", "prop":"revisions|langlinks|extlinks", 
            "titles":self._title, "rvprop":"user|content|timestamp",
            "rvdir":"older"}
        res = self.site.query(query, query_continue=True, 
                prefix=("rv", "ll", "el"))
        result = res["query"]["pages"].values()[0]
        revisions = result["revisions"][0]
        i = list(res["query"]["pages"])[0]
        langlinks = res["query"]["pages"][i].get("langlinks", None)
        extlinks = res["query"]["pages"][i].get("extlinks", None)
        content = revisions["*"]
        try:
            self._content = content.decode()
        except Exception:
            self._content = content
        b = self._title.split(":")
        self._prefix = b[0] if not b[0] == self.title else None
        self._last_editor = revisions["user"]
        self._last_edited = parse(revisions["timestamp"])
        code = mwparserfromhell.parse(self._content)
        self._templates = code.filter_templates(recursive=True)
        self._links = code.filter_links()
        for link in self._links:                
            title = str(link.title).lower()
            if title.startswith("category:"):
                cat = title.split(":")
                if cat[0] == title:
                    continue
                self._categories.append(unicode(link.title))

            elif title.startswith("image:") or title.startswith("file:") \
                    or title.startswith("media:"):
                self._files.append(unicode(link.title))
        if langlinks:
            for langlink in langlinks:
                self._langlinks[langlink["lang"]] = langlink["*"]

        if extlinks:
            for extlink in extlinks:
                self._extlinks.append(extlink["*"])

        # Find out if we are allowed to edit the page or not.
        user = self.site.get_username()
        regex = "\{\{\s*(no)?bots\s*\|?((deny|allow)=(.*?))?\}\}"
        re_compile = re.search(regex, self._content)
        if not re_compile:
            return
        if re_compile.group(1):
            self._is_excluded = True
        if user.lower() in re_compile.group(4).lower():
            if re_compile.group(3) == "allow":
                self._is_excluded = False
            if re_compile.group(3) == "deny":
                self._is_excluded = True
        return

    def _edit(self, text, summary, bot, minor, force, section, append, 
              prepend, create):
        """Edits the page."""
        token = self._tokens["edit"]
        query = {"action":"edit", "title":self.title, "summary":summary}
        if section and (isinstance(section, (tuple, list)) or \
            section == "new"):
            if not section == "new":
                query["section"] = section[0]
                query["sectiontitle"] = section[1]
            else:
                query["section"] = "new"
        if bot is True:
            query["bot"] = "true"
        if minor is True:
            query["minor"] = "true"
        if not force:
            query["basetimestamp"] = self.last_edited
            query["starttimestamp"] = self._starttimestamp
            if create and (self.exists is False):
                query["createonly"] = "true"
            elif create and (self.exists is not False):
                error = "You requested that {0} page be created, but it"
                error += " already exists."
                raise exceptions.PageExistsError(error.format(self.title))
        else:
            query["recreate"] = "true"

        blah = text.encode("utf8") if isinstance(text, unicode) else text
        hashed = md5(blah).hexdigest()
        if append:
            query.update({"appendtext":text})
        elif prepend:
            query.update({"prependtext":text})
        else:
            query.update({"text":text})
        query.update({"md5":hashed, "token":token})
        try:
            data = self.site.query(query)
        except exceptions.APIError as error:
            if error.code in ["editconflict", "pagedeleted", "articleexists"]:
                # These values are now outdated and need to be reloaded
                self._content = None
                self._last_edited = None
                self._exists = None
                raise exceptions.EditError(error.info)
            elif error.code in ["noedit-anon", "cantcreate-anon",
                "noimageredirect-anon", "noedit", "cantcreate", 
                "protectedtitle", "noimageredirect", "emptypage", 
                "emptynewsection"]:
                raise exceptions.PermissionsError(error.info)
            elif error.code == "spamdetected":
                raise exceptions.SpamDetectedError(error.info)
            elif error.code == "contenttobig":
                raise exceptions.ContentExceedsError(error.info)
            elif error.code == "filtered":
                raise exceptions.FilteredError(error.info)

            raise exceptions.EditError(error.info)

        if data["edit"]["result"] == "Success":
            self._content = None
            self._last_edited = None
            self._exists = None
            return data

        raise exceptions.EditError(data["edit"])

    def edit(self, text, summary="", bot=False, minor=False, force=False,
             section=False):
        """Replaces the page's contents with *text* with 
        *summary* as the edit summary. If *bot* is set to True, the
        edit is marked as a bot edit, and if *minor* is set to True,
        the edit is marked as a minor edit.
        
        *force* can be set to True to make the edit to our page,
        disregarding if the page doesn't exist or if there is an edit
        conflict.
        
        Returns a dictionary containing the results of the edit.
        """
        self.assert_ability("edit")
        return self._edit(text, summary, bot, minor, force, section, 
                          append=False, prepend=False, create=False)

    def append(self, text, summary="", bot=False, minor=False, force=False):
        """Appends *text* to the bottom of the page's content with 
        *summary* as the edit summary. If *bot* is set to True, the
        edit is marked as a bot edit, and if *minor* is set to True,
        the edit is marked as a minor edit.
        
        *force* can be set to True to make the edit to our page,
        disregarding if the page doesn't exist or if there is an edit
        conflict.
        
        Returns a dictionary containing the results of the edit.
        """
        self.assert_ability("edit")
        return self._edit(text, summary, bot, minor, force, section=False,
                          append=True, prepend=False, create=False)

    def prepend(self, text, summary="", bot=False, minor=False, force=False):
        """Prepends *text* to the top of the page's content with 
        *summary* as the edit summary. If *bot* is set to True, the
        edit is marked as a bot edit, and if *minor* is set to True,
        the edit is marked as a minor edit.
        
        *force* can be set to True to make the edit to our page,
        disregarding if the page doesn't exist or if there is an edit
        conflict.
        
        Returns a dictionary containing the results of the edit.
        """
        self.assert_ability("edit")
        return self._edit(text, summary, bot, minor, force, section=False,
                          append=False, prepend=True, create=False)

    def create(self, text, summary="", bot=False, minor=False, force=False):
        """Creates our page with *text* as the page's contents and 
        *summary* as the edit summary. If *bot* is set to True, the
        edit is marked as a bot edit, and if *minor* is set to True,
        the edit is marked as a minor edit.
        
        *force* can be set to True to make the edit to our page,
        disregarding if the page doesn't exist or if there is an edit
        conflict.
        
        Returns a dictionary containing the results of the edit.
        """
        self.assert_ability("edit")
        return self._edit(text, summary, bot, minor, force, section=False,
                          append=False, prepend=False, create=True)

    def move(self, target, reason="", *args):
        """Moves our current page to *target with our reasoning being 
        *reason*.
        """
        self.assert_ability("move")
        token = self._tokens(["move"])
        query = {"action":"move", "from":self.title, "to":target,
                 "reason":reason, "token":token}
        allowed = ["movetalk", "movesubpages", "noredirect", "watch", 
                   "unwatch"]
        for arg in args:
            if arg in allowed:
                query[arg] = "true"
        return self.site.query(query)

    def toggle_talk(self, follow_redirects=None):
        if self.namespace < 0:
            ns = self.site.id_to_name(self.namespace)
            error = "Pages in the {0} namespace cannot have talk pages."
            raise exceptions.PageError(error)

        if self.is_talkpage:
            namespace = self.namespace - 1
        else:
            namespace = self.namespace + 1

        try:
            new_title = self.title.split(":", 1)[1]
        except IndexError:
            new_title = self._title

        new_prefix = self.site.id_to_name(namespace)
        if new_prefix:
            new_title = u":".join((new_prefix, new_title))
        else:
            new_title = new_title

        if follow_redirects is None:
            follow_redirects = self._follow_redirects
        return Page(self.site, new_title, follow_redirects=follow_redirects)

    def get_redirect_target(self):
        """Get the target of the redirect in the current page's contents."""
        if not self.exists:
            error = "Current page {0} does not exist."
            raise exceptions.PageExistsError(error.format(self.title))
        re_redirect = r"^\s*\#\s*redirect\s*\[\[(.*?)\]\]"
        content = self.content
        if not self.is_redirect:
            self.redirect_target = None
            return None
        try:
            target = re.match(re_redirect, content).group(1)
            self.redirect_target = Page(self.site, page)
        except IndexError:
            error = "Something went wrong. This may be a glitch in MediaWiki."
            raise exceptions.PageError(error)
        return self.redirect_target

    def rollback(self):
        """Reverts the last edit to the current page."""
        raise NotImplementedError()

    def protect(self, protections=[], expiry="", reason="", ):
        """Protects the current page if the current user id permitted
        to do so. *protections* should be a list of tuples like:
            [(\"edit\", \"autoconfirmed\")
             (\"move\", \"sysop\")]
            or
            [(\"create\", \"sysop\")]
        *expiry* is the date and/or time that the protection should 
        expire in GNU date format. like:
            19 Dec 2004 9:20pm EST
        You may also put `infinity`, `indefinite` or `never` to make the 
        protection never expire. More information documentation about 
        protecting pages is here: 
            http://www.mediawiki.org/wiki/API:Protect#Protecting_pages
        """
        raise NotImplementedError()

    def delete(self, reason="", unwatch=True, watch=False):
        """Deletes the current page and clears invalidated attributes."""
        self.assert_ability("delete")
        token = self._tokens["delete"]
        query = {"action":"delete", "title":self.title, "token":token,
                 "reason":reason}
        if watch and unwatch:
            error = "Both `watch` and `unwatch` cannot be True."
            raise TypeError(error)
        if unwatch:
            query["unwatch"] = "true"
        elif watch:
            query["watch"] = "true"
        data = self.query(query)
        self._content = None
        self._last_edited = None
        self._exists = False
        return data

    def watch(self, action="watch"):
        """Adds the current page to the current user's watchlist."""
        self.assert_ability("watch")
        token = self._tokens["watch"]
        query = {"action":"watch", "title":self.title, "token":token}
        if action == "watch":
            data = self.query(query)
        elif action == "unwatch":
            query["unwatch"] = "true"
            data = self.query(query)
        else:
            error = "Unknown option `{0}` was specified."
            raise exceptions.InvalidOptionError(error)
        return data

    @property
    def title(self):
        return self._title

    @property
    def pageid(self):
        return self._pageid

    @property
    def exists(self):
        return self._exists

    @property
    def is_redirect(self):
        return self._is_redirect

    @property
    def last_revid(self):
        return self._last_revid

    @property
    def last_edited(self):
        return self._last_edited

    @property
    def creator(self):
        return self._creator

    @property
    def fullurl(self):
        return self._fullurl

    @property
    def content(self):
        return self._content

    @property
    def prefix(self):
        return self._prefix

    @property
    def namespace(self):
        return self._namespace

    @property
    def templates(self):
        return self._templates

    @property
    def extlinks(self):
        return self._extlinks

    @property
    def links(self):
        return self._links

    @property
    def categories(self):
        return self._categories

    @property
    def files(self):
        return self._files

    @property
    def is_excluded(self):
        return self._is_excluded

    @property
    def is_talkpage(self):
        return self._is_talkpage

    @property
    def redirect_target(self):
        return self._redirect_target

    @redirect_target.setter
    def redirect_target(self, value):
        setattr(self, "_redirect_target", value)

    def __repr__(self):
        """Return a canonical string representation of Page."""
        res = "Page(title=%s, follow_redirects=%s, site=%s)"
        return res % (self._title, self._follow_redirects, self.site)

    def __str__(self):
        """Return a prettier string representation of Page."""
        res = "<Page(%s of %s)>"
        return res % (self._title, str(self.site),)
