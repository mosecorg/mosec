import argparse


class ArgParser:
    @classmethod
    def parse(cls) -> argparse.Namespace:
        """Parsing user configurations"""
        parser = argparse.ArgumentParser(
            description="Mosec Server Configurations",
        )

        parser.add_argument(
            "--path",
            help="Unix Domain Socket address for internal Inter-Process Communication",
            type=str,
            default="/tmp/mosec",
        )

        parser.add_argument(
            "--capacity",
            help="Capacity of the request queue, beyond which new requests will be "
            "rejected with status 429",
            type=int,
            default=1024,
        )

        parser.add_argument(
            "--timeout",
            help="Service timeout for one request (milliseconds)",
            type=int,
            default=3000,
        )

        parser.add_argument(
            "--wait",
            help="Wait time for the batcher to batch (milliseconds)",
            type=int,
            default=10,
        )

        parser.add_argument(
            "--address",
            help="Address of the HTTP service",
            type=str,
            default="0.0.0.0",
        )

        parser.add_argument(
            "--port",
            help="Port of the HTTP service",
            type=int,
            default=8000,
        )

        parser.add_argument(
            "--namespace",
            help="Namespace for prometheus metrics",
            type=str,
            default="mosec_service",
        )

        args = parser.parse_args()
        return args


if __name__ == "__main__":
    ArgParser.parse()
