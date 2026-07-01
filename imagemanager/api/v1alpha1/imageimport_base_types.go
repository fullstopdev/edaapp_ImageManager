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

// ImageImport is the Schema for the imageimports API. Creating one is the
// declarative equivalent of using the app's "Upload Image From File" dialog:
// the controller fetches spec.sourceUrl, auto-detects the image kind, and
// creates the same Artifact(s) a manual upload would, targeting this CR's
// own namespace.
// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:path=imageimports,scope=Namespaced,shortName=imgimport
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="NOS",type=string,JSONPath=`.status.detectedNos`
// +kubebuilder:printcolumn:name="Size",type=integer,JSONPath=`.status.sizeBytes`
// +kubebuilder:printcolumn:name="Message",type=string,JSONPath=`.status.message`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`
type ImageImport struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   ImageImportSpec   `json:"spec,omitempty"`
	Status ImageImportStatus `json:"status,omitempty"`
}

// ImageImportList contains a list of ImageImport
// +kubebuilder:object:root=true
type ImageImportList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []ImageImport `json:"items"`
}

func init() {
	SchemeBuilder.Register(&ImageImport{}, &ImageImportList{})
}
