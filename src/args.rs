use clap::{crate_version, AppSettings, Clap};

#[derive(Clap, Debug)]
#[clap(version = crate_version!())]
#[clap(setting = AppSettings::ColoredHelp)]
// #[clap(setting = AppSettings::)]
pub(crate) struct Opts {
    /// Unix domain socket directory path
    #[clap(short, long, default_value = "/tmp/mosec")]
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
}
