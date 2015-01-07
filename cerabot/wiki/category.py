import sys
from cerabot import exceptions
from .page import Page
from .file import File

class Category(Page):
    """Object that represents a single category on a wiki."""

    def load_attributes(self, res=None, get_all_members=False):
        super(Category, self).load(res)
        self._members = []
        self._subcats = []
        self._files = []
        self._count = {}
        self._is_empty = False

        self._load_attributes(res, get_all_members)

    def _load_attributes(self, res=None, get_all_members=False):
        """Loads attributes about our current category."""
        query_one = {"action":"query", "generator":"categorymembers",
            "gcmtitle":self.title}
        query_two = {"action":"query", "prop":"categoryinfo", "titles":
            self.title}
        a = res if res else self.site.query(query_one, prefix="gcm",
            non_stop=get_all_members)
        try:
            data = a["query"]["pages"].values()
        except (TypeError, IndexError, KeyError):
            data = []
        for cat in data:
            if cat["ns"] == 14:
                c = Category(self.site, cat["title"])
                self._subcats.append(c)
            elif cat["ns"] == 6:
                f = File(self.site, cat["title"])
                self._files.append(f)
            else:
                p = Page(self.site, cat["title"])
                self._members.append(p)
        a = self.site.query(query_two)
        result = a["query"]["pages"].values()[0]["categoryinfo"]
        self._count.update({"size":result["size"],
                            "pages":result["pages"],
                            "files":result["files"],
                            "subcats":result["subcats"]
                        })
        size = len(self._subcats) + len(self._members) + len(self._files)
        if size == 0:
            self._is_empty = True

    @property
    def members(self):
        return self._members

    @property
    def subcats(self):
        return self._subcats

    @property
    def files(self):
        return self._files

    @property
    def categories(self):
        return self._subcats

    @property
    def is_empty(self):
        return self._is_empty

    def size(self, member_type):
        """Gets the amount of *member_type* in our category."""
        try:
            count = self._count[member_type]
        except KeyError:
            error = "Key {0} does not exist."
            raise exceptions.InvalidOptionError(error.format(member_type))
        return count

    def __repr__(self):
        """Return a canonical string representation of Cateogry."""
        res = "Category(title={0}, site={1})"
        return res.format(self.title, str(self.site))

    def __str__(self):
        res = "<Category(category {0} for site object {1})>"
        return res.format(self.title, str(self.site))
