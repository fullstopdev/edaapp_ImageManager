#!/usr/bin/env python3
# Auto-generated classes based on your _types.go file (with special logic for CRDs that embed metav1.ObjectMeta)
# The change on this file will be overwritten by running edabuilder create or generate.
import eda_common as eda

from . import Metadata, Y_NAME

from .constants import *
Y_DISPLAYNAME = 'displayName'
Y_NAMESPACE = 'namespace'
Y_SIZEBYTES = 'sizeBytes'
Y_DOWNLOADSTATUS = 'downloadStatus'
Y_STATUSREASON = 'statusReason'
Y_REPO = 'repo'
Y_FILEPATH = 'filePath'
Y_ARTIFACTNAME = 'artifactName'
Y_OPEN = 'open'
# Package objects (GVK Schemas)
IMAGEMANAGERARTIFACT_SCHEMA = eda.Schema(group='imagemanager.eda.edacommunity.com', version='v1alpha1', kind='ImageManagerArtifact')


class ImageManagerArtifactSpec:
    def __init__(
        self,
    ):
        pass

    def to_input(self):  # pragma: no cover
        _rval = {}
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageManagerArtifactSpec | None':
        if obj:
            return ImageManagerArtifactSpec(
            )
        return None  # pragma: no cover


class ImageManagerArtifactStatus:
    def __init__(
        self,
        displayName: str | None = None,
        namespace: str | None = None,
        sizeBytes: int | None = None,
        downloadStatus: str | None = None,
        statusReason: str | None = None,
        repo: str | None = None,
        filePath: str | None = None,
        artifactName: str | None = None,
        open: str | None = None,
    ):
        self.displayName = displayName
        self.namespace = namespace
        self.sizeBytes = sizeBytes
        self.downloadStatus = downloadStatus
        self.statusReason = statusReason
        self.repo = repo
        self.filePath = filePath
        self.artifactName = artifactName
        self.open = open

    def to_input(self):  # pragma: no cover
        _rval = {}
        if self.displayName is not None:
            _rval[Y_DISPLAYNAME] = self.displayName
        if self.namespace is not None:
            _rval[Y_NAMESPACE] = self.namespace
        if self.sizeBytes is not None:
            _rval[Y_SIZEBYTES] = self.sizeBytes
        if self.downloadStatus is not None:
            _rval[Y_DOWNLOADSTATUS] = self.downloadStatus
        if self.statusReason is not None:
            _rval[Y_STATUSREASON] = self.statusReason
        if self.repo is not None:
            _rval[Y_REPO] = self.repo
        if self.filePath is not None:
            _rval[Y_FILEPATH] = self.filePath
        if self.artifactName is not None:
            _rval[Y_ARTIFACTNAME] = self.artifactName
        if self.open is not None:
            _rval[Y_OPEN] = self.open
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageManagerArtifactStatus | None':
        if obj:
            _displayName = obj.get(Y_DISPLAYNAME)
            _namespace = obj.get(Y_NAMESPACE)
            _sizeBytes = obj.get(Y_SIZEBYTES)
            _downloadStatus = obj.get(Y_DOWNLOADSTATUS)
            _statusReason = obj.get(Y_STATUSREASON)
            _repo = obj.get(Y_REPO)
            _filePath = obj.get(Y_FILEPATH)
            _artifactName = obj.get(Y_ARTIFACTNAME)
            _open = obj.get(Y_OPEN)
            return ImageManagerArtifactStatus(
                displayName=_displayName,
                namespace=_namespace,
                sizeBytes=_sizeBytes,
                downloadStatus=_downloadStatus,
                statusReason=_statusReason,
                repo=_repo,
                filePath=_filePath,
                artifactName=_artifactName,
                open=_open,
            )
        return None  # pragma: no cover


class ImageManagerArtifact:
    def __init__(
        self,
        metadata: Metadata | None = None,
        spec: ImageManagerArtifactSpec | None = None,
        status: ImageManagerArtifactStatus | None = None
    ):
        self.metadata = metadata
        self.spec = spec
        self.status = status

    def to_input(self):  # pragma: no cover
        _rval = {}
        _rval[Y_SCHEMA_KEY] = IMAGEMANAGERARTIFACT_SCHEMA
        if self.metadata is not None:
            _rval[Y_NAME] = self.metadata.name
        if self.spec is not None:
            _rval[Y_SPEC] = self.spec.to_input()
        if self.status is not None:
            _rval[Y_STATUS] = self.status.to_input()
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageManagerArtifact | None':
        if obj:
            _metadata = (
                Metadata.from_input(obj.get(Y_METADATA))
                if obj.get(Y_METADATA, None)
                else Metadata.from_name(obj.get(Y_NAME))
            )
            _spec = ImageManagerArtifactSpec.from_input(obj.get(Y_SPEC, None))
            _status = ImageManagerArtifactStatus.from_input(obj.get(Y_STATUS))
            return ImageManagerArtifact(
                metadata=_metadata,
                spec=_spec,
                status=_status,
            )
        return None  # pragma: no cover


class ImageManagerArtifactList:
    def __init__(
        self,
        items: list[ImageManagerArtifact],
        listMeta: object | None = None
    ):
        self.items = items
        self.listMeta = listMeta

    def to_input(self):  # pragma: no cover
        _rval = {}
        if self.items is not None:
            _rval[Y_ITEMS] = self.items
        if self.listMeta is not None:
            _rval[Y_METADATA] = self.listMeta
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageManagerArtifactList | None':
        if obj:
            _items = obj.get(Y_ITEMS, [])
            _listMeta = obj.get(Y_METADATA, None)
            return ImageManagerArtifactList(
                items=_items,
                listMeta=_listMeta,
            )
        return None  # pragma: no cover
