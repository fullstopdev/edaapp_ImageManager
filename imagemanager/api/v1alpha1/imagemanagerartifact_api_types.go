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

// ImageManagerArtifactStatus is a launcher-dashlet row for one tracked image.
// The controller is the sole writer; rows mirror PVC uploads and managed
// Artifact CRs so the EDA nav table can query a flat CR list (EQL cannot
// navigate into ImageManagerConfig.status.artifacts arrays).
type ImageManagerArtifactStatus struct {
	// DisplayName is the human-friendly image name shown in the launcher UI.
	DisplayName string `json:"displayName,omitempty"`

	// Namespace is the Artifact CR namespace.
	Namespace string `json:"namespace,omitempty"`

	// SizeBytes is the on-disk size when known.
	SizeBytes int64 `json:"sizeBytes,omitempty"`

	// DownloadStatus mirrors Artifact.status.downloadStatus (or aggregated).
	DownloadStatus string `json:"downloadStatus,omitempty"`

	// StatusReason is a short error/detail string when applicable.
	StatusReason string `json:"statusReason,omitempty"`

	// Repo is the artifact repo.
	Repo string `json:"repo,omitempty"`

	// FilePath is the artifact-server destination path.
	FilePath string `json:"filePath,omitempty"`

	// ArtifactName is the primary Artifact CR name for this row.
	ArtifactName string `json:"artifactName,omitempty"`

	// Open is the launcher "View" link label (navigation uses dashlet target).
	Open string `json:"open,omitempty"`
}
