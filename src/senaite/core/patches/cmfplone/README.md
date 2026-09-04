# CMFPlone Patches

This package contains patches for `Products.CMFPlone`.

## Control Panel Export/Import

The module `controlpanel` contains a patch for the class
`Products.CMFPlone.exportimport.controlpanel.ControlPanelXMLAdapter`, the
adapter behind the GenericSetup `controlpanel` import step.

### Patches

The following methods are patched:

- `_initConfiglets`

### Reason

The original builds the configlet title with

    title = Message(str(child.getAttribute('title')), domain=domain)

`getAttribute` returns unicode and `Message` subclasses it, so the `str()` is
an implicit `encode("ascii")`. Any control panel entry with a translated title
raises `UnicodeEncodeError` and aborts the whole `controlpanel` import step.

The patch passes the title as text.

### Notes

The other `str()` calls in the method are deliberately left alone: action ids,
TALES expressions, categories and permission names are identifiers, not prose.
