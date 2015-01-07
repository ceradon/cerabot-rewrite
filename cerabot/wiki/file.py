import sys
from cerabot import exceptions
from os.path import expanduser, join, exists
from urllib import urlretrieve
from .page import Page
from dateutil.parser import parse

class File(Page):
    """Object represents a single file on the wiki."""

    def load_attributes(self, res=None):
        """Loads all attributes of the current file."""
        query = {"action":"query", "prop":"imageinfo", "iiprop":
            "timestamp|user|url|size|sha1|mime", "titles":self.title}
        res = self.site.query(query)
        res = res["query"]["pages"][list(res["query"]["pages"])[0]]
        super(File, self).load()
        try:
            result = res["imageinfo"][0]
        except (KeyError, IndexError):
            return
        self._repository = res["imagerepository"]
        self._timestamp = parse(result["timestamp"])
        self._user = result["user"] # TODO: Make a User clase
        self._size = result["size"]
        self._url = result["url"]
        self._hashed = result["sha1"]
        self._mime = result["mime"]
        self._description = result["descriptionurl"]
        self._dimensions = result["height"], result["width"]

    def download(self, local=""):
        """Downloads the current image and stores it at
        *local*. By default local is '~/<filename>'."""
        if not self.exists:
            error = "File {0!r} doesn't exist."
            raise exceptions.PageExistsError(error)
        path = join(expanduser("~"), self.title.split(":")[-1])
        try:
            urlretrieve(self.url, local if local else path)
        except urllib.HTTPError:
            return False
        if not exists(local if local else path):
            return False
        return True

    def upload(self, fileobj=None, text="", summary="", comment="", 
            watch=True, key=""):
        self.assert_ability("edit")
        path = join(expanduser("~"), self.title.split(":")[-1])
        if not fileobj or not isinstance(fileobj, file):
            fileobj = open(path)
        fileobj.seek(0)
        contents = fileobj.read()
        query = {"filename": self.title, "text": text, "comment": summary, 
                 "watch": watch, "ignorewarnings": True, "file": contents,
                 "token": self._tokens["edit"]}
        if key:
            query["sessionkey"] = key
        result = self.site.query(query).get("upload", 0)
        if result and result["result"] == "Success":
            self.dimensions, self._user, self._hashed = (None, None, None)
            self._exists = True
        return result

    @property
    def user(self):
        return self._user

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def size(self):
        return self._size

    @property
    def url(self):
        return self._url

    @property
    def hashed(self):
        return self._hashed

    @property
    def mime(self):
        return self._mime

    @property
    def description(self):
        return self._description

    @property
    def dimensions(self):
        self._dimensions
