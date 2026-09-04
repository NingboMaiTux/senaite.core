# CMFCore Patches

This package contains patches for `Products.CMFCore`.

## Portal Catalog Processor

The module `portal_catalog_processor` contains patches for the class
`Products.CMFCore.indexing.PortalCatalogProcessor` which is registered as the
default `IIndexQueueProcessor` utility for the `portal_catalog`.


### Patches

The following methods are patched:

- `index`
- `unindex`
- `reindex`

### Reason

The patches ensure that AT based SENAITE content types are not additionally
indexed in `portal_catalog` if they have a primary catalog assigned, e.g.
Samples -> `senaite_catalog_sample`.

### Notes

Currently, we only keep the root folders like `Clients`, `Methods`, `Samples` etc. in `portal_catalog`.

`index_in_portal_catalog` skips an object whose `portal_type` is missing.
`manage_renameObject` detaches the object from its container while it runs, so
acquisition cannot resolve `portal_type` for the duration, and anything
issuing a catalog search inside that window flushes the indexing queue through
here. Raising there aborts the GenericSetup `content` import step, and
indexing anyway only moves the failure downstream to the metadata columns,
which need the schema the missing type would have named. The rename queues a
fresh index request once the object is back in its container.


## Workflow Tool

The modules `workflowtool` contains patches for the class `Products.CMFCore.WorkflowTool.WorkflowTool`,
which provides workflow related methods like e.g. the `doActionFor` method to
transition from one workflow state to the other.

### Patches

The following methods are patched:

- `_reindexWorkflowVariables`

### Reason

Please see docstring and https://github.com/senaite/senaite.core/pull/2593 for details.

### Notes

Removing this patch made the test `WorkflowAnalysisUnassign` fail, which is an unexpected side-effect.

TODO: We need to investigate the reason of this behavior!


## Content Export/Import

The module `exportimport_content` contains a patch for the class
`Products.CMFCore.exportimport.content.FolderishDAVAwareFileAdapter`, the
adapter `StructureFolderWalkingAdapter` uses to serialize a folder through
WebDAV during the GenericSetup `content` export step.

### Patches

The following methods are patched:

- `export`

### Reason

Archetypes folders decline WebDAV marshalling: `BaseFolder.__dav_marshall__`
is `False`, so `WebDAVSupport.collection_check` raises. CMFCore anticipates
this and falls back to writing a plain `.properties` file, but it catches
`zope.publisher.interfaces.http.MethodNotAllowed` while Archetypes raises
`zExceptions.MethodNotAllowed`. The two classes are unrelated, so the fallback
never fires and the exception escapes to the publisher, aborting the whole
`content` step -- which is what makes "Export all steps" fail in portal_setup.

The patch translates the exception into the class CMFCore actually catches.

### Notes

Only the folderish adapter is patched. Its base `DAVAwareFileAdapter`
serializes non-folderish content elsewhere and must keep raising the HTTP
exception unchanged.
