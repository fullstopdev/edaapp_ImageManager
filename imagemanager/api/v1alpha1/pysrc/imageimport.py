#!/usr/bin/env python3
# Auto-generated classes based on your _types.go file (with special logic for CRDs that embed metav1.ObjectMeta)
# The change on this file will be overwritten by running edabuilder create or generate.
import eda_common as eda

from . import Metadata, Y_NAME

from .constants import *
from .imagemanagerconfig import TrackedArtifact
Y_SOURCEURL = 'sourceUrl'
Y_REPO = 'repo'
Y_LICENSEKEY = 'licenseKey'
Y_LICENSEKEYSECRETREF = 'licenseKeySecretRef'
Y_INSECURESKIPTLSVERIFY = 'insecureSkipTLSVerify'
Y_PHASE = 'phase'
Y_MESSAGE = 'message'
Y_DETECTEDNOS = 'detectedNos'
Y_SIZEBYTES = 'sizeBytes'
Y_ARTIFACTS = 'artifacts'
Y_NODEPROFILESNIPPET = 'nodeProfileSnippet'
Y_STARTTIME = 'startTime'
Y_COMPLETIONTIME = 'completionTime'
Y_OBSERVEDGENERATION = 'observedGeneration'
# Package objects (GVK Schemas)
IMAGEIMPORT_SCHEMA = eda.Schema(group='imagemanager.eda.edacommunity.com', version='v1alpha1', kind='ImageImport')


class ImageImportSpec:
    def __init__(
        self,
        sourceUrl: str,
        name: str | None = None,
        repo: str | None = None,
        licenseKey: str | None = None,
        licenseKeySecretRef: str | None = None,
        insecureSkipTLSVerify: bool | None = None,
    ):
        self.sourceUrl = sourceUrl
        self.name = name
        self.repo = repo
        self.licenseKey = licenseKey
        self.licenseKeySecretRef = licenseKeySecretRef
        self.insecureSkipTLSVerify = insecureSkipTLSVerify

    def to_input(self):  # pragma: no cover
        _rval = {}
        if self.sourceUrl is not None:
            _rval[Y_SOURCEURL] = self.sourceUrl
        if self.name is not None:
            _rval[Y_NAME] = self.name
        if self.repo is not None:
            _rval[Y_REPO] = self.repo
        if self.licenseKey is not None:
            _rval[Y_LICENSEKEY] = self.licenseKey
        if self.licenseKeySecretRef is not None:
            _rval[Y_LICENSEKEYSECRETREF] = self.licenseKeySecretRef
        if self.insecureSkipTLSVerify is not None:
            _rval[Y_INSECURESKIPTLSVERIFY] = self.insecureSkipTLSVerify
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageImportSpec | None':
        if obj:
            _sourceUrl = obj.get(Y_SOURCEURL)
            _name = obj.get(Y_NAME)
            _repo = obj.get(Y_REPO)
            _licenseKey = obj.get(Y_LICENSEKEY)
            _licenseKeySecretRef = obj.get(Y_LICENSEKEYSECRETREF)
            _insecureSkipTLSVerify = obj.get(Y_INSECURESKIPTLSVERIFY, False)
            return ImageImportSpec(
                sourceUrl=_sourceUrl,
                name=_name,
                repo=_repo,
                licenseKey=_licenseKey,
                licenseKeySecretRef=_licenseKeySecretRef,
                insecureSkipTLSVerify=_insecureSkipTLSVerify,
            )
        return None  # pragma: no cover


