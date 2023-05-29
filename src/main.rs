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

mod args;
mod coordinator;
mod errors;
mod metrics;
mod protocol;
mod routes;
mod tasks;

use std::net::SocketAddr;

use axum::{
    routing::{get, post},
    Router,
};
use tokio::signal::unix::{signal, SignalKind};
use tracing::info;
use tracing_subscriber::fmt::time::OffsetTime;
use tracing_subscriber::{filter, prelude::*, Layer};

use crate::args::Opts;
use crate::coordinator::Coordinator;
use crate::routes::{index, inference, metrics, sse_inference, AppState};
use crate::tasks::TaskManager;

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
async fn run(opts: &Opts) {
    let state = AppState {
        mime: opts.mime.clone(),
    };
    let coordinator = Coordinator::init_from_opts(opts);
    let barrier = coordinator.run();
    barrier.wait().await;

    let app = Router::new()
        .route("/", get(index))
        .route("/metrics", get(metrics))
        .route("/inference", post(inference))
        .route("/sse_inference", post(sse_inference))
        .with_state(state);

    let addr: SocketAddr = format!("{}:{}", opts.address, opts.port).parse().unwrap();
    info!(?addr, "http service is running");
    axum::Server::bind(&addr)
        .serve(app.into_make_service())
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

fn main() {
    let opts: Opts = argh::from_env();

    // this has to be defined before tokio multi-threads
    let timer = OffsetTime::local_rfc_3339().expect("local time offset");
    if opts.debug {
        // use colorful log for debug
        let output = tracing_subscriber::fmt::layer().compact().with_timer(timer);
        tracing_subscriber::registry()
            .with(
                output
                    .with_filter(filter::filter_fn(|metadata| {
                        !metadata.target().starts_with("hyper")
                    }))
                    .with_filter(filter::LevelFilter::DEBUG),
            )
            .init();
    } else {
        // use JSON format for production
        tracing_subscriber::fmt()
            .with_max_level(tracing::Level::INFO)
            .json()
            .with_timer(timer)
            .init();
    }

    info!(?opts, "parse service arguments");
    run(&opts);
}
