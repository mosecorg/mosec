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

use std::collections::BTreeMap;
use std::str::FromStr;

use serde::Deserialize;
use utoipa::openapi::path::Operation;
use utoipa::openapi::request_body::RequestBody;
use utoipa::openapi::{Components, OpenApi, PathItemType, RefOr, Response, Responses, Schema};

#[derive(Deserialize, Default)]
pub(crate) struct PythonAPIDoc {
    #[serde(skip_serializing_if = "Option::is_none", default)]
    request_body: Option<RequestBody>,

    #[serde(skip_serializing_if = "Option::is_none", default)]
    responses: Option<BTreeMap<String, RefOr<Response>>>,

    #[serde(skip_serializing_if = "Option::is_none", default)]
    schemas: Option<BTreeMap<String, RefOr<Schema>>>,
}

impl FromStr for PythonAPIDoc {
    type Err = serde_json::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        serde_json::from_str::<PythonAPIDoc>(s)
    }
}

#[derive(Default, Clone)]
pub(crate) struct MosecOpenAPI {
    pub api: OpenApi,
}

impl MosecOpenAPI {
    fn get_operation(&mut self, route: &str, method: &PathItemType) -> Option<&mut Operation> {
        let path = self.api.paths.paths.get_mut(route).unwrap();
        path.operations.get_mut(method)
    }

    fn get_route_request_body(
        &mut self,
        route: &str,
        method: &PathItemType,
    ) -> Option<&mut RequestBody> {
        let op = self.get_operation(route, method).unwrap();
        if op.request_body.is_none() {
            op.request_body = Some(RequestBody::default());
        }
        op.request_body.as_mut()
    }

    fn get_route_responses(&mut self, route: &str, method: &PathItemType) -> &mut Responses {
        let op = self.get_operation(route, method).unwrap();
        &mut op.responses
    }

    /// merge PythonAPIDoc of target route to mosec api
    pub fn merge(&mut self, route: &str, python_api: PythonAPIDoc) {
        // let mut api = self.api.clone();

        if let Some(mut other_schemas) = python_api.schemas {
            if self.api.components.is_none() {
                self.api.components = Some(Components::default());
            }
            self.api
                .components
                .as_mut()
                .unwrap()
                .schemas
                .append(&mut other_schemas);
        };

        if let Some(req) = python_api.request_body {
            let req_body = self
                .get_route_request_body(route, &PathItemType::Post)
                .unwrap();
            *req_body = req;
        };

        if let Some(mut responses) = python_api.responses {
            let response = self.get_route_responses(route, &PathItemType::Post);
            response.responses.append(&mut responses);
        };
    }

    /// This function replaces a [OpenAPI Path Item Object][path_item] from path `from` to path `to`.
    ///
    /// e.g. /inference -> /v1/inference.
    ///
    /// It is used to handle cases where variable paths are not supported by the [utoipa-gen][utoipa-gen] library.
    ///
    /// [path_item]: https://spec.openapis.org/oas/latest.html#path-item-object
    /// [utoipa-gen]: https://crates.io/crates/utoipa-gen
    pub fn replace_path_item(&mut self, from: &str, to: &str) {
        if let Some(path_item) = self.api.paths.paths.remove(from) {
            self.api.paths.paths.insert(to.to_owned(), path_item);
        }
    }
}