class ImageImportStatus:
    def __init__(
        self,
        phase: str | None = None,
        message: str | None = None,
        detectedNos: str | None = None,
        sizeBytes: int | None = None,
        artifacts: list[TrackedArtifact] | None = None,
        nodeProfileSnippet: str | None = None,
        startTime: str | None = None,
        completionTime: str | None = None,
        observedGeneration: int | None = None,
    ):
        self.phase = phase
        self.message = message
        self.detectedNos = detectedNos
        self.sizeBytes = sizeBytes
        self.artifacts = artifacts
        self.nodeProfileSnippet = nodeProfileSnippet
        self.startTime = startTime
        self.completionTime = completionTime
        self.observedGeneration = observedGeneration

    def to_input(self):  # pragma: no cover
        _rval = {}
        if self.phase is not None:
            _rval[Y_PHASE] = self.phase
        if self.message is not None:
            _rval[Y_MESSAGE] = self.message
        if self.detectedNos is not None:
            _rval[Y_DETECTEDNOS] = self.detectedNos
        if self.sizeBytes is not None:
            _rval[Y_SIZEBYTES] = self.sizeBytes
        if self.artifacts is not None:
            _rval[Y_ARTIFACTS] = [x.to_input() for x in self.artifacts]
        if self.nodeProfileSnippet is not None:
            _rval[Y_NODEPROFILESNIPPET] = self.nodeProfileSnippet
        if self.startTime is not None:
            _rval[Y_STARTTIME] = self.startTime
        if self.completionTime is not None:
            _rval[Y_COMPLETIONTIME] = self.completionTime
        if self.observedGeneration is not None:
            _rval[Y_OBSERVEDGENERATION] = self.observedGeneration
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageImportStatus | None':
        if obj:
            _phase = obj.get(Y_PHASE)
            _message = obj.get(Y_MESSAGE)
            _detectedNos = obj.get(Y_DETECTEDNOS)
            _sizeBytes = obj.get(Y_SIZEBYTES)
            _artifacts = []
            if obj.get(Y_ARTIFACTS) is not None:
                for x in obj.get(Y_ARTIFACTS):
                    _artifacts.append(TrackedArtifact.from_input(x))
            _nodeProfileSnippet = obj.get(Y_NODEPROFILESNIPPET)
            _startTime = obj.get(Y_STARTTIME)
            _completionTime = obj.get(Y_COMPLETIONTIME)
            _observedGeneration = obj.get(Y_OBSERVEDGENERATION)
            return ImageImportStatus(
                phase=_phase,
                message=_message,
                detectedNos=_detectedNos,
                sizeBytes=_sizeBytes,
                artifacts=_artifacts,
                nodeProfileSnippet=_nodeProfileSnippet,
                startTime=_startTime,
                completionTime=_completionTime,
                observedGeneration=_observedGeneration,
            )
        return None  # pragma: no cover


class ImageImport:
    def __init__(
        self,
        metadata: Metadata | None = None,
        spec: ImageImportSpec | None = None,
        status: ImageImportStatus | None = None
    ):
        self.metadata = metadata
        self.spec = spec
        self.status = status

    def to_input(self):  # pragma: no cover
        _rval = {}
        _rval[Y_SCHEMA_KEY] = IMAGEIMPORT_SCHEMA
        if self.metadata is not None:
            _rval[Y_NAME] = self.metadata.name
        if self.spec is not None:
            _rval[Y_SPEC] = self.spec.to_input()
        if self.status is not None:
            _rval[Y_STATUS] = self.status.to_input()
        return _rval

    @staticmethod
    def from_input(obj) -> 'ImageImport | None':
        if obj:
            _metadata = (
                Metadata.from_input(obj.get(Y_METADATA))
                if obj.get(Y_METADATA, None)
                else Metadata.from_name(obj.get(Y_NAME))
            )
            _spec = ImageImportSpec.from_input(obj.get(Y_SPEC, None))
            _status = ImageImportStatus.from_input(obj.get(Y_STATUS))
            return ImageImport(
                metadata=_metadata,
                spec=_spec,
                status=_status,
            )
        return None  # pragma: no cover


class ImageImportList:
    def __init__(
        self,
        items: list[ImageImport],
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
    def from_input(obj) -> 'ImageImportList | None':
        if obj:
            _items = obj.get(Y_ITEMS, [])
            _listMeta = obj.get(Y_METADATA, None)
            return ImageImportList(
                items=_items,
                listMeta=_listMeta,
            )
        return None  # pragma: no cover
