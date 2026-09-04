# Archetypes Patches

This package contains patches for Archetype based content types.

## Catalog Multiplex

The module `catalog_multiplex` contains patches for the class
`Products.Archetpyes.CatalogMultiplex.CatalogMultiplex`, which is a mixin for
`BaseContent` and controls how to index, unindex, reindex these content and is
used when e.g. `obj.reindexObject` is called.

### Patches

The following methods are patched:

- `indexObject`
- `unindexObject`
- `reindexObject`

### Reason

The patches ensure that temporary objects are not indexed and delegate the
operation to the respective method of the catalog itself.

Due to the fact that SENAITE catalogs inherit from `Products.CMFPlone.CatalogTool.CatalogTool`,
which is a subclass of `Products.CMFCore.CatalogTool.CatalogTool`, this operation uses the
`IndexQueue` defined in `Products.CMFCore.indexing.IndexQueue` to optimize indexing.

### Notes

The index queue always looks up all registered `IIndexQueueProcessor` utilities
to further delegate the operation.

Since the `PortalCatalogProcessor` utility is registered there as well, a
patching is required to avoid indexing of, e.g. Samples or Analyses there as
they should be only indexed in their primary catalog, e.g.
`seanite_catalog_sample` or `senaite_catalog_analysis`.

Please see `senaite.core.patches.cmfcore.portal_catalog_processor` for details.

Furthermore, changes in `senaite.core.catalog.catalog_multiplex_processor.CatalogMultiplexProcessor` 
were required to handle AT based contens as well.

Please see https://github.com/senaite/senaite.core/pull/2632 for details.

💡 It might make sense to define for each catalog its own `IIndexQueueProcessor`.
A simple check by content type would could decide if a content should be indexed or not.


## UID Catalog indexing

The module `referencable` contains patches for the class `Products.Archetypes.Referencable.Referencable`,
which is a mixin for `BaseObject` and controls AT native referencable behavior
(not used) and the indexing in the UID Catalog (used and needed for UID
references and more).

### Patches

The following methods are patched:

- `_catalogUID_`
- `uncatalogUID`

### Reason

The patches ensure that temporary objects are not indexed.

### Notes

As soon as we have migrated all contents to Dexterity, we should provide a
custom `senaite_catalog_uid` to keep track of the UIDs and maybe references.


## Base Object

The module `base_objects` contains patches for the class `Products.Archetypes.BaseObject.BaseObject`,
which is the base class for our AT based contents.

### Patches

The following methods are patched:

- `getLabels`
- `isTemporary`

### Reason

Provide a similar methods for AT contents as for DX contents.

**getLabels**: Get SENAITE labels (dynamically extended fields)

**isTemporary**: Checks if an object contains a temporary ID to avoid further indexing/processing


## RFC822 Marshaller

The module `marshall` contains a patch for the class
`Products.Archetypes.Marshall.RFC822Marshaller`, the marshaller
`manage_FTPget` uses to serialize an Archetypes object as an RFC822 document.

### Patches

The following methods are patched:

- `marshall`

### Reason

The original calls `str()` on every field value. Under Python 2 that is an
implicit `encode("ascii")` for unicode, so a single field holding translated
text raises `UnicodeEncodeError`. The GenericSetup `content` export step walks
every Archetypes object through `manage_FTPget`, so one such value aborts the
whole step -- and with it every full export run from portal_setup.

The patch routes field values through a `to_str` helper that encodes text as
UTF-8 and leaves everything else to `str()`.

### Notes

Archetypes only: Dexterity content is serialized by
`plone.dexterity.exportimport` and never reaches this marshaller. Byte strings
are the native storage of AT fields, so the UTF-8 written here round-trips on
import into the representation the objects already hold. RFC822 headers carry
no charset declaration, so the file is interpretable as UTF-8 by convention.
