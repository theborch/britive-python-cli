import yaml
from pathlib import Path
from .config import ConfigManager
from ..britive_cli import BritiveCli
import os


def sanitize(name: str):
    name = name.lower()
    # name = name.replace(' ', '_').replace('/', "_").replace('\\', '_')
    return name


def check_env_var(filename, cli: BritiveCli):
    kubeconfig = os.getenv('KUBECONFIG')

    # no env var present
    if not kubeconfig:
        command = f'export KUBECONFIG=~/.kube/config:{filename}'
        cli.print(f'Please ensure your KUBECONFIG environment variable includes the Britive managed kube config file.')
        cli.print(command)
    else:
        for configfile in kubeconfig.split(':'):
            full_path = str(Path(configfile).expanduser()).lower()
            if filename.lower() == full_path:
                return  # we found what we came for - silently continue

        # if we get here we need to instruct the user to add the britive managed kube config file
        cli.print(f'Please modify your KUBECONFIG environment variable to include the '
                  f'Britive managed kube config file.')
        command = f'export KUBECONFIG="${{KUBECONFIG}}:{filename}"'
        cli.print(command)


def merge_new_with_existing(clusters, contexts, users, filename, tenant, assigned_aliases):
    # get the existing config, so we can pop out all
    # items related to this tenant as we will be replacing
    # them with the above created items
    existing_kubeconfig = {}
    if Path(filename).exists():
        with open(filename, 'r') as f:
            existing_kubeconfig = yaml.safe_load(f) or {}

    prefix = f'{tenant}-'
    for cluster in existing_kubeconfig.get('clusters', []):
        if not cluster.get('name', '').startswith(prefix):
            clusters.append(cluster)

    for context in existing_kubeconfig.get('contexts', []):
        name = context.get('name', '')
        if not name.startswith(prefix) and name not in assigned_aliases:
            contexts.append(context)

    for user in existing_kubeconfig.get('users', []):
        if not user.get('name', '').startswith(prefix):
            users.append(user)

    kubeconfig = {
        'apiVersion': 'v1',
        'clusters': clusters,
        'contexts': contexts,
        'users': users,
        'kind': 'Config'
    }

    # write out the config file
    with open(filename, 'w') as f:
        yaml.safe_dump(kubeconfig, f, default_flow_style=False, encoding='utf-8')


def parse_profiles(profiles, aliases):
    cluster_names = {}
    assigned_aliases = []
    for profile in profiles:
        env_profile = f"{sanitize(profile['env'])}-{sanitize(profile['profile'].lower())}"
        if env_profile not in cluster_names:
            app = BritiveCli.escape_profile_element(profile['app'])
            env = BritiveCli.escape_profile_element(profile['env'])
            pro = BritiveCli.escape_profile_element(profile['profile'])

            escaped_profile_str = f"{app}/{env}/{pro}".lower()
            alias = aliases.get(escaped_profile_str, None)
            assigned_aliases.append(alias)

            cluster_names[env_profile] = {
                'apps': [],
                'url': profile['url'],
                'cert': profile['cert'],
                'escaped_profile': escaped_profile_str,
                'profile': f"{profile['app']}/{profile['env']}/{profile['profile']}".lower(),
                'alias': alias
            }
        cluster_names[env_profile]['apps'].append(sanitize(profile['app']))
    return [cluster_names, assigned_aliases]


def build_tenant_config(tenant, cluster_names, username):
    users = [
        {
            'name': username,
            'user': {
                'exec': {
                    'apiVersion': 'client.authentication.k8s.io/v1beta1',
                    'command': 'pybritive-kube-exec',
                    'args': [
                        '-t',
                        tenant
                    ],
                    'env': None,
                    'interactiveMode': 'Never',
                    'provideClusterInfo': True
                }
            }
        }
    ] if len(cluster_names.keys()) > 0 else []
    contexts = []
    clusters = []

    for env_profile, details in cluster_names.items():
        if len(details['apps']) == 1:
            names = [env_profile]
        else:
            names = [f"{sanitize(a)}-{env_profile}" for a in details['apps']]

        cert = details['cert']
        url = details['url']

        for name in names:
            clusters.append(
                {
                    'name': f'{tenant}-{name}',
                    'cluster': {
                        'certificate-authority-data': cert,
                        'server': url,
                        'extensions': [
                            {
                                'name': 'client.authentication.k8s.io/exec',
                                'extension': {
                                    'britive-profile': details.get('alias', details['escaped_profile'])
                                }
                            }
                        ]
                    }
                }
            )

            contexts.append(
                {
                    'name': details.get('alias', f'{tenant}-{name}'),
                    'context': {
                        'cluster': f'{tenant}-{name}',
                        'user': username
                    }
                }
            )
    return [clusters, contexts, users]


def build_kube_config(profiles: list, config: ConfigManager, username: str, cli: BritiveCli):
    tenant = config.get_tenant()['alias'].lower()  # must be run first to set the tenant alias in the config

    # something unique that is not likely to clash with any other username that may be present in a kube config file
    # add the tenant details which will mean 1 user per tenant
    username = f'{tenant}-{username}'

    # grab the aliases
    aliases = config.get_profile_aliases(reverse_keys=True)

    # parse all the profiles
    cluster_names, assigned_aliases = parse_profiles(profiles, aliases)

    # establish the 3 elements of the config
    clusters, contexts, users = build_tenant_config(
        tenant=tenant,
        cluster_names=cluster_names,
        username=username
    )

    # calculate the path for the config
    kube_dir = Path(config.base_path) / 'kube'
    kube_dir.mkdir(exist_ok=True)
    filename = str(kube_dir / 'config')

    # merge any existing config with the new config
    # and write it to disk
    merge_new_with_existing(
        clusters=clusters,
        contexts=contexts,
        users=users,
        tenant=tenant,
        filename=filename,
        assigned_aliases=assigned_aliases
    )

    # if required ensure we tell the user they need to modify their KUBECONFIG env var
    # in order to pick up the Britive managed kube config file
    if len(clusters) > 0:
        check_env_var(filename=filename, cli=cli)
