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

use hyper::StatusCode;
use serde::Deserialize;
use utoipa::openapi::{
    path::Operation, request_body::RequestBody, Components, Content, ContentBuilder, OpenApi,
    PathItemType, RefOr, ResponseBuilder, Responses, Schema,
};

#[derive(Deserialize, Default)]
pub(crate) struct InferenceSchemas {
    req_schema: RefOr<Schema>,
    res_schema: RefOr<Schema>,
    schemas: BTreeMap<String, RefOr<Schema>>,
}

impl FromStr for InferenceSchemas {
    type Err = serde_json::Error;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        serde_json::from_str::<InferenceSchemas>(s)
    }
}

pub(crate) struct MosecApiDoc {
    pub rust_api: OpenApi,
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

    fn merge_schemas(&self, api: &mut OpenApi, mut other_schemas: BTreeMap<String, RefOr<Schema>>) {
        if api.components.is_none() {
            api.components = Some(Components::default());
        }
        let schemas = &mut api.components.as_mut().unwrap().schemas;
        schemas.append(&mut other_schemas);
    }

    fn merge_request(&self, req_body: &mut RequestBody, req_schema: RefOr<Schema>) {
        let content = ContentBuilder::new().schema(req_schema).build();
        req_body
            .content
            .insert("application/json".to_string(), content);
    }

    fn merge_response(&self, response: &mut Responses, res_schema: RefOr<Schema>) {
        let ok_res = ResponseBuilder::new()
            .content("application/json", Content::new(res_schema))
            .build();
        response
            .responses
            .insert(StatusCode::OK.as_str().to_string(), RefOr::from(ok_res));
    }

    pub fn merge(&self, python_schema: InferenceSchemas) -> OpenApi {
        let mut api = self.rust_api.clone();
        self.merge_schemas(&mut api, python_schema.schemas.clone());

        let req_body = self
            .get_route_request_body(&mut api, "/inference", &PathItemType::Post)
            .unwrap();
        self.merge_request(req_body, python_schema.req_schema);

        let response = self.get_route_responses(&mut api, "/inference", &PathItemType::Post);
        self.merge_response(response, python_schema.res_schema);
        api
    }
}
