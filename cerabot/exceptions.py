"""Contains all exceptions Cerabot will need."""

class CerabotError(Exception):
    """Base exception for all follwing exceptions"""

class MissingSettingsError(CerabotError):
    """The settings dictionary in settings.py
    Is empty.
    """

class NoPasswordError(CerabotError):
    """The `passwd` variable was not provided 
    and the `passwd_file` variable is empty.
    """

class RunPageDisabledError(CerabotError):
    """The on-wiki page is disabled."""

class PageInUseError(CerabotError):
    """This is raised when the template {{in use}}
    is present in a page's text. We should not be 
    editing pages that are in use.
    """

class DeadSocketError(CerabotError):
    """IRC Socket is dead."""

class APIError(CerabotError):
    """Error when interacting eith the MediaWiki
    API."""

class APILoginError(APIError):
    """Error when logging into the API."""

class NoConfigError(CerabotError):
    """No config exists or config is empty."""

class SQLError(CerabotError):
    """Error performing something related to an 
    SQL query."""

class ParserError(CerabotError):
    """Error parsing an IRC line."""

class PageError(CerabotError):
    """Error while handling a page."""

class EditError(CerabotError):
    """Error was caught while trying to edit a
    page."""

class PageExistsError(PageError):
    """Page does not exist."""

class InvalidPageError(PageError):
    """Page is invalid."""

class PermissionsError(CerabotError):
    """The current user doesn't have the abilty to 
    perfrom an action."""

class SpamDetectedError(EditError):
    """The API has detected spam in an edit."""

class ContentExceedsError(EditError):
    """The size of the content sent to the API was
    larger than allowed by the wiki."""

class FilteredError(EditError):
    """An abuse filter has tripped and rejected
    our edit."""

class InvalidOptionError(CerabotError):
    """An option or options provided are invalid."""

class UserError(CerabotError):
    """Error while dealing with a user."""

class UserExistsError(UserError):
    """User exists."""

class APIWarningsError(APIError):
    """API gave us a warning."""

class AccountCreationError(UserError):
    """Error while creating an account."""

class UserBlockError(UserError):
    """Error while blocking a user."""

class UserUnblockError(UserError):
    """Error while unblocking a user."""
