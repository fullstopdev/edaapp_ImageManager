/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package v1alpha1

// ImageImportSpec defines the desired state of ImageImport.
//
// Creating an ImageImport is the declarative equivalent of using the
// "Upload Image From File" dialog in the app's web UI: the controller
// downloads SourceUrl, detects whether it's an SR Linux, SR OS (TiMOS), or
// SR-SIM vendor zip, and creates the same Artifact(s) the manual upload path
// creates. The CR's own namespace is used as the target Artifact namespace
// (the same choice the upload dialog's namespace dropdown makes).
type ImageImportSpec struct {
	// SourceUrl is the HTTP(S) URL of the vendor .zip to import (SR Linux,
	// SR OS 7750 TiMOS hardware, or SR-SIM). Must be reachable from inside
	// the cluster. The image type is auto-detected from the zip contents,
	// exactly like a manual upload.
	//
	// To upload a file from your laptop, use the Image Manager dashboard
	// (Image Manager nav entry) — this CR cannot browse local files.
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:Pattern=`^https?://.+`
	// +eda:ui:title="Source URL"
	// +eda:ui:orderpriority=100
	SourceUrl string `json:"sourceUrl"`

	// Name overrides the auto-derived artifact name (default: derived from
	// the detected version, e.g. "srlinux-26.3.9"). Always lowercased.
	// +eda:ui:title="Name override"
	// +eda:ui:orderpriority=200
	Name string `json:"name,omitempty"`

	// Repo overrides ImageManagerConfig.spec.defaultRepo for SR Linux
	// images. SR OS boot images always go to "srosimages" and schema
	// profiles to "schemaprofiles" regardless of this field.
	// +eda:ui:title="Repo override"
	// +eda:ui:orderpriority=300
	Repo string `json:"repo,omitempty"`

	// LicenseKey is an optional Nokia SR OS / SR Linux simulator license
	// key, pasted the same way as the upload dialog's License field
	// (surrounding whitespace/quotes/labels are parsed out). Stored as a
	// ConfigMap in eda-system and wired into the generated NodeProfile via
	// spec.license, exactly like a manual upload.
	//
	// NOTE: this field is plaintext in the CR spec (kubectl get/describe
	// will show it). Prefer LicenseKeySecretRef in namespaces where that
	// matters; this field remains for parity with the upload dialog.
	// +eda:ui:title="License key (inline)"
	// +eda:ui:orderpriority=400
	LicenseKey string `json:"licenseKey,omitempty"`

	// LicenseKeySecretRef names a Secret (in the same namespace as this
	// ImageImport) whose "license.key" data key holds the license, as an
	// alternative to the inline LicenseKey field above.
	// +eda:ui:title="License key (Secret reference)"
	// +eda:ui:orderpriority=410
	LicenseKeySecretRef string `json:"licenseKeySecretRef,omitempty"`

	// InsecureSkipTLSVerify skips TLS certificate verification when
	// fetching SourceUrl. Only intended for lab source servers using
	// self-signed certs; leave false otherwise.
	// +kubebuilder:default=false
	// +eda:ui:title="Skip TLS verify on source"
	// +eda:ui:orderpriority=500
	InsecureSkipTLSVerify bool `json:"insecureSkipTLSVerify,omitempty"`
}

// ImageImportStatus defines the observed state of ImageImport.
// The controller is the sole writer of this status.
type ImageImportStatus struct {
	// Phase is the current stage of the import:
	// Pending, Downloading, Extracting, InProgress, Available, Ready,
	// Failed, or Error. Mirrors the same states shown in the web UI's
	// Status column.
	// +kubebuilder:printcolumn
	Phase string `json:"phase,omitempty"`

	// Message is a human-readable detail for the current phase (e.g. the
	// download error, or the MD5 mismatch reason).
	Message string `json:"message,omitempty"`

	// DetectedNos is the auto-detected image kind: srlinux, sros, or srsim.
	DetectedNos string `json:"detectedNos,omitempty"`

	// SizeBytes is the total downloaded size once known.
	SizeBytes int64 `json:"sizeBytes,omitempty"`

	// Artifacts lists the Artifact CR(s) this import created, mirroring
	// each one's live eda-asvr download status (same shape ImageManager
	// already exposes on ImageManagerConfig.status.artifacts).
	Artifacts []TrackedArtifact `json:"artifacts,omitempty"`

	// NodeProfileSnippet is a ready-to-paste spec.images block once
	// Available/Ready, identical to what the "node profile" popup shows
	// in the web UI.
	NodeProfileSnippet string `json:"nodeProfileSnippet,omitempty"`

	// StartTime is when the controller began processing this import.
	StartTime string `json:"startTime,omitempty"`

	// CompletionTime is when the import reached a terminal phase
	// (Available, Ready, Failed, or Error).
	CompletionTime string `json:"completionTime,omitempty"`

	// ObservedGeneration is the spec generation last reconciled, so the UI
	// can tell a stale status from a fresh one after a spec edit.
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}
