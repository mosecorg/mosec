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

use std::{collections::BTreeMap, str::FromStr};

use serde::Deserialize;
use utoipa::openapi::{
    path::Operation, request_body::RequestBody, Components, OpenApi, PathItemType, RefOr, Response,
    Responses, Schema,
};

#[derive(Deserialize, Default)]
pub(crate) struct PythonApiDoc {
    #[serde(skip_serializing_if = "Option::is_none", default)]
    request_body: Option<RequestBody>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    responses: Option<BTreeMap<String, RefOr<Response>>>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    schemas: Option<BTreeMap<String, RefOr<Schema>>>,
}

impl FromStr for PythonApiDoc {
    type Err = serde_json::Error;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        serde_json::from_str::<PythonApiDoc>(s)
    }
}

pub(crate) struct MosecApiDoc {
    pub api: OpenApi,
}

impl MosecApiDoc {
    fn get_operation<'a>(
        &self,
        api: &'a mut OpenApi,
        route: &str,
        method: &PathItemType,
    ) -> Option<&'a mut Operation> {
        let path = api.paths.paths.get_mut(route).unwrap();
        path.operations.get_mut(method)
    }

    fn get_route_request_body<'a>(
        &self,
        api: &'a mut OpenApi,
        route: &str,
        method: &PathItemType,
    ) -> Option<&'a mut RequestBody> {
        let op = self.get_operation(api, route, method).unwrap();
        if op.request_body.is_none() {
            op.request_body = Some(RequestBody::default());
        }
        op.request_body.as_mut()
    }

    fn get_route_responses<'a>(
        &self,
        api: &'a mut OpenApi,
        route: &str,
        method: &PathItemType,
    ) -> &'a mut Responses {
        let op = self.get_operation(api, route, method).unwrap();
        &mut op.responses
    }

    pub fn merge(&self, route: &str, python_api: PythonApiDoc) -> Self {
        // merge PythonApiDoc of target route to mosec api
        let mut api = self.api.clone();

        if let Some(mut other_schemas) = python_api.schemas {
            if api.components.is_none() {
                api.components = Some(Components::default());
            }
            api.components
                .as_mut()
                .unwrap()
                .schemas
                .append(&mut other_schemas);
        };

        if let Some(req) = python_api.request_body {
            let req_body = self
                .get_route_request_body(&mut api, route, &PathItemType::Post)
                .unwrap();
            *req_body = req;
        };

        if let Some(mut responses) = python_api.responses {
            let response = self.get_route_responses(&mut api, route, &PathItemType::Post);
            response.responses.append(&mut responses);
        };

        MosecApiDoc { api }
    }

    pub fn move_path(&self, from: &str, to: &str) -> Self {
        // move one path to another
        let mut api = self.api.clone();
        if let Some(r) = api.paths.paths.remove(from) {
            api.paths.paths.insert(to.to_owned(), r);
        }
        MosecApiDoc { api }
    }
}
