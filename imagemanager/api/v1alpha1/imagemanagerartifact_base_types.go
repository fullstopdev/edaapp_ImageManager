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

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ImageManagerArtifact is a flat launcher row for one tracked upload/image.
// Cluster-scoped; metadata.name is stable per upload (see controller).
// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:path=imagemanagerartifacts,scope=Cluster
// +kubebuilder:printcolumn:name="Display",type=string,JSONPath=`.status.displayName`
// +kubebuilder:printcolumn:name="Namespace",type=string,JSONPath=`.status.namespace`
// +kubebuilder:printcolumn:name="Size",type=integer,JSONPath=`.status.sizeBytes`
// +kubebuilder:printcolumn:name="Status",type=string,JSONPath=`.status.downloadStatus`
type ImageManagerArtifact struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Status ImageManagerArtifactStatus `json:"status,omitempty"`
}

// ImageManagerArtifactList contains a list of ImageManagerArtifact
// +kubebuilder:object:root=true
type ImageManagerArtifactList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []ImageManagerArtifact `json:"items"`
}

func init() {
	SchemeBuilder.Register(&ImageManagerArtifact{}, &ImageManagerArtifactList{})
}
