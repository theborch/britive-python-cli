import sys


sys.tracebacklimit = 0


def get_args():
    from getopt import getopt  # lazy load
    from sys import argv  # lazy load
    options, non_options = getopt(argv[1:], 't:T:p:f:P:hv', [
        'tenant=',
        'token=',
        'passphrase=',
        'help',
        'version'
    ])

    args = {
        'tenant': None,
        'token': None,
        'passphrase': None
    }

    for opt, arg in options:
        if opt in ('-t', '--tenant'):
            args['tenant'] = arg
        if opt in ('-T', '--token'):
            args['token'] = arg
        if opt in ('-p', '--passphrase'):
            args['passphrase'] = arg
        if opt in ('-h', '--help'):
            usage()
        if opt in ('-v', '--version'):
            from platform import platform, python_version  # lazy load
            from pkg_resources import get_distribution  # lazy load
            cli_version = get_distribution('pybritive').version
            print(
                f'pybritive: {cli_version} / platform: {platform()} / python: {python_version()}'
            )
            exit()

    return args


def usage():
    from sys import argv  # lazy load
    print("Usage : %s [-t/--tenant, -T/--token, -t/--passphrase, -f/--force-renew]" % (argv[0]))
    exit()


def process():
    args = get_args()

    from .k8s_exec_credential_builder import KubernetesExecCredentialProcessor

    k8s_processor = KubernetesExecCredentialProcessor()

    from .cache import Cache  # lazy load
    creds = Cache(passphrase=args['passphrase']).get_credentials(
        profile_name=k8s_processor.profile,
        mode='kube-exec'
    )
    if creds:
        from datetime import datetime  # lazy load
        expiration = datetime.fromisoformat(creds['expirationTime'].replace('Z', ''))
        now = datetime.utcnow()
        if now > expiration:  # creds have expired so set to none so new one get checked out
            creds = None
        else:
            print(k8s_processor.construct_exec_credential(creds))
            exit()

    if not creds:
        from ..britive_cli import BritiveCli  # lazy load for performance purposes

        b = BritiveCli(tenant_name=args['tenant'], token=args['token'], passphrase=args['passphrase'], silent=True)
        b.config.get_tenant()  # have to load the config here as that work is generally done elsewhere
        b.checkout(
            alias=None,
            blocktime=None,
            console=False,
            justification=None,
            mode='kube-exec',
            maxpolltime=None,
            profile=k8s_processor.profile,
            passphrase=args['passphrase'],
            force_renew=None,
            aws_credentials_file=None,
            gcloud_key_file=None,
            verbose=None
        )
        exit()


def main():
    process()


if __name__ == '__main__':
    main()
