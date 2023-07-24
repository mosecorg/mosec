// Copyright 2023 MOSEC Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use utoipa::openapi::{Components, OpenApi, PathItemType};

use crate::config::Route;

#[derive(Default, Clone)]
pub(crate) struct MosecOpenAPI {
    pub api: OpenApi,
}

impl MosecOpenAPI {
    /// Merge the route request_body/response/schemas into the OpenAPI.
    pub fn merge_route(&mut self, route: &Route) -> &mut Self {
        let reserved = match route.is_sse {
            true => "/openapi/reserved/inference",
            false => "/openapi/reserved/inference_sse",
        };
        let mut path = self.api.paths.paths.get(reserved).unwrap().clone();
        let op = path.operations.get_mut(&PathItemType::Post).unwrap();

        if let Some(mut user_schemas) = route.schemas.clone() {
            if self.api.components.is_none() {
                self.api.components = Some(Components::default());
            }
            self.api
                .components
                .as_mut()
                .unwrap()
                .schemas
                .append(&mut user_schemas);
        };
        if let Some(req) = route.request_body.clone() {
            op.request_body = Some(req);
        };

        if let Some(mut responses) = route.responses.clone() {
            op.responses.responses.append(&mut responses);
        };

        self.api.paths.paths.insert(route.endpoint.clone(), path);
        self
    }

    /// Removes the reserved paths from the OpenAPI spec.
    pub fn clean(&mut self) -> &mut Self {
        self.api.paths.paths.remove("/openapi/reserved/inference");
        self.api
            .paths
            .paths
            .remove("/openapi/reserved/inference_sse");
        self
    }
}
