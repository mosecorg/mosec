use clap::{crate_version, AppSettings, Clap};

#[derive(Clap, Debug)]
#[clap(version = crate_version!())]
#[clap(setting = AppSettings::ColoredHelp)]
pub(crate) struct Opts {
    /// Unix domain socket directory path
    #[clap(long, default_value = "")]
    pub(crate) path: String,

    /// batch size for each stage
    #[clap(short, long, default_values = &["1", "8", "1"])]
    pub(crate) batches: Vec<u32>,

    /// capacity for the channel
    /// (when the channel is full, the new requests will be dropped with 429 Too Many Requests)
    #[clap(short, long, default_value = "1024")]
    pub(crate) capacity: usize,

    /// timeout for one request (milliseconds)
    #[clap(short, long, default_value = "3000")]
    pub(crate) timeout: u64,

    /// wait time for each batch (milliseconds)
    #[clap(short, long, default_value = "10")]
    pub(crate) wait: u64,

    /// service host
    #[clap(short, long, default_value = "0.0.0.0")]
    pub(crate) address: String,

    /// service port
    #[clap(short, long, default_value = "8000")]
    pub(crate) port: u16,

    /// metrics namespace
    #[clap(short, long, default_value = "mosec_service")]
    pub(crate) namespace: String,
}
