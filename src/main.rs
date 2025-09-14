// Copyright 2022 MOSEC Authors
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

#![forbid(unsafe_code)]

mod apidoc;
mod config;
mod errors;
mod metrics;
mod protocol;
mod routes;
mod tasks;

use std::env;
use std::fs::read_to_string;
use std::net::SocketAddr;

use axum::Router;
use axum::routing::{get, post};
use log::{debug, info};
use logforth::append;
use logforth::layout::{JsonLayout, TextLayout};
use logforth::record::LevelFilter;
use tokio::signal::unix::{SignalKind, signal};
use tower::ServiceBuilder;
use tower_http::compression::CompressionLayer;
use tower_http::decompression::RequestDecompressionLayer;
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

use crate::apidoc::MosecOpenAPI;
use crate::config::Config;
use crate::metrics::{METRICS, Metrics};
use crate::routes::{RustAPIDoc, index, inference, metrics, sse_inference};
use crate::tasks::{TASK_MANAGER, TaskManager};

async fn shutdown_signal() {
    let mut interrupt = signal(SignalKind::interrupt()).unwrap();
    let mut terminate = signal(SignalKind::terminate()).unwrap();
    loop {
        tokio::select! {
            _ = interrupt.recv() => {
                info!("service received interrupt signal, will ignore it here \
                    since it should be controlled by the main process (send SIGTERM \
                    to `mosec` if you really want to kill it manually)");
            },
            _ = terminate.recv() => {
                info!("service received terminate signal");
                let task_manager = TaskManager::global();
                task_manager.shutdown().await;
                info!("service shutdown complete");
                break;
            },
        };
    }
}

#[tokio::main]
async fn run(conf: &Config) {
    let mut doc = MosecOpenAPI {
        api: RustAPIDoc::openapi(),
    };
    for route in &conf.routes {
        doc.merge_route(route);
    }
    doc.clean();

    let metrics_instance = Metrics::init_with_namespace(&conf.namespace, conf.timeout);
    METRICS.set(metrics_instance).unwrap();
    let mut task_manager = TaskManager::new(conf.timeout);
    let barrier = task_manager.init_from_config(conf);
    TASK_MANAGER.set(task_manager).unwrap();

    let mut router = Router::new()
        .merge(SwaggerUi::new("/openapi/swagger").url("/openapi/metadata.json", doc.api))
        .route("/", get(index))
        .route("/metrics", get(metrics));

    for route in &conf.routes {
        if route.is_sse {
            router = router.route(&route.endpoint, post(sse_inference));
        } else {
            router = router.route(&route.endpoint, post(inference));
        }
    }

    if conf.compression {
        router = router.layer(
            ServiceBuilder::new()
                .layer(RequestDecompressionLayer::new())
                .layer(CompressionLayer::new()),
        );
    }

    // wait until each stage has at least one worker alive
    barrier.wait().await;
    let addr: SocketAddr = format!("{}:{}", conf.address, conf.port).parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    info!(addr:?; "http service is running");
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

fn main() {
    // let opts: Opts = argh::from_env();
    let cmd_args: Vec<String> = env::args().collect();
    if cmd_args.len() != 2 {
        println!("expect one argument as the config path but got {cmd_args:?}");
        return;
    }
    let config_str = read_to_string(&cmd_args[1]).expect("read config file failure");
    let conf: Config = serde_json::from_str(&config_str).expect("parse config failure");

    if conf.log_level == "debug" {
        // use colorful log for debug
        let layout = TextLayout::default().timezone(jiff::tz::TimeZone::UTC);
        logforth::starter_log::builder()
            .dispatch(|d| {
                d.filter(LevelFilter::Debug)
                    .append(append::Stderr::default().with_layout(layout))
            })
            .apply();
    } else {
        // use JSON format for production
        let level_filter = match conf.log_level.as_str() {
            "error" => LevelFilter::Error,
            "warning" => LevelFilter::Warn,
            _ => LevelFilter::Info,
        };
        let layout = JsonLayout::default().timezone(jiff::tz::TimeZone::UTC);
        logforth::starter_log::builder()
            .dispatch(|d| {
                d.filter(level_filter)
                    .append(append::Stderr::default().with_layout(layout))
            })
            .apply();
    }

    debug!(conf:?; "parse service arguments");
    run(&conf);
}
