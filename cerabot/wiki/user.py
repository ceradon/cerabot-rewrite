import sys
from ipaddress import ip_address
from dateutil.parser import parse
from cerabot.wiki.page import Page
from cerabot import exceptions

class User(object):
    """Object representing a single user on the wiki."""

    def __init__(self, site, name):
        """Constructs the User object."""
        self._site = site
        self._user = name

        self._load_attributes()

    def _load_attributes(self):
        """Loads all attributes relating to our current user."""
        props = "blockinfo|groups|rights|editcount|registration|emailable|gender"
        query = {"action":"query", "list":"users", "ususers":self._user,
            "usprop":props}
        res = self._site.query(query)
        result = res["query"]["users"][0]

        # If the name was entered oddly, normalize it:
        self._user = result["name"]

        try:
            self._userid = result["userid"]
        except KeyError:
            self._exists = False
            return

        self._exists = True

        try:
            self._blocked = {
                "by": result["blockedby"],
                "reason": result["blockreason"],
                "expiry": result["blockexpiry"]
            }
        except KeyError:
            self._blocked = False

        self._groups = result["groups"]
        try:
            self._rights = result["rights"].values()
        except AttributeError:
            self._rights = result["rights"]
        self._editcount = result["editcount"]

        reg = result["registration"]
        try:
            self._registration = parse(reg)
        except TypeError:
            # In case the API doesn't give is a date.
            self._registration = parse("0")

        try:
            result["emailable"]
        except KeyError:
            self._emailable = False
        else:
            self._emailable = True

        self._gender = result["gender"]

    def email(self, text, subject, cc=True):
        if not self._emailable:
            raise exceptions.UserError("User is not allowed to be emailed.")
        token = self._site.tokener(["email"])["email"]
        if not token:
            raise exceptions.PermissionError("Not permitted to email users.")
        query = {"action":"emailuser", "target":self.user, "text":text,
            "subject":subject, "token":token}
        if cc:
            query["ccme"] = "true"
        return self._site.query(query)

    def create(self, password, email, token="", reason="", real=None,
               attempts=0):
        """Create an account for our current user."""
        query = {"action":"createaccount", "name":self.user, "email":email,
            "reason":reason, "realname":real}
        if token:
            query["token"] = token
        res = self._site.query(query)
        if res["result"].lower() == "success":
            return
        elif res["result"].lower() == "needtoken" and attempts == 0:
            return self.create(password, email, reason, real, 
                token=res["token"], attempts=1)
        elif "error" in res:
            if res["error"]["code"] in ["blocked", 
                    "permdenied-createaccount"]:
                raise exceptions.PermissionsError(res["error"]["info"])
            elif res["error"]["code"] == "userexists":
                raise exceptions.UserExistsError(res["error"]["info"])
            else:
                raise exceptions.UserError(res["error"]["info"])
        elif "warning" in res:
            raise exceptions.APIWarningsError(res["warning"])
        raise exceptions.AccountCreationError()

    def block(self, expiry, token="", reason="", *args):
        """Blocks the current user for a period of *expiry* with our
        reasoning being *reason*. *args* are the arguments to the block.
        Possible accepted arguments include:
            * anononly: Blocks the user's IP address(es) from editing, thus
                        forcing the user to log in or create an account to 
                        be able to edit.
            * nocreate: The user's IP address(es) will not be permitted to 
                        create new user accounts.
            * autoblock: Automatically blocks the last IP address that the 
                         user used, and any subsequent IP address that the 
                         user logs in with.
            * noemail: Prevents the user from sending emails through 
                       Special:Emailuser.

        *expiry* is the time that the block will expire. i.e. \"5 months\"
        or \"3 years\". *expiry* may also be set to \"infinity\", 
        \"indefinite\" or \"never\" for the block to never expire.
        """
        valid_args = ["anononly", "nocreate", "autoblock", "noemail"]
        args = args - valid_args
        if not args:
            raise exceptions.UserBlockError("No valid arguments specified.")
        token_ = token if token else self._site.tokener(["block"])["block"]
        if not token:
            raise exceptions.PermissionsError("Not permitted to block users.")
        query = {"action":"block", "user":self.user, "expiry":expiry, "reason":
            reason, "token":token_}
        for arg in args:
            query[arg] = "true"
        res = self._site.query(query)
        if "error" in res:
            if res["error"]["code"] == "permissiondenied":
                raise exceptions.PermissionsError(res["error"]["info"])
            raise exceptions.UserBlockError(res["error"]["info"])
        return res

    def unblock(self, reason=""):
        """Unblocks the current user, with our reasoning being *reason*."""
        token = self._site.tokener(["unblock"])["unblock"]
        if not token:
            raise exceptions.PermissionsError("Not permitted to unblock users")
        query = {"action":"unblock", "user":self.name, "token":token, "reason":
            reason}
        res = self._site.query(query)
        if "error" in res:
            raise exceptions.UserUnblockError(res["error"]["info"])
        return res

    @property
    def user(self):
        return self._user

    @property
    def userid(self):
        return self._userid

    @property
    def exists(self):
        return self._exists

    @property
    def blocked(self):
        return self._blocked

    @property
    def groups(self):
        return self._groups

    @property
    def rights(self):
        return self._rights

    @property
    def editcount(self):
        return self._editcount

    @property
    def registration(self):
        return self._registration

    @property
    def emailable(self):
        return self._emailable

    @property
    def gender(self):
        return self._gender

    @property
    def is_ip(self):
        try:
            is_ip = bool(ip_address(self.user))
        except ValueError:
            is_ip = False
        return is_ip

    @property
    def userpage(self):
        if self._userpage:
            return self._userpage
        else:
            self._userpage = Page(self._site, "User:{0}".format(self.user))
        return self._userpage

    @property
    def talkpage(self):
        if self._talkpage:
            return self._talkpage
        else:
            talkpage = "User talk:{0}".format(self.user)
            self._talkpage = Page(self._site, talkpage)
        return self._talkpage

    def reload(self):
        """Forcibly reload all of the current user's attributes."""
        return self._load_attributes()
